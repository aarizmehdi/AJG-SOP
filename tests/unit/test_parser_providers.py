from packages.contracts.source import SourceDocument, SourceFormat
from services.ingestion.extractors.azure_document_intelligence import (
    AzureDocumentIntelligenceParser,
)
from services.ingestion.extractors.fixtures import FixtureDocumentParser
from services.ingestion.extractors.router import ParserRouter


def source(source_format: SourceFormat = SourceFormat.SCANNED_PDF) -> SourceDocument:
    return SourceDocument(
        id="source-1",
        organization_id="ajt",
        policy_id="policy-1",
        version_id="version-1",
        file_name="policy.pdf",
        media_type="application/pdf",
        source_format=source_format,
        sha256="abc",
        original_artifact_uri="local://ajt/policy.pdf",
    )


def test_router_reports_every_source_format_and_explicit_availability() -> None:
    router = ParserRouter([FixtureDocumentParser()])

    capabilities = router.capabilities("ajt")

    assert {item.source_format for item in capabilities} == set(SourceFormat)
    assert next(
        item for item in capabilities if item.source_format is SourceFormat.IMAGE
    ).available is False
    assert next(
        item for item in capabilities if item.source_format is SourceFormat.XLSX
    ).available is True


def test_azure_normalization_preserves_native_payload_spans_and_coordinates() -> None:
    payload = {
        "status": "succeeded",
        "analyzeResult": {
            "apiVersion": "2024-11-30",
            "pages": [{"pageNumber": 1, "width": 10, "height": 20}],
            "paragraphs": [
                {
                    "role": "sectionHeading",
                    "content": "4.3 Damaged Stock",
                    "spans": [{"offset": 10, "length": 17}],
                    "boundingRegions": [
                        {"pageNumber": 1, "polygon": [1, 2, 9, 2, 9, 4, 1, 4]}
                    ],
                }
            ],
            "tables": [
                {
                    "spans": [{"offset": 30, "length": 8}],
                    "boundingRegions": [
                        {"pageNumber": 1, "polygon": [1, 5, 9, 5, 9, 10, 1, 10]}
                    ],
                    "cells": [
                        {
                            "rowIndex": 0,
                            "columnIndex": 0,
                            "content": "Role",
                            "kind": "columnHeader",
                            "spans": [{"offset": 30, "length": 4}],
                            "boundingRegions": [
                                {
                                    "pageNumber": 1,
                                    "polygon": [1, 5, 5, 5, 5, 7, 1, 7],
                                }
                            ],
                        }
                    ],
                }
            ],
        },
    }

    raw = AzureDocumentIntelligenceParser._normalize(source(), payload)

    assert raw.organization_id == "ajt"
    assert raw.provider_payload == payload
    assert raw.blocks[0].text_start == 10
    assert raw.blocks[0].bounding_boxes[0].x == 0.1
    assert raw.blocks[1].table_cells[0].text_end == 34
