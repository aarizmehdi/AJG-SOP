from abc import ABC, abstractmethod

from apps.api.app.models.organization import EmployeeProfile
from packages.contracts.retrieval import CandidateChannel, RetrievalCandidate


class CandidateFusion(ABC):
    @abstractmethod
    def fuse(
        self,
        lexical: list[RetrievalCandidate],
        semantic: list[RetrievalCandidate],
        profile: EmployeeProfile,
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
        profile: EmployeeProfile,
    ) -> list[tuple[str, float]]:
        scores: dict[str, float] = {}
        seen_ranges: set[str] = set()

        for candidate in [*lexical, *semantic]:
            # Access-scope sanitation
            if candidate.tenant_id != profile.organization_id:
                continue
            if candidate.publication_state != "published":
                continue
            if candidate.department and candidate.department not in profile.departments and "all" not in profile.departments:  # noqa: E501
                continue
            if candidate.location and candidate.location not in profile.locations and "all" not in profile.locations:  # noqa: E501
                continue
            if candidate.allowed_roles:
                if not any(role in profile.organizational_roles for role in candidate.allowed_roles) and "all" not in profile.organizational_roles:  # noqa: E501
                    continue

            # Deduplicate by SOP ID and chunk range (using chunk_id logic)
            # Assuming chunk_id format: version_id:section_id:chunk_index
            parts = candidate.chunk_id.split(":")
            if len(parts) >= 2:
                range_key = f"{parts[0]}:{parts[1]}"
            else:
                range_key = candidate.chunk_id
            
            if range_key in seen_ranges and candidate.chunk_id not in scores:
                continue # Already have a higher ranked chunk from this section range
            
            seen_ranges.add(range_key)

            weight = (
                self.lexical_weight
                if candidate.channel is CandidateChannel.LEXICAL
                else self.semantic_weight
            )
            scores[candidate.chunk_id] = scores.get(candidate.chunk_id, 0.0) + weight / (
                self.rank_constant + candidate.rank
            )
        return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
