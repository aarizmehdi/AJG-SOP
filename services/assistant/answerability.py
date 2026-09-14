from abc import ABC, abstractmethod
from collections.abc import Sequence

from packages.contracts.retrieval import SearchEvidence


class AnswerabilityGate(ABC):
    @abstractmethod
    def is_answerable(self, question: str, evidence: Sequence[SearchEvidence]) -> bool:
        raise NotImplementedError


class FixtureAnswerabilityGate(AnswerabilityGate):
    """Evidence-presence gate; the final threshold awaits real SOP evaluation."""

    def is_answerable(self, question: str, evidence: Sequence[SearchEvidence]) -> bool:
        return bool(question.strip() and evidence)
