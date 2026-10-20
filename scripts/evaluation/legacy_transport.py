"""Benchmark-only batching/retry shim for a legacy E5 provider; never used by the app."""

import os
from collections.abc import Awaitable, Callable

import anyio

from services.ingestion.embeddings.pinecone_e5 import PineconeE5EmbeddingProvider


async def _available[T](call: Callable[[], Awaitable[T]]) -> T:
    for attempt in range(3):
        try:
            return await call()
        except Exception as error:
            status = getattr(error, "status", None) or getattr(error, "status_code", None)
            if status not in {429, 500, 502, 503, 504} or attempt == 2:
                raise
            await anyio.sleep(0.5 * 2**attempt)
    raise AssertionError("Unreachable retry state")


def build_baseline_e5() -> PineconeE5EmbeddingProvider:
    provider = PineconeE5EmbeddingProvider(
        os.environ["PINECONE_API_KEY"],
        os.environ.get("PINECONE_INDEX", "aziz-jan-sop"),
        os.environ.get("EMBEDDING_MODEL", "multilingual-e5-large"),
    )
    documents, query = provider.embed_documents, provider.embed_query

    async def batched(texts: list[str]) -> list[list[float]]:
        result = []
        for offset in range(0, len(texts), 64):
            batch = texts[offset : offset + 64]
            result.extend(await _available(lambda: documents(batch)))  # noqa: B023
        return result

    async def retried(text: str) -> list[float]:
        return await _available(lambda: query(text))

    provider.embed_documents = batched  # type: ignore[method-assign]
    provider.embed_query = retried  # type: ignore[method-assign]
    return provider
