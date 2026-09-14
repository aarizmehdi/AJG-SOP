from datetime import datetime
from enum import StrEnum

from pydantic import Field

from packages.contracts.common import OrganizationOwned, utc_now


class SourceFormat(StrEnum):
    PDF = "pdf"
    SCANNED_PDF = "scanned_pdf"
    IMAGE = "image"
    DOCX = "docx"
    XLSX = "xlsx"
    MARKDOWN = "markdown"
    STRUCTURED_TEXT = "structured_text"


class SourceStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    FAILED = "failed"


class SourceDocument(OrganizationOwned):
    id: str
    policy_id: str
    version_id: str
    file_name: str
    media_type: str
    source_format: SourceFormat
    sha256: str
    original_artifact_uri: str
    status: SourceStatus = SourceStatus.UPLOADED
    parser_provider: str | None = None
    parser_version: str | None = None
    raw_artifact_uri: str | None = None
    canonical_artifact_uri: str | None = None
    reviewed_artifact_uri: str | None = None
    error_code: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class ParserCapability(OrganizationOwned):
    provider: str
    source_format: SourceFormat
    available: bool
    provisional: bool = True
    detail: str
