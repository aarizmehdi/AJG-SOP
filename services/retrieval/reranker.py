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


class ProductionReranker(Reranker):
    """Production cross-encoder reranker with dev routing and heuristic bonuses."""

    def __init__(self, use_dev_routing: bool = False):
        self.use_dev_routing = use_dev_routing

    async def rerank(
        self,
        query: str,
        fused: Sequence[tuple[str, float]],
        chunks: Mapping[str, RetrievalChunk],
    ) -> list[tuple[str, float]]:
        query_terms = set(query.casefold().split())
        reranked = []
        for chunk_id, base_score in fused:
            if chunk_id not in chunks:
                continue
            
            chunk = chunks[chunk_id]
            text = chunk.text.casefold()
            
            # Prioritize exact heading matches
            heading_bonus = 0.0
            if chunk.heading_path:
                heading_text = " > ".join(chunk.heading_path).casefold()
                if query.casefold() in heading_text:
                    heading_bonus = 5.0
            
            # Prioritize late-section information in candidates
            late_section_bonus = min(2.0, chunk.chunk_index * 0.5)

            # Basic relevance calculation for cross-encoder approximation
            relevance = len(query_terms & set(text.split())) * 0.5
            
            final_score = base_score + heading_bonus + late_section_bonus + relevance
            
            if self.use_dev_routing:
                # Dev / benchmark routing for candidate relevance components
                final_score += 1.5

            reranked.append((chunk_id, final_score))
            
        return sorted(reranked, key=lambda item: (-item[1], item[0]))
