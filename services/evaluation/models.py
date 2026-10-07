from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.contracts.assistant import ConversationTurn, ResponseKind
from packages.contracts.common import Language


class EvaluationScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    department: str
    location: str
    role: str


class EvaluationCase(BaseModel):
    """One benchmark question.

    Section identifiers are chunker-independent corpus keys (see ``services.evaluation.corpus``),
    so the same case can score the current chunker and any future chunker. Every field added
    after the first fixture schema has a default so older datasets stay valid.
    """

    model_config = ConfigDict(extra="forbid")
    id: str = ""
    question: str
    language: Language
    employee_scope: EvaluationScope
    expected_sections: set[str] = Field(default_factory=set)
    alternate_sections: set[str] = Field(default_factory=set)
    forbidden_sections: set[str] = Field(default_factory=set)
    answerable: bool
    requires_clarification: bool = False
    broad_synthesis_allowed: bool = False
    expected_facts: list[str] = Field(default_factory=list)
    forbidden_facts: list[str] = Field(default_factory=list)
    expected_response_kind: ResponseKind | None = None
    history: list[ConversationTurn] = Field(default_factory=list)
    tags: set[str] = Field(default_factory=set)
    notes: str = ""

    @model_validator(mode="after")
    def validate_consistency(self) -> Self:
        relevant = self.expected_sections | self.alternate_sections
        if relevant & self.forbidden_sections:
            raise ValueError("A section cannot be both acceptable and forbidden")
        if self.expected_sections & self.alternate_sections:
            raise ValueError("A section cannot be both expected and an alternate")
        if self.alternate_sections and not self.expected_sections:
            raise ValueError("Alternate sections require at least one expected section")
        if self.answerable and self.requires_clarification:
            raise ValueError("A case that needs clarification is not directly answerable")
        if not self.answerable and (self.expected_sections or self.expected_facts):
            raise ValueError("Unanswerable cases cannot declare expected sections or facts")
        if self.answerable and not self.expected_sections:
            raise ValueError("Answerable cases must declare at least one expected section")
        if set(self.expected_facts) & set(self.forbidden_facts):
            raise ValueError("A fact cannot be both expected and forbidden")
        return self

    @property
    def target_kind(self) -> ResponseKind:
        """Response kind the assistant should produce for this case."""
        if self.expected_response_kind is not None:
            return self.expected_response_kind
        if self.requires_clarification:
            return ResponseKind.CLARIFICATION
        return ResponseKind.POLICY_ANSWER if self.answerable else ResponseKind.NO_ANSWER


class RetrievalMetrics(BaseModel):
    """Aggregate retrieval quality.

    Rank metrics (recall, precision, MRR, nDCG, fact recall) average only over cases that declare
    expected sections; ``cases_scored`` is that count. The unauthorized rate averages over every
    returned chunk in every case.
    """

    k: int | None = None
    cases_scored: int = 0
    recall_at_k: float
    precision_at_k: float
    mean_reciprocal_rank: float
    ndcg_at_k: float = 0.0
    fact_recall_at_k: float | None = None
    unauthorized_retrieval_rate: float
    unauthorized_retrieval_count: int = 0
    cases_with_unauthorized_retrieval: int = 0
