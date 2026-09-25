from abc import ABC, abstractmethod
from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from packages.contracts.canonical import BoundingBox
from packages.contracts.source import ParserCapability, SourceDocument, SourceFormat


class RawBlockKind(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"


class RawTableCell(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row: int
    column: int
    text: str
    row_span: int = 1
    column_span: int = 1
    is_header: bool = False
    sheet_name: str | None = None
    cell_reference: str | None = None
    page: int | None = None
    bounding_boxes: tuple[BoundingBox, ...] = ()
    text_start: int | None = None
    text_end: int | None = None


class RawBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: RawBlockKind
    text: str = ""
    level: int | None = None
    marker: str | None = None
    page: int | None = None
    bounding_boxes: tuple[BoundingBox, ...] = ()
    sheet_name: str | None = None
    cell_range: str | None = None
    block_anchor: str | None = None
    text_start: int | None = None
    text_end: int | None = None
    table_cells: list[RawTableCell] = Field(default_factory=list)


class RawDocumentResult(BaseModel):
    """Application-owned raw contract; provider-native payloads are stored separately."""

    model_config = ConfigDict(extra="forbid")
    organization_id: str
    provider: str
    provider_version: str
    source_document_id: str
    title: str
    policy_number: str | None = None
    effective_date: date | None = None
    blocks: list[RawBlock]
    warnings: list[str] = Field(default_factory=list)
    provider_artifact_uri: str | None = None
    # Opaque provider data is moved to an immutable artifact before this normalized
    # result is retained. Downstream code never reads this provider-specific schema.
    provider_payload: dict[str, Any] | None = None


class ParserUnavailableError(RuntimeError):
    pass


class DocumentParser(ABC):
    @abstractmethod
    def capabilities(self, organization_id: str) -> list[ParserCapability]:
        raise NotImplementedError

    @abstractmethod
    async def parse(self, source: SourceDocument, content: bytes) -> RawDocumentResult:
        raise NotImplementedError

    def supports(self, source_format: SourceFormat, organization_id: str) -> bool:
        return any(
            capability.source_format is source_format and capability.available
            for capability in self.capabilities(organization_id)
        )
