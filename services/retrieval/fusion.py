from abc import ABC, abstractmethod

from packages.contracts.retrieval import CandidateChannel, RetrievalCandidate


class CandidateFusion(ABC):
    @abstractmethod
    def fuse(
        self,
        lexical: list[RetrievalCandidate],
        semantic: list[RetrievalCandidate],
    ) -> list[tuple[str, float]]:
        raise NotImplementedError


class ReciprocalRankFusion(CandidateFusion):
    """Provisional RRF configuration; weights require real multilingual evaluation."""

    def __init__(
        self, lexical_weight: float = 1.0, semantic_weight: float = 1.0, rank_constant: int = 60
    ) -> None:
        self.lexical_weight = lexical_weight
        self.semantic_weight = semantic_weight
        self.rank_constant = rank_constant

    def fuse(
        self,
        lexical: list[RetrievalCandidate],
        semantic: list[RetrievalCandidate],
    ) -> list[tuple[str, float]]:
        scores: dict[str, float] = {}
        for candidate in [*lexical, *semantic]:
            weight = (
                self.lexical_weight
                if candidate.channel is CandidateChannel.LEXICAL
                else self.semantic_weight
            )
            scores[candidate.chunk_id] = scores.get(candidate.chunk_id, 0.0) + weight / (
                self.rank_constant + candidate.rank
            )
        return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
