"""Machine-readable result models for benchmark runs."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from services.evaluation.models import RetrievalMetrics


class ConfigStatus(StrEnum):
    OK = "ok"
    SKIPPED = "skipped"
    FAILED = "failed"


class AssistantCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observed_kind: str
    error: str | None = None
    answer_chars: int = 0
    cited_sections: list[str] = []
    context_sections: list[str] = []
    unauthorized_context_sections: list[str] = []
    answerability_correct: bool
    clarification_correct: bool
    kind_correct: bool
    citation_correct: bool | None = None
    grounded: bool | None = None
    fact_coverage: float | None = None
    forbidden_fact_leak: bool | None = None
    latency_ms: float = 0.0


class CaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    language: str
    tags: list[str]
    routed_without_retrieval: bool = False
    returned_sections: list[str] = []
    returned_chunk_ids: list[str] = []
    missing_sections: list[str] = []
    unauthorized_sections: list[str] = []
    recall: float | None = None
    reciprocal_rank: float | None = None
    fact_recall: float | None = None
    error: str | None = None
    latency_ms: float = 0.0
    assistant: AssistantCaseResult | None = None


class TagMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cases: int
    recall_at_k: float
    mean_reciprocal_rank: float
    ndcg_at_k: float
    fact_recall_at_k: float | None = None


class AssistantMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cases: int
    answerability_accuracy: float
    clarification_accuracy: float
    clarification_recall: float | None = None
    false_clarification_rate: float
    kind_accuracy: float
    citation_correctness: float | None = None
    grounding_correctness: float | None = None
    fact_coverage: float | None = None
    forbidden_fact_leak_rate: float | None = None
    answered_cases: int = 0
    technical_failure_rate: float = 0.0
    unauthorized_context_count: int = 0
    latency_ms_p50: float = 0.0
    latency_ms_p95: float = 0.0


class CostReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    embedding_model: str = ""
    index_build_seconds: float = 0.0
    query_calls: int = 0
    provider_texts: int = 0
    provider_chars: int = 0
    provider_seconds: float = 0.0
    chunks: int = 0
    chunk_chars: int = 0


class ConfigResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    status: ConfigStatus
    reason: str = ""
    settings: dict[str, object] = {}
    retrieval_by_k: dict[str, RetrievalMetrics] = {}
    by_tag: dict[str, TagMetrics] = {}
    retrieval_technical_failure_rate: float = 0.0
    retrieval_latency_ms_p50: float = 0.0
    retrieval_latency_ms_p95: float = 0.0
    assistant: AssistantMetrics | None = None
    cost: CostReport | None = None
    cases: list[CaseResult] = []


class GateOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")
    passed: bool
    failures: list[str] = []
    unauthorized_retrieval_count: int = 0


class BenchmarkResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "1"
    run_id: str
    created_at: datetime
    git_commit: str | None = None
    dataset: str
    dataset_sha256: str
    corpus_fingerprint: str
    case_count: int
    ks: list[int]
    primary_k: int
    configs: list[ConfigResult] = Field(default_factory=list)
    gate: GateOutcome | None = None
