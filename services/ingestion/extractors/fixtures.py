import io
import re

from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader

from packages.contracts.source import ParserCapability, SourceDocument, SourceFormat
from services.ingestion.extractors.base import (
    DocumentParser,
    ParserUnavailableError,
    RawBlock,
    RawBlockKind,
    RawDocumentResult,
    RawTableCell,
)


class FixtureDocumentParser(DocumentParser):
    """Deterministic local parser for architecture tests; quality is not production-validated."""

    _supported = {
        SourceFormat.PDF,
        SourceFormat.DOCX,
        SourceFormat.XLSX,
        SourceFormat.MARKDOWN,
        SourceFormat.STRUCTURED_TEXT,
    }

    def capabilities(self, organization_id: str) -> list[ParserCapability]:
        return [
            ParserCapability(
                organization_id=organization_id,
                provider="fixture",
                source_format=source_format,
                available=source_format in self._supported,
                detail=(
                    "Deterministic local extraction; requires human review"
                    if source_format in self._supported
                    else "Requires a configured OCR-capable provider"
                ),
            )
            for source_format in SourceFormat
        ]

    async def parse(self, source: SourceDocument, content: bytes) -> RawDocumentResult:
        parsers = {
            SourceFormat.PDF: self._parse_pdf,
            SourceFormat.DOCX: self._parse_docx,
            SourceFormat.XLSX: self._parse_xlsx,
            SourceFormat.MARKDOWN: self._parse_text,
            SourceFormat.STRUCTURED_TEXT: self._parse_text,
        }
        parser = parsers.get(source.source_format)
        if parser is None:
            raise ParserUnavailableError(
                f"Fixture parser cannot OCR {source.source_format.value}; "
                "configure Azure or Docling"
            )
        blocks, warnings = parser(content)
        return RawDocumentResult(
            organization_id=source.organization_id,
            provider="fixture",
            provider_version="1",
            source_document_id=source.id,
            title=source.file_name.rsplit(".", 1)[0],
            blocks=blocks,
            warnings=warnings,
        )

    @staticmethod
    def _parse_text(content: bytes) -> tuple[list[RawBlock], list[str]]:
        blocks: list[RawBlock] = []
        for index, line in enumerate(content.decode("utf-8").splitlines()):
            stripped = line.strip()
            if not stripped:
                continue
            heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            list_item = re.match(r"^((?:\d+[.)])|[-*])\s+(.+)$", stripped)
            if heading:
                blocks.append(
                    RawBlock(
                        kind=RawBlockKind.HEADING,
                        text=heading.group(2),
                        level=len(heading.group(1)),
                        block_anchor=f"line-{index + 1}",
                    )
                )
            elif list_item:
                marker = list_item.group(1)
                blocks.append(
                    RawBlock(
                        kind=RawBlockKind.LIST_ITEM,
                        text=list_item.group(2),
                        marker=marker,
                        level=max(0, (len(line) - len(line.lstrip())) // 2),
                        block_anchor=f"line-{index + 1}",
                    )
                )
            else:
                blocks.append(
                    RawBlock(
                        kind=RawBlockKind.PARAGRAPH,
                        text=stripped,
                        block_anchor=f"line-{index + 1}",
                    )
                )
        return blocks, []

    @staticmethod
    def _parse_pdf(content: bytes) -> tuple[list[RawBlock], list[str]]:
        reader = PdfReader(io.BytesIO(content))
        blocks: list[RawBlock] = []
        warnings: list[str] = []
        for page_index, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if not text:
                warnings.append(f"Page {page_index} contains no native text and requires OCR")
                continue
            blocks.extend(
                RawBlock(kind=RawBlockKind.PARAGRAPH, text=line, page=page_index)
                for line in text.splitlines()
                if line.strip()
            )
        return blocks, warnings

    @staticmethod
    def _parse_docx(content: bytes) -> tuple[list[RawBlock], list[str]]:
        document = Document(io.BytesIO(content))
        blocks: list[RawBlock] = []
        for index, paragraph in enumerate(document.paragraphs):
            text = paragraph.text.strip()
            if not text:
                continue
            style = paragraph.style.name if paragraph.style else ""
            match = re.match(r"Heading\s+(\d+)", style)
            kind = RawBlockKind.HEADING if match else RawBlockKind.PARAGRAPH
            blocks.append(
                RawBlock(
                    kind=kind,
                    text=text,
                    level=int(match.group(1)) if match else None,
                    block_anchor=f"paragraph-{index + 1}",
                )
            )
        for table_index, table in enumerate(document.tables):
            cells = [
                RawTableCell(
                    row=row_index,
                    column=column_index,
                    text=cell.text.strip(),
                    is_header=row_index == 0,
                )
                for row_index, row in enumerate(table.rows)
                for column_index, cell in enumerate(row.cells)
            ]
            blocks.append(
                RawBlock(
                    kind=RawBlockKind.TABLE,
                    table_cells=cells,
                    block_anchor=f"table-{table_index + 1}",
                )
            )
        return blocks, []

    @staticmethod
    def _parse_xlsx(content: bytes) -> tuple[list[RawBlock], list[str]]:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=False)
        blocks: list[RawBlock] = []
        for sheet in workbook.worksheets:
            cells = [
                RawTableCell(
                    row=cell.row - 1,
                    column=cell.column - 1,
                    text=str(cell.value) if cell.value is not None else "",
                    is_header=cell.row == 1,
                    sheet_name=sheet.title,
                    cell_reference=cell.coordinate,
                )
                for row in sheet.iter_rows()
                for cell in row
                if cell.value is not None
            ]
            if cells:
                blocks.append(
                    RawBlock(
                        kind=RawBlockKind.TABLE,
                        table_cells=cells,
                        sheet_name=sheet.title,
                        cell_range=sheet.calculate_dimension(),
                    )
                )
        return blocks, []
