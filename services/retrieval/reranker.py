from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence

from packages.contracts.canonical import RetrievalChunk


class Reranker(ABC):
    @abstractmethod
    async def rerank(
        self,
        query: str,
        fused: Sequence[tuple[str, float]],
        chunks: Mapping[str, RetrievalChunk],
    ) -> list[tuple[str, float]]:
        raise NotImplementedError


class FixtureReranker(Reranker):
    """Deterministic test reranker; provider/model selection remains provisional."""

    async def rerank(
        self,
        query: str,
        fused: Sequence[tuple[str, float]],
        chunks: Mapping[str, RetrievalChunk],
    ) -> list[tuple[str, float]]:
        query_terms = set(query.casefold().split())
        reranked = [
            (
                chunk_id,
                score + 0.001 * len(query_terms & set(chunks[chunk_id].text.casefold().split())),
            )
            for chunk_id, score in fused
            if chunk_id in chunks
        ]
        return sorted(reranked, key=lambda item: (-item[1], item[0]))
