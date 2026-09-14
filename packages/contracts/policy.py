from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from packages.contracts.access import AccessScope
from packages.contracts.common import OrganizationOwned, utc_now


class PolicyStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"


class VersionStatus(StrEnum):
    DRAFT = "draft"
    EXTRACTION_REVIEW = "extraction_review"
    READY_FOR_INDEXING = "ready_for_indexing"
    INDEXING = "indexing"
    READY_TO_PUBLISH = "ready_to_publish"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"
    FAILED = "failed"


class IngestionState(StrEnum):
    UPLOADED = "uploaded"
    EXTRACTING = "extracting"
    STRUCTURING = "structuring"
    REVIEW_REQUIRED = "review_required"
    STRUCTURE_APPROVED = "structure_approved"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    VERIFYING = "verifying"
    READY_FOR_REVIEW = "ready_for_review"
    PUBLISHED = "published"
    FAILED = "failed"


class IngestionEvent(OrganizationOwned):
    state: IngestionState
    occurred_at: datetime = Field(default_factory=utc_now)
    detail: str


class IngestionJob(OrganizationOwned):
    id: str
    source_document_id: str
    version_id: str
    state: IngestionState
    events: list[IngestionEvent]
    retry_count: int = Field(default=0, ge=0)
    error_code: str | None = None


class SOPPolicy(OrganizationOwned):
    id: str
    title: str
    category: str
    policy_number: str | None = None
    status: PolicyStatus = PolicyStatus.DRAFT
    active_version_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SOPVersion(OrganizationOwned):
    id: str
    policy_id: str
    version_label: str
    effective_date: date | None = None
    status: VersionStatus = VersionStatus.DRAFT
    access: AccessScope
    source_document_ids: list[str] = Field(default_factory=list)
    canonical_document_ids: list[str] = Field(default_factory=list)
    index_revision: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    published_at: datetime | None = None


class SectionChangeKind(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"


class SectionChange(OrganizationOwned):
    kind: SectionChangeKind
    stable_key: str
    heading: str
    old_content: str | None = None
    new_content: str | None = None
    access_changed: bool = False


class DuplicateSectionOccurrence(BaseModel):
    source_document_id: str
    section_id: str
    heading: str


class DuplicateSectionGroup(OrganizationOwned):
    content_hash: str
    occurrences: list[DuplicateSectionOccurrence]


class AuditEvent(OrganizationOwned):
    id: str
    actor_id: str
    action: str
    entity_type: str
    entity_id: str
    occurred_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, str] = Field(default_factory=dict)
