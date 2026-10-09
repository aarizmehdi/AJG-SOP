"""Pluggable retrieval components for benchmark configurations.

Specs are plain strings so a matrix file can name them:

* chunker:    ``current`` | ``plugin:<module>:<factory>``
* embedding:  ``fixture-hash`` | ``pinecone-e5`` | ``bge-m3`` | ``plugin:<module>:<factory>``
* reranker:   ``fixture`` | ``none`` | ``plugin:<module>:<factory>``

A ``plugin`` factory is called with no arguments and must return a ``Chunker``,
``EmbeddingProvider`` or ``Reranker``. That is how another branch's chunker, embedding provider or
reranker is benchmarked without this framework importing it.

A component that cannot be built (missing credentials, optional package, missing module) raises
``ProviderUnavailableError``. The runner records the configuration as *skipped* with the reason;
it never substitutes a different component or invents numbers.

Nothing here writes to Pinecone, MongoDB or object storage. Semantic search runs in memory
(``FixtureSemanticRetriever``) over vectors produced by the selected embedding provider.
"""

import importlib
import os
import time
import zlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

import anyio

from packages.contracts.canonical import RetrievalChunk
from services.ingestion.chunking.semantic_chunker import Chunker, SectionAwareFixtureChunker
from services.ingestion.embeddings.base import EmbeddingProvider
from services.ingestion.embeddings.e5_provider import E5EmbeddingProvider
from services.retrieval.reranker import FixtureReranker, Reranker


class ProviderUnavailableError(RuntimeError):
    """The requested component cannot be constructed in this environment."""


class StableHashEmbeddingProvider(EmbeddingProvider):
    """Deterministic stand-in embedding.

    The repository's ``FixtureEmbeddingProvider`` uses Python's ``hash()``, which is randomized per
    process, so its rankings change between runs. This version uses CRC32 so benchmark numbers
    are reproducible. It is a bag-of-words hash, not a semantic model: semantic gains or losses
    measured with it say nothing about E5 or BGE-M3.
    """

    model_id = "fixture-hash-stable"
    dimension = 64

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    @classmethod
    def _vector(cls, text: str) -> list[float]:
        vector = [0.0] * cls.dimension
        for token in text.casefold().split():
            vector[zlib.crc32(token.encode("utf-8")) % cls.dimension] += 1.0
        magnitude = sum(value * value for value in vector) ** 0.5 or 1.0
        return [value / magnitude for value in vector]


@dataclass
class EmbeddingCost:
    query_calls: int = 0
    document_texts: int = 0
    provider_texts: int = 0
    provider_chars: int = 0
    provider_seconds: float = 0.0
    cache_hits: int = 0


class MeteredEmbeddingProvider(EmbeddingProvider):
    """Caches vectors by (kind, text) and records how much the wrapped provider actually did.

    ``FixtureSemanticRetriever`` re-embeds every eligible chunk for every query; without a cache
    a real provider would be called thousands of times. The counters report real provider work so
    cost comparisons stay honest.
    """

    def __init__(self, inner: EmbeddingProvider) -> None:
        self.inner = inner
        self.model_id = inner.model_id
        self.dimension = inner.dimension
        self.cost = EmbeddingCost()
        self._documents: dict[str, list[float]] = {}
        self._queries: dict[str, list[float]] = {}

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.cost.document_texts += len(texts)
        missing = list(dict.fromkeys(text for text in texts if text not in self._documents))
        self.cost.cache_hits += len(texts) - len(missing)
        if missing:
            started = time.perf_counter()
            vectors = await self.inner.embed_documents(missing)
            self.cost.provider_seconds += time.perf_counter() - started
            self.cost.provider_texts += len(missing)
            self.cost.provider_chars += sum(len(text) for text in missing)
            self._documents.update(zip(missing, vectors, strict=True))
        return [self._documents[text] for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        self.cost.query_calls += 1
        if text in self._queries:
            self.cost.cache_hits += 1
            return self._queries[text]
        started = time.perf_counter()
        vector = await self.inner.embed_query(text)
        self.cost.provider_seconds += time.perf_counter() - started
        self.cost.provider_texts += 1
        self.cost.provider_chars += len(text)
        self._queries[text] = vector
        return vector


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    """Local dense embeddings through ``sentence-transformers`` (used for BGE-M3).

    ``sentence-transformers`` and the model weights are deliberately not project dependencies;
    install them in a scratch environment to run this candidate. BGE-M3 dense retrieval needs no
    query/passage prefix, so both methods encode text unchanged.
    """

    def __init__(
        self, model_name: str = "BAAI/bge-m3", *, model: Any | None = None, max_length: int = 512
    ) -> None:
        self.model_id = model_name
        self._max_length = max_length
        if model is None:
            try:
                sentence_transformers = importlib.import_module("sentence_transformers")
            except ImportError as error:
                raise ProviderUnavailableError(
                    "sentence-transformers is not installed; run "
                    "`uv pip install sentence-transformers` in a scratch environment "
                    f"to benchmark {model_name}"
                ) from error
            try:
                model = sentence_transformers.SentenceTransformer(model_name)
            except Exception as error:  # noqa: BLE001 - weights download/load failures vary
                raise ProviderUnavailableError(
                    f"{model_name} could not be loaded: {error}"
                ) from error
        self._model: Any = model
        if hasattr(self._model, "max_seq_length"):
            self._model.max_seq_length = max_length
        dimension = self._model.get_sentence_embedding_dimension()
        if not isinstance(dimension, int) or dimension <= 0:
            raise ProviderUnavailableError(f"{model_name} did not report an embedding dimension")
        self.dimension = dimension

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._encode(texts)

    async def embed_query(self, text: str) -> list[float]:
        return (await self._encode([text]))[0]

    async def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        encoded = await anyio.to_thread.run_sync(
            lambda: self._model.encode(
                list(texts), normalize_embeddings=True, batch_size=16, show_progress_bar=False
            )
        )
        return [[float(value) for value in row] for row in encoded]


def _plugin(spec: str, kind: str) -> object:
    parts = spec.split(":")
    if len(parts) != 3 or parts[0] != "plugin" or not parts[1] or not parts[2]:
        raise ProviderUnavailableError(f"Invalid {kind} spec {spec!r}; use plugin:<module>:<name>")
    try:
        module = importlib.import_module(parts[1])
        factory = getattr(module, parts[2])
    except (ImportError, AttributeError) as error:
        raise ProviderUnavailableError(
            f"{kind} plugin {spec!r} is not importable here: {error}"
        ) from error
    try:
        return cast(object, factory())
    except Exception as error:  # noqa: BLE001 - plugin factories can fail in arbitrary ways
        raise ProviderUnavailableError(
            f"{kind} plugin {spec!r} failed to start: {error}"
        ) from error


def build_chunker(spec: str) -> Chunker:
    if spec == "current":
        return SectionAwareFixtureChunker()
    built = _plugin(spec, "chunker")
    if not isinstance(built, Chunker):
        raise ProviderUnavailableError(f"{spec!r} did not produce a Chunker")
    return built


def build_embedding(spec: str, environment: Mapping[str, str] | None = None) -> EmbeddingProvider:
    if spec == "fixture-hash":
        return StableHashEmbeddingProvider()
    if spec == "bge-m3":
        return SentenceTransformerEmbeddingProvider("BAAI/bge-m3")
    if spec == "pinecone-e5":
        return _build_pinecone_e5(environment)
    built = _plugin(spec, "embedding")
    if not isinstance(built, EmbeddingProvider):
        raise ProviderUnavailableError(f"{spec!r} did not produce an EmbeddingProvider")
    return built


def _build_pinecone_e5(environment: Mapping[str, str] | None) -> EmbeddingProvider:
    """Hosted multilingual E5, exactly as the product configures it.

    Only stateless embedding inference plus read-only index metadata checks are used; no vectors
    are upserted or queried in any index.
    """
    env = environment if environment is not None else os.environ
    api_key = env.get("PINECONE_API_KEY")
    if not api_key:
        raise ProviderUnavailableError("PINECONE_API_KEY is not set; cannot run the E5 baseline")
    try:
        return E5EmbeddingProvider(
            api_key,
            env.get("PINECONE_INDEX", "aziz-jan-sop"),
            env.get("EMBEDDING_MODEL", "multilingual-e5-large"),
        )
    except Exception as error:  # noqa: BLE001 - configuration/network errors vary
        raise ProviderUnavailableError(f"Pinecone E5 provider failed to start: {error}") from error


class IdentityReranker(Reranker):
    """No-op reranker: keeps the fused order (isolates what reranking contributes)."""

    async def rerank(
        self,
        query: str,
        fused: Sequence[tuple[str, float]],
        chunks: Mapping[str, RetrievalChunk],
    ) -> list[tuple[str, float]]:
        return [(chunk_id, score) for chunk_id, score in fused if chunk_id in chunks]


def build_reranker(spec: str) -> Reranker:
    if spec == "fixture":
        return FixtureReranker()
    if spec == "none":
        return IdentityReranker()
    built = _plugin(spec, "reranker")
    if not isinstance(built, Reranker):
        raise ProviderUnavailableError(f"{spec!r} did not produce a Reranker")
    return built
