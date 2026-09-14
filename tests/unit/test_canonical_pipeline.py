from packages.contracts.source import SourceDocument, SourceFormat
from services.ingestion.extractors.fixtures import FixtureDocumentParser
from services.ingestion.structure.canonical_document import Canonicalizer


async def test_markdown_preserves_heading_list_and_source_anchor() -> None:
    source = SourceDocument(
        id="source-1",
        organization_id="ajt",
        policy_id="policy-1",
        version_id="version-1",
        file_name="fixture.md",
        media_type="text/markdown",
        source_format=SourceFormat.MARKDOWN,
        sha256="abc",
        original_artifact_uri="local://ajt/source",
    )
    raw = await FixtureDocumentParser().parse(
        source,
        b"# Store Operations\n## 4.3 Damaged Stock\n1. Isolate the item\n2. Record damage",
    )
    canonical = Canonicalizer().canonicalize(source, raw)

    damaged = next(section for section in canonical.sections if "Damaged" in section.heading)
    assert damaged.heading_level == 2
    assert damaged.heading_path == ("Store Operations", "4.3 Damaged Stock")
    assert damaged.policy_number == "4.3"
    assert damaged.blocks[0].list_items[0].source.block_anchor == "line-3"


async def test_xlsx_preserves_sheet_and_cell_coordinates() -> None:
    import io

    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Approval Limits"
    sheet.append(["Role", "Limit"])
    sheet.append(["Manager", 5000])
    content = io.BytesIO()
    workbook.save(content)
    source = SourceDocument(
        id="source-2",
        organization_id="ajt",
        policy_id="policy-1",
        version_id="version-1",
        file_name="limits.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        source_format=SourceFormat.XLSX,
        sha256="def",
        original_artifact_uri="local://ajt/source",
    )
    raw = await FixtureDocumentParser().parse(source, content.getvalue())
    canonical = Canonicalizer().canonicalize(source, raw)
    table = canonical.sections[0].blocks[0].table
    assert table is not None
    cell = table.cells[0]

    assert cell.source.sheet_name == "Approval Limits"
    assert cell.source.cell_range == "A1"
