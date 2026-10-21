"""Synthetic regressions for source-faithful collection ingestion (no private SOPs)."""

from apps.api.app.services.policy_reader_service import PolicyReaderService
from packages.contracts.canonical import BlockKind, SectionContentRole
from packages.contracts.source import SourceDocument, SourceFormat
from services.ingestion.chunking.semantic_chunker import SemanticChunker
from services.ingestion.extractors.base import RawBlock, RawBlockKind, RawDocumentResult
from services.ingestion.extractors.fixtures import FixtureDocumentParser
from services.ingestion.structure.canonical_document import Canonicalizer
from services.ingestion.structure.markdown import canonical_to_markdown


def source() -> SourceDocument:
    return SourceDocument(
        id="synthetic-source",
        organization_id="test-org",
        policy_id="collection",
        version_id="version",
        file_name="collection.md",
        media_type="text/markdown",
        source_format=SourceFormat.MARKDOWN,
        sha256="fixture",
        original_artifact_uri="local://fixture",
    )


async def parse(text: str):
    raw = await FixtureDocumentParser().parse(source(), text.encode())
    return raw, Canonicalizer().canonicalize(source(), raw)


async def test_editorial_comments_excluded_without_moving_original_line_anchors():
    raw, canonical = await parse(
        "# Synthetic collection\n<!-- reviewer: not policy\nSECRET_EDITORIAL -->\n"
        "## SOP #201 Dispatch\n1. Follow the approved order.\n---\n"
        "<!-- inline -->2. Record receipt.\n<!-- NOT_POLICY -->"
    )
    assert [block.block_anchor for block in raw.blocks] == ["line-1", "line-4", "line-5", "line-7"]
    rendered = canonical_to_markdown(canonical)
    assert "SECRET_EDITORIAL" not in rendered
    assert "NOT_POLICY" not in rendered
    assert "<!--" not in rendered
    assert "1. Follow the approved order." in rendered
    assert "2. Record receipt." in rendered


async def test_unclosed_comment_fails_instead_of_silently_dropping_trailing_policy():
    import pytest

    with pytest.raises(ValueError, match="Unclosed Markdown comment"):
        await parse(
            "# Policy\n<!-- unfinished reviewer note\n1. Must not silently lose this clause."
        )


async def test_clause_markers_and_nested_approval_roles_survive_canonical_round_trip():
    _, canonical = await parse(
        "# Synthetic collection\n## SOP #201 Dispatch\n"
        "1. Approval is required.\n  a. First signer\n  b) Second signer\n"
        "2. Check the exceptions.\n  i) Exception one\n  ii) Exception two\n"
        "5.1. Preserve source numbering.\n10) Source skips a number.\n"
        "I am ordinary prose.\n12.30pm is a time.\n"
    )
    section = canonical.sections[0]
    ordered = section.blocks[0]
    assert ordered.kind is BlockKind.ORDERED_LIST
    assert [item.marker for item in ordered.list_items] == ["1.", "2.", "5.1.", "10)"]
    assert [item.marker for item in ordered.list_items[0].children] == ["a.", "b)"]
    assert [item.marker for item in ordered.list_items[1].children] == ["i)", "ii)"]
    assert [b.text for b in section.blocks[1:]] == ["I am ordinary prose.", "12.30pm is a time."]
    rendered = canonical_to_markdown(canonical)
    for marker in ("a.", "b)", "i)", "ii)", "5.1.", "10)"):
        assert marker in rendered


async def test_real_heading_parents_and_policy_numbers_remain_navigable():
    _, canonical = await parse(
        "# Synthetic collection\n## SOP #201 Dispatch\n### Responsibilities\n"
        "1. Keep the register.\n#### Exceptions\nNo unapproved dispatch.\n"
        "## SOP #202 Receipt\n### Responsibilities\n1. Record received goods."
    )
    assert [s.heading for s in canonical.sections] == [
        "SOP #201 Dispatch",
        "Responsibilities",
        "Exceptions",
        "SOP #202 Receipt",
        "Responsibilities",
    ]
    ids = {s.id for s in canonical.sections}
    assert all(
        s.parent_section_id is None or s.parent_section_id in ids for s in canonical.sections
    )
    assert canonical.sections[1].parent_section_id == canonical.sections[0].id
    assert canonical.sections[2].parent_section_id == canonical.sections[1].id
    assert canonical.sections[1].policy_number == "SOP #201"
    assert canonical.sections[-1].policy_number == "SOP #202"
    assert canonical.policy_number is None
    _, reimported = await parse(canonical_to_markdown(canonical))
    assert [(s.heading, s.heading_level) for s in reimported.sections] == [
        (s.heading, s.heading_level) for s in canonical.sections
    ]


async def test_similarly_titled_source_occurrences_keep_distinct_repeatable_keys():
    text = (
        "# Synthetic collection\n## Assistant Officer\n### Duties\n1. First occurrence.\n"
        "## Assistant Officer\n### Duties\n1. Distinct second occurrence."
    )
    _, first = await parse(text)
    _, second = await parse(text)
    assert len({s.stable_key for s in first.sections}) == len(first.sections) == 4
    assert [s.stable_key for s in first.sections] == [s.stable_key for s in second.sections]
    assert first.sections[3].parent_section_id == first.sections[2].id


def test_section_page_range_includes_nested_list_and_table_cell_pages():
    raw = RawDocumentResult(
        organization_id="test-org",
        provider="fixture",
        provider_version="1",
        source_document_id=source().id,
        title="Synthetic",
        blocks=[
            RawBlock(kind=RawBlockKind.HEADING, text="Policy", level=2, page=2),
            RawBlock(kind=RawBlockKind.LIST_ITEM, text="Parent", marker="1.", page=2),
            RawBlock(
                kind=RawBlockKind.LIST_ITEM, text="Continuation", marker="a.", level=1, page=3
            ),
        ],
    )
    section = Canonicalizer().canonicalize(source(), raw).sections[0]
    assert section.source.page_start == 2
    assert section.source.page_end == 3


async def test_reader_keeps_nested_conditions_and_annotations_cannot_be_policy_evidence():
    _, document = await parse(
        "# Synthetic collection\n## SOP #201 Dispatch\n1. Obtain approval.\n"
        "  a. Required signer\n  b. Exception with conditions\n"
        "### Handwritten source annotations — PDF page4\n"
        "Does this change the authorization?\n#### Margin table\n"
        "| Previous | Next |\n|---|---|\n| Material A | Material B |\n"
        "## SOP #202 Receipt\nRecord receipts."
    )
    assert "Required signer" in PolicyReaderService._section_text(document.sections[0])
    assert "Exception with conditions" in PolicyReaderService._section_text(document.sections[0])
    annotations = [
        s for s in document.sections if s.content_role is SectionContentRole.SOURCE_ANNOTATION
    ]
    assert len(annotations) == 2
    rendered = canonical_to_markdown(document)
    assert "Does this change the authorization?" in rendered
    assert "Material B" in rendered
    chunks = SemanticChunker().chunk(document, "staged")
    assert chunks
    assert not {s.id for s in annotations} & {chunk.section_id for chunk in chunks}
    assert "Required signer" in "\n".join(chunk.text for chunk in chunks)
    assert "Material B" not in "\n".join(chunk.text for chunk in chunks)
