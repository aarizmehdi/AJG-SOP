from packages.contracts.source import ParserCapability, SourceDocument, SourceFormat
from services.ingestion.extractors.base import (
    DocumentParser,
    ParserUnavailableError,
    RawDocumentResult,
)


class ParserRouter(DocumentParser):
    """Routes formats without allowing provider contracts into application code."""

    def __init__(self, parsers: list[DocumentParser]) -> None:
        if not parsers:
            raise ValueError("At least one parser must be configured")
        self._parsers = parsers

    def capabilities(self, organization_id: str) -> list[ParserCapability]:
        capabilities = [
            item
            for parser in self._parsers
            for item in parser.capabilities(organization_id)
        ]
        result: list[ParserCapability] = []
        for source_format in SourceFormat:
            selected = next(
                (
                    item
                    for item in capabilities
                    if item.source_format is source_format and item.available
                ),
                None,
            )
            if selected:
                result.append(selected)
                continue
            details = [
                item.detail for item in capabilities if item.source_format is source_format
            ]
            result.append(
                ParserCapability(
                    organization_id=organization_id,
                    provider="unavailable",
                    source_format=source_format,
                    available=False,
                    detail="; ".join(dict.fromkeys(details)),
                )
            )
        return result

    async def parse(self, source: SourceDocument, content: bytes) -> RawDocumentResult:
        for parser in self._parsers:
            if parser.supports(source.source_format, source.organization_id):
                return await parser.parse(source, content)
        raise ParserUnavailableError(
            f"No configured parser can process {source.source_format.value}"
        )
