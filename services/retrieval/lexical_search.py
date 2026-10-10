import re
from abc import ABC, abstractmethod
from collections.abc import Sequence

from apps.api.app.models.organization import EmployeeProfile
from packages.contracts.canonical import RetrievalChunk
from packages.contracts.retrieval import CandidateChannel, RetrievalCandidate


class LexicalCandidateRetriever(ABC):
    @abstractmethod
    async def search(
        self,
        query: str,
        profile: EmployeeProfile,
        eligible_chunks: Sequence[RetrievalChunk],
        limit: int,  # noqa: E501
    ) -> list[RetrievalCandidate]:
        raise NotImplementedError


ROMAN_URDU_MAP = {
    "chutti": "leave",
    "tankhwa": "salary",
    "tankha": "salary",
    "godam": "warehouse",
    "godown": "warehouse",
    "haziri": "attendance",
    "mansookhi": "cancellation",
    "wapsi": "return",
    "shikayat": "complaint",
    "mustarad": "rejected",
    "manzoori": "approval",
    "tareeqa": "procedure",
    "usool": "policy",
}


# Note: FixtureLexicalRetriever is the ACTUAL production lexical channel
# used in live mode. It executes an in-memory keyword search over the fully
# authorized eligible_chunks from the FoundationStore.
class FixtureLexicalRetriever(LexicalCandidateRetriever):
    async def search(
        self,
        query: str,
        profile: EmployeeProfile,
        eligible_chunks: Sequence[RetrievalChunk],
        limit: int,  # noqa: E501
    ) -> list[RetrievalCandidate]:
        normalized_query = self._normalize_urdu(query)
        terms = self._terms(normalized_query)
        query_sop_codes = self._extract_sop_codes(query)

        scored: list[tuple[RetrievalChunk, float]] = []
        for chunk in eligible_chunks:
            content = chunk.text.casefold()

            # Exact SOP number match
            policy_bonus = 0.0
            if chunk.policy_number and chunk.policy_number.casefold() in query_sop_codes:
                policy_bonus = 10.0

            # Exact phrase match
            exact_bonus = 4.0 if normalized_query in content else 0.0

            hits = sum(content.count(term) for term in terms)

            if hits > 0 or exact_bonus > 0 or policy_bonus > 0:
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
                allowed_roles=list(chunk.access.roles.values),
                department=next(iter(chunk.access.departments.values))
                if chunk.access.departments.values
                else None,  # noqa: E501
                location=next(iter(chunk.access.locations.values))
                if chunk.access.locations.values
                else None,  # noqa: E501
            )
            for rank, (chunk, score) in enumerate(scored[:limit], start=1)
        ]

    @staticmethod
    def _normalize_urdu(text: str) -> str:
        text = text.casefold()
        for urdu, eng in ROMAN_URDU_MAP.items():
            text = re.sub(rf"\b{urdu}\b", eng, text)
        return text

    @staticmethod
    def _extract_sop_codes(text: str) -> set[str]:
        # Matches formats like SOP-014, HR-POL-2024
        return set(re.findall(r"[a-z]{2,4}(?:-[a-z]{2,4})*-\d{3,4}", text.casefold()))

    @staticmethod
    def _terms(text: str) -> set[str]:
        return {term for term in re.findall(r"[\w.-]+", text.casefold()) if len(term) > 1}
