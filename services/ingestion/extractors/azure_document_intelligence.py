import asyncio
import re
from typing import Any

import httpx

from packages.contracts.canonical import BoundingBox
from packages.contracts.source import ParserCapability, SourceDocument, SourceFormat
from services.ingestion.extractors.base import (
    DocumentParser,
    ParserUnavailableError,
    RawBlock,
    RawBlockKind,
    RawDocumentResult,
    RawTableCell,
)


class AzureDocumentIntelligenceParser(DocumentParser):
    """Live Azure adapter; provider JSON is normalized before leaving this module."""

    _supported = {SourceFormat.PDF, SourceFormat.SCANNED_PDF, SourceFormat.IMAGE}

    def __init__(self, endpoint: str | None, api_key: str | None) -> None:
        self._endpoint = endpoint.rstrip("/") if endpoint else None
        self._api_key = api_key

    def capabilities(self, organization_id: str) -> list[ParserCapability]:
        configured = bool(self._endpoint and self._api_key)
        return [
            ParserCapability(
                organization_id=organization_id,
                provider="azure_document_intelligence",
                source_format=source_format,
                available=configured and source_format in self._supported,
                detail=(
                    "Configured with prebuilt-layout 2024-11-30; accuracy is provisional"
                    if configured and source_format in self._supported
                    else "Azure credentials are unavailable or this format uses another parser"
                ),
            )
            for source_format in SourceFormat
        ]

    async def parse(self, source: SourceDocument, content: bytes) -> RawDocumentResult:
        if not self._endpoint or not self._api_key or source.source_format not in self._supported:
            raise ParserUnavailableError("Azure Document Intelligence is not configured")
        url = (
            f"{self._endpoint}/documentintelligence/documentModels/"
            "prebuilt-layout:analyze?api-version=2024-11-30"
        )
        headers = {
            "Ocp-Apim-Subscription-Key": self._api_key,
            "Content-Type": source.media_type or "application/octet-stream",
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                submitted = await client.post(url, headers=headers, content=content)
                submitted.raise_for_status()
                operation_url = submitted.headers["operation-location"]
                payload = await self._poll(client, operation_url, headers)
        except (httpx.HTTPError, KeyError) as error:
            raise ParserUnavailableError("Azure document analysis failed") from error
        return self._normalize(source, payload)

    @staticmethod
    async def _poll(
        client: httpx.AsyncClient, operation_url: str, headers: dict[str, str]
    ) -> dict[str, Any]:
        for _ in range(90):
            response = await client.get(operation_url, headers=headers)
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
            state = str(payload.get("status", "")).lower()
            if state == "succeeded":
                return payload
            if state in {"failed", "canceled"}:
                raise ParserUnavailableError("Azure document analysis did not complete")
            await asyncio.sleep(1)
        raise ParserUnavailableError("Azure document analysis timed out")

    @classmethod
    def _normalize(cls, source: SourceDocument, payload: dict[str, Any]) -> RawDocumentResult:
        result = payload.get("analyzeResult", {})
        if not isinstance(result, dict):
            raise ParserUnavailableError("Azure returned an invalid analysis result")
        pages = {
            int(page.get("pageNumber", 0)): (
                float(page.get("width", 1) or 1),
                float(page.get("height", 1) or 1),
            )
            for page in result.get("pages", [])
            if isinstance(page, dict)
        }
        ordered: list[tuple[int, RawBlock]] = []
        title = source.file_name.rsplit(".", 1)[0]
        for index, paragraph in enumerate(result.get("paragraphs", [])):
            if not isinstance(paragraph, dict):
                continue
            text = str(paragraph.get("content", "")).strip()
            if not text:
                continue
            role = str(paragraph.get("role", ""))
            if role == "title" and title == source.file_name.rsplit(".", 1)[0]:
                title = text
            kind = (
                RawBlockKind.HEADING
                if role in {"title", "sectionHeading"}
                else RawBlockKind.PARAGRAPH
            )
            list_match = re.match(r"^((?:\d+[.)])|[-*•])\s+(.+)$", text)
            if list_match and kind is RawBlockKind.PARAGRAPH:
                kind = RawBlockKind.LIST_ITEM
                marker = list_match.group(1)
                text = list_match.group(2)
            else:
                marker = None
            start, end = cls._span(paragraph)
            page, boxes = cls._location(paragraph, pages)
            ordered.append(
                (
                    start if start is not None else 1_000_000 + index,
                    RawBlock(
                        kind=kind,
                        text=text,
                        level=1 if role == "title" else (2 if role == "sectionHeading" else None),
                        marker=marker,
                        page=page,
                        bounding_boxes=boxes,
                        text_start=start,
                        text_end=end,
                        block_anchor=f"azure-paragraph-{index + 1}",
                    ),
                )
            )
        for table_index, table in enumerate(result.get("tables", [])):
            if not isinstance(table, dict):
                continue
            start, end = cls._span(table)
            page, boxes = cls._location(table, pages)
            cells: list[RawTableCell] = []
            for cell in table.get("cells", []):
                if not isinstance(cell, dict):
                    continue
                cell_start, cell_end = cls._span(cell)
                cell_page, cell_boxes = cls._location(cell, pages)
                cells.append(
                    RawTableCell(
                        row=int(cell.get("rowIndex", 0)),
                        column=int(cell.get("columnIndex", 0)),
                        row_span=int(cell.get("rowSpan", 1)),
                        column_span=int(cell.get("columnSpan", 1)),
                        text=str(cell.get("content", "")),
                        is_header=str(cell.get("kind", "")) in {"columnHeader", "rowHeader"},
                        page=cell_page,
                        bounding_boxes=cell_boxes,
                        text_start=cell_start,
                        text_end=cell_end,
                    )
                )
            ordered.append(
                (
                    start if start is not None else 2_000_000 + table_index,
                    RawBlock(
                        kind=RawBlockKind.TABLE,
                        page=page,
                        bounding_boxes=boxes,
                        text_start=start,
                        text_end=end,
                        block_anchor=f"azure-table-{table_index + 1}",
                        table_cells=cells,
                    ),
                )
            )
        ordered.sort(key=lambda item: item[0])
        return RawDocumentResult(
            organization_id=source.organization_id,
            provider="azure_document_intelligence",
            provider_version=str(result.get("apiVersion", "2024-11-30")),
            source_document_id=source.id,
            title=title,
            blocks=[block for _, block in ordered],
            warnings=["Extraction accuracy requires human review and real-SOP benchmarking"],
            provider_payload=payload,
        )

    @staticmethod
    def _span(item: dict[str, Any]) -> tuple[int | None, int | None]:
        spans = item.get("spans") or []
        if not spans or not isinstance(spans[0], dict):
            return None, None
        start = int(spans[0].get("offset", 0))
        return start, start + int(spans[0].get("length", 0))

    @staticmethod
    def _location(
        item: dict[str, Any], pages: dict[int, tuple[float, float]]
    ) -> tuple[int | None, tuple[BoundingBox, ...]]:
        regions = item.get("boundingRegions") or []
        if not regions or not isinstance(regions[0], dict):
            return None, ()
        region = regions[0]
        page = int(region.get("pageNumber", 0)) or None
        polygon = region.get("polygon") or []
        if page is None or len(polygon) < 8:
            return page, ()
        width, height = pages.get(page, (1.0, 1.0))
        x_values = [float(value) for value in polygon[0::2]]
        y_values = [float(value) for value in polygon[1::2]]
        left, right = min(x_values), max(x_values)
        top, bottom = min(y_values), max(y_values)
        return page, (
            BoundingBox(
                x=left / width,
                y=top / height,
                width=(right - left) / width,
                height=(bottom - top) / height,
            ),
        )
