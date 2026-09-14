from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from packages.contracts.canonical import SourceLocator
from packages.contracts.common import Language, OrganizationOwned


class CandidateChannel(StrEnum):
    SEMANTIC = "semantic"
    LEXICAL = "lexical"


class RetrievalCandidate(OrganizationOwned):
    chunk_id: str
    channel: CandidateChannel
    score: float
    rank: int = Field(ge=1)


class SearchEvidence(OrganizationOwned):
    chunk_id: str
    policy_id: str
    version_id: str
    section_id: str
    policy_title: str
    heading_path: tuple[str, ...]
    policy_number: str | None = None
    excerpt: str
    source: SourceLocator
    fused_score: float


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=2, max_length=500)
    language: Language = Language.ENGLISH
    limit: int = Field(default=8, ge=1, le=20)


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    results: list[SearchEvidence]
    query: str
    language: Language


class PolicyReaderSection(OrganizationOwned):
    policy_id: str
    version_id: str
    section_id: str
    heading: str
    heading_path: tuple[str, ...]
    policy_number: str | None = None
    content: str
    source: SourceLocator


class PolicyReaderDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy_id: str
    title: str
    category: str
    version_label: str
    sections: list[PolicyReaderSection]
    original_download_allowed: bool
