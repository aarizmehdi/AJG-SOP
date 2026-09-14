import re
from collections.abc import Sequence

from packages.contracts.assistant import GeneratedAnswer
from packages.contracts.retrieval import SearchEvidence


class GroundingVerifier:
    """Deterministic safety checks; calibration awaits the real SOP evaluation set."""

    _unsupported_advice = ("contact hr", "ask hr", "call hr")

    def verify(self, answer: GeneratedAnswer, evidence: Sequence[SearchEvidence]) -> bool:
        cited_ids = {citation.chunk_id for citation in answer.citations}
        cited_text = " ".join(
            item.excerpt.casefold() for item in evidence if item.chunk_id in cited_ids
        )
        answer_text = answer.answer.casefold().strip()
        if not answer_text or not cited_text:
            return False
        unsupported_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", answer_text)) - set(
            re.findall(r"\b\d+(?:\.\d+)?\b", cited_text)
        )
        if unsupported_numbers:
            return False
        return not any(
            phrase in answer_text and phrase not in cited_text
            for phrase in self._unsupported_advice
        )
