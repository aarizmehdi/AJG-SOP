import re
from abc import ABC, abstractmethod
from collections.abc import Sequence

from packages.contracts.canonical import RetrievalChunk
from packages.contracts.retrieval import CandidateChannel, RetrievalCandidate


class LexicalCandidateRetriever(ABC):
    @abstractmethod
    async def search(
        self,
        query: str,
        eligible_chunks: Sequence[RetrievalChunk],
        limit: int,
    ) -> list[RetrievalCandidate]:
        raise NotImplementedError


class FixtureLexicalRetriever(LexicalCandidateRetriever):
    """In-memory lexical candidate retriever used across both fixture and live modes.

    Despite its fixture-prefixed name, this component is the active lexical retrieval channel
    in production wiring. It operates strictly over pre-filtered, authorized eligible chunks,
    applying exact SOP code matching bonuses (+10.0), exact phrase matching bonuses (+8.0),
    stop-word-filtered term coordination matching, and sub-linear term frequency scoring.
    All candidate rankings are deterministic.
    """

    STOP_WORDS = frozenset({
        "a", "an", "the", "and", "or", "but", "if", "then", "else", "when",
        "at", "from", "by", "for", "with", "about", "against", "between",
        "into", "through", "during", "before", "after", "above", "below",
        "to", "of", "up", "down", "in", "out", "on", "off", "over", "under",
        "again", "further", "once", "here", "there", "all", "any", "both",
        "each", "few", "more", "most", "other", "some", "such", "no", "nor",
        "not", "only", "own", "same", "so", "than", "too", "very", "s", "t",
        "can", "will", "just", "don", "should", "now", "is", "are", "was",
        "were", "be", "been", "being", "have", "has", "had", "do", "does",
        "did", "doing", "what", "which", "who", "whom", "this", "that",
        "these", "those", "am", "how",
    })

    ABBREVIATIONS = {
        "standard": "std",
        "weight": "wt",
        "kilometres": "km",
        "kilometre": "km",
        "kilometers": "km",
        "kilometer": "km",
        "kilograms": "kg",
        "kilogram": "kg",
        "kgs": "kg",
        "number": "no",
        "numbers": "nos",
    }

    async def search(
        self,
        query: str,
        eligible_chunks: Sequence[RetrievalChunk],
        limit: int,
    ) -> list[RetrievalCandidate]:
        terms = self._terms(query)
        query_sop_codes = self._extract_sop_codes(query)

        # Expand domain-standard abbreviations (e.g. std <-> standard, wt <-> weight)
        expanded_terms: list[str] = []
        for t in terms:
            expanded_terms.append(t)
            if t in self.ABBREVIATIONS:
                expanded_terms.append(self.ABBREVIATIONS[t])

        scored: list[tuple[RetrievalChunk, float]] = []
        for chunk in eligible_chunks:
            content = chunk.text.casefold()

            # Exact SOP number match
            policy_bonus = 0.0
            if chunk.policy_number and chunk.policy_number.casefold() in query_sop_codes:
                policy_bonus = 10.0

            matched_terms: set[str] = set()
            tf_score = 0.0
            for t in expanded_terms:
                st = self._stem(t)
                cnt = content.count(t)
                if cnt == 0 and st != t and len(st) >= 3:
                    cnt = content.count(st)
                    if cnt > 0:
                        matched_terms.add(st)
                elif cnt > 0:
                    matched_terms.add(t)
                tf_score += min(cnt, 3)

            if not matched_terms and policy_bonus == 0.0:
                continue

            # Exact phrase match
            exact_bonus = 8.0 if query.casefold() in content else 0.0
            coord_bonus = len(matched_terms) * 5.0

            score = tf_score + coord_bonus + exact_bonus + policy_bonus
            scored.append((chunk, score))

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
                else None,
                location=next(iter(chunk.access.locations.values))
                if chunk.access.locations.values
                else None,
            )
            for rank, (chunk, score) in enumerate(scored[:limit], start=1)
        ]

    @staticmethod
    def _stem(term: str) -> str:
        if len(term) > 4:
            for suffix in ["ies", "es", "ed", "ing", "s"]:
                if term.endswith(suffix):
                    if suffix == "ies":
                        return term[:-3] + "y"
                    return term[:-len(suffix)]
        return term

    @staticmethod
    def _extract_sop_codes(text: str) -> set[str]:
        # Matches formats like SOP-014, HR-POL-2024
        return set(re.findall(r"[a-z]{2,4}(?:-[a-z]{2,4})*-\d{3,4}", text.casefold()))

    @classmethod
    def _terms(cls, text: str) -> set[str]:
        tokens = re.findall(r"[\w.-]+", text.casefold())
        content_terms = {
            t for t in tokens if (len(t) > 1 or t.isdigit()) and t not in cls.STOP_WORDS
        }
        if content_terms:
            return content_terms
        return {t for t in tokens if len(t) > 1 or t.isdigit()}
