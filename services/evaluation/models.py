from pydantic import BaseModel, ConfigDict, Field

from packages.contracts.common import Language


class EvaluationScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    department: str
    location: str
    role: str


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str
    language: Language
    employee_scope: EvaluationScope
    expected_sections: set[str] = Field(default_factory=set)
    forbidden_sections: set[str] = Field(default_factory=set)
    answerable: bool


class RetrievalMetrics(BaseModel):
    recall_at_k: float
    precision_at_k: float
    mean_reciprocal_rank: float
    unauthorized_retrieval_rate: float
