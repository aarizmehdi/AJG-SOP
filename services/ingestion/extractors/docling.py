from packages.contracts.source import ParserCapability, SourceDocument, SourceFormat
from services.ingestion.extractors.base import (
    DocumentParser,
    ParserUnavailableError,
    RawDocumentResult,
)


class DoclingDocumentParser(DocumentParser):
    """Optional Docling boundary kept out of application contracts until benchmarked."""

    def capabilities(self, organization_id: str) -> list[ParserCapability]:
        return [
            ParserCapability(
                organization_id=organization_id,
                provider="docling",
                source_format=source_format,
                available=False,
                detail="Optional provider is not installed; benchmark after receiving real SOPs",
            )
            for source_format in SourceFormat
        ]

    async def parse(self, source: SourceDocument, content: bytes) -> RawDocumentResult:
        raise ParserUnavailableError("Docling provider is not installed")
