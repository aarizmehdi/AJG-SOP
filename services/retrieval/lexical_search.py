import re
from abc import ABC, abstractmethod
from collections.abc import Sequence

from apps.api.app.models.organization import EmployeeProfile
from packages.contracts.canonical import RetrievalChunk
from packages.contracts.retrieval import CandidateChannel, RetrievalCandidate


class LexicalCandidateRetriever(ABC):
    @abstractmethod
    async def search(
        self, query: str, profile: EmployeeProfile, eligible_chunks: Sequence[RetrievalChunk], limit: int
    ) -> list[RetrievalCandidate]:
        raise NotImplementedError


class FixtureLexicalRetriever(LexicalCandidateRetriever):
    async def search(
        self, query: str, profile: EmployeeProfile, eligible_chunks: Sequence[RetrievalChunk], limit: int
    ) -> list[RetrievalCandidate]:
        terms = self._terms(query)
        scored: list[tuple[RetrievalChunk, float]] = []
        for chunk in eligible_chunks:
            content = chunk.text.casefold()
            exact_bonus = 4.0 if query.casefold() in content else 0.0
            policy_bonus = (
                3.0
                if chunk.policy_number and chunk.policy_number.casefold() in query.casefold()
                else 0.0
            )
            hits = sum(content.count(term) for term in terms)
            if hits or exact_bonus or policy_bonus:
                scored.append((chunk, float(hits) + exact_bonus + policy_bonus))
        scored.sort(key=lambda item: (-item[1], item[0].id))
        return [
            RetrievalCandidate(
                tenant_id=chunk.organization_id,
                organization_id=chunk.organization_id,
                chunk_id=chunk.id,
                channel=CandidateChannel.LEXICAL,
                score=score,
                rank=rank,
                text=chunk.text,
                policy_number=chunk.policy_number,
                heading_path=chunk.heading_path,
                allowed_roles=chunk.access.roles,
                department=chunk.access.departments[0] if chunk.access.departments else None,
                location=chunk.access.locations[0] if chunk.access.locations else None,
            )
            for rank, (chunk, score) in enumerate(scored[:limit], start=1)
        ]

    @staticmethod
    def _terms(text: str) -> set[str]:
        return {term for term in re.findall(r"[\w.-]+", text.casefold()) if len(term) > 1}
