"""Provider-neutral permanent policy deletion contracts."""

from pydantic import BaseModel, ConfigDict, Field


class PurgeCounts(BaseModel):
    mongo: dict[str, int] = Field(default_factory=dict)
    r2_objects: int = 0
    r2_bytes: int = 0
    pinecone_vectors: int = 0


class PurgePreview(BaseModel):
    policy_id: str
    title: str
    published: bool
    counts: PurgeCounts
    preview_token: str
    limitations: list[str]


class PurgeConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    phrase: str
    preview_token: str


class PurgeResult(BaseModel):
    policy_id: str
    status: str
    counts: PurgeCounts
    stages: dict[str, str]
    remaining: dict[str, int]
    error: str | None = None


class PurgeGraph(BaseModel):
    organization_id: str
    policy_id: str
    version_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    canonical_ids: list[str] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    # Exact database row identities; never supplied by the HTTP client.
    records: dict[str, list[dict[str, str | bool]]] = Field(default_factory=dict)
