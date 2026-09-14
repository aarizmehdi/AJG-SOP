from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.contracts.access import AccessScope
from packages.contracts.common import OrganizationOwned, utc_now


class BlockKind(StrEnum):
    PARAGRAPH = "paragraph"
    ORDERED_LIST = "ordered_list"
    UNORDERED_LIST = "unordered_list"
    TABLE = "table"


class BoundingBox(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    x: float
    y: float
    width: float
    height: float
    unit: str = "normalized"


class SourceLocator(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_document_id: str
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    bounding_boxes: tuple[BoundingBox, ...] = ()
    text_start: int | None = Field(default=None, ge=0)
    text_end: int | None = Field(default=None, ge=0)
    sheet_name: str | None = None
    cell_range: str | None = None
    block_anchor: str | None = None

    @model_validator(mode="after")
    def validate_location(self) -> "SourceLocator":
        if self.page_start and self.page_end and self.page_end < self.page_start:
            raise ValueError("Page end cannot precede page start")
        return self


class CanonicalListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    level: int = Field(default=0, ge=0)
    marker: str | None = None
    children: list["CanonicalListItem"] = Field(default_factory=list)
    source: SourceLocator


class CanonicalTableCell(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row: int = Field(ge=0)
    column: int = Field(ge=0)
    text: str
    row_span: int = Field(default=1, ge=1)
    column_span: int = Field(default=1, ge=1)
    is_header: bool = False
    source: SourceLocator


class CanonicalTable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    caption: str | None = None
    cells: list[CanonicalTableCell]
    source: SourceLocator


class CanonicalBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: BlockKind
    text: str | None = None
    list_items: list[CanonicalListItem] = Field(default_factory=list)
    table: CanonicalTable | None = None
    source: SourceLocator


class CanonicalSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    stable_key: str
    policy_number: str | None = None
    chapter: str | None = None
    heading: str
    heading_level: int = Field(ge=1)
    parent_section_id: str | None = None
    heading_path: tuple[str, ...]
    blocks: list[CanonicalBlock]
    access: AccessScope
    source: SourceLocator
    content_hash: str


class ReviewRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    reviewer_id: str
    note: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class CanonicalSOP(OrganizationOwned):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "1.0"
    id: str
    policy_id: str
    version_id: str
    source_document_ids: tuple[str, ...]
    title: str
    policy_number: str | None = None
    sections: list[CanonicalSection]
    review_revisions: list[ReviewRevision] = Field(default_factory=list)
    approved: bool = False
    approved_at: datetime | None = None


class RetrievalChunk(OrganizationOwned):
    id: str
    policy_id: str
    version_id: str
    source_document_id: str
    section_id: str
    parent_section_id: str | None = None
    heading_path: tuple[str, ...]
    policy_number: str | None = None
    text: str
    access: AccessScope
    source: SourceLocator
    chunk_index: int = Field(ge=0)
    publication_status: str
