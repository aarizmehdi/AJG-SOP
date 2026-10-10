from collections.abc import Mapping, Sequence
from typing import Any

import anyio
from pinecone import Pinecone

from services.ingestion.embeddings.base import EmbeddingProvider


class EmbeddingConfigurationError(RuntimeError):
    pass


class EmbeddingDimensionError(RuntimeError):
    pass


class PineconeE5EmbeddingProvider(EmbeddingProvider):
    """Pinecone-hosted multilingual E5 with distinct passage/query semantics."""

    def __init__(
        self,
        api_key: str,
        index_name: str,
        model_id: str,
        *,
        client: Any | None = None,
    ) -> None:
        self.model_id = model_id
        self._client = client or Pinecone(api_key=api_key)
        description = self._client.describe_index(index_name)
        configured_model = self._value(self._value(description, "embed"), "model")
        if configured_model != model_id:
            raise EmbeddingConfigurationError(
                f"Pinecone index model is {configured_model!r}; configured model is {model_id!r}"
            )
        model = self._client.inference.get_model(model=model_id)
        dimension = self._value(model, "default_dimension")
        if not isinstance(dimension, int) or dimension <= 0:
            raise EmbeddingConfigurationError("Pinecone E5 model dimension is unavailable")
        self.dimension = dimension
        stats = self._client.Index(index_name).describe_index_stats()
        index_dimension = self._value(stats, "dimension")
        if index_dimension != self.dimension:
            raise EmbeddingDimensionError(
                f"Embedding dimension {self.dimension} does not match Pinecone index dimension "
                f"{index_dimension}"
            )

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, "passage")

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self._embed([text], "query")
        return vectors[0]

    async def _embed(self, texts: Sequence[str], input_type: str) -> list[list[float]]:
        if not texts:
            return []
        response = await anyio.to_thread.run_sync(
            lambda: self._client.inference.embed(
                model=self.model_id,
                inputs=list(texts),
                parameters={"input_type": input_type, "truncate": "END"},
            )
        )
        vectors = [self._vector(item) for item in response.data]
        if len(vectors) != len(texts):
            raise EmbeddingDimensionError("Pinecone returned an unexpected embedding count")
        for vector in vectors:
            if len(vector) != self.dimension:
                raise EmbeddingDimensionError(
                    f"Embedding dimension {len(vector)} does not match expected {self.dimension}"
                )
        return vectors

    @classmethod
    def _vector(cls, item: Any) -> list[float]:
        values = cls._value(item, "values")
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            raise EmbeddingDimensionError("Pinecone embedding response has no dense values")
        return [float(value) for value in values]

    @staticmethod
    def _value(item: Any, key: str) -> Any:
        if item is None:
            return None
        if isinstance(item, Mapping):
            return item.get(key)
        return getattr(item, key, None)
