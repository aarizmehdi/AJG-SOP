from packages.contracts.canonical import (
    CanonicalListItem,
    CanonicalTable,
    CanonicalTableCell,
    SourceLocator,
)
from services.ingestion.chunking.semantic_chunker import (
    SemanticChunker,
    serialize_list,
    serialize_table,
)


def test_table_semantic_serialization():
    # Scenario 4: Table question retrieval
    dummy_source = SourceLocator(source_document_id="doc1")
    table = CanonicalTable(
        caption="Godown Capacity",
        cells=[
            CanonicalTableCell(row=0, column=0, text="", is_header=True, source=dummy_source),
            CanonicalTableCell(
                row=0, column=1, text="Material Capacity", is_header=True, source=dummy_source
            ),  # noqa: E501
            CanonicalTableCell(row=1, column=0, text="Godown", is_header=True, source=dummy_source),
            CanonicalTableCell(
                row=1, column=1, text="500 MT", is_header=False, source=dummy_source
            ),  # noqa: E501
        ],
        source=dummy_source,
    )
    lines = serialize_table(table)
    assert "**Godown Capacity**" in lines
    assert "|  | Material Capacity |" in lines
    assert "|---|---|" in lines
    assert "| Godown | 500 MT |" in lines


def test_table_split_repeats_headers():
    chunker = SemanticChunker()
    chunker.MAX_WORDS = 10  # Force split quickly

    dummy_source = SourceLocator(source_document_id="doc1")
    table = CanonicalTable(
        caption="Large Table",
        cells=[
            CanonicalTableCell(
                row=0, column=0, text="Header A", is_header=True, source=dummy_source
            ),
            CanonicalTableCell(
                row=0, column=1, text="Header B", is_header=True, source=dummy_source
            ),
            CanonicalTableCell(
                row=1,
                column=0,
                text="Row 1 Data A with many words here",
                is_header=False,
                source=dummy_source,
            ),
            CanonicalTableCell(
                row=1,
                column=1,
                text="Row 1 Data B with many words here",
                is_header=False,
                source=dummy_source,
            ),
            CanonicalTableCell(
                row=2,
                column=0,
                text="Row 2 Data A with many words here",
                is_header=False,
                source=dummy_source,
            ),
            CanonicalTableCell(
                row=2,
                column=1,
                text="Row 2 Data B with many words here",
                is_header=False,
                source=dummy_source,
            ),
        ],
        source=dummy_source,
    )

    from packages.contracts.access import AccessDimension
    from packages.contracts.canonical import (
        AccessScope,
        BlockKind,
        CanonicalBlock,
        CanonicalSection,
        CanonicalSOP,
    )

    doc = CanonicalSOP(
        id="sop1",
        organization_id="org1",
        policy_id="pol1",
        version_id="v1",
        source_document_ids=["doc1"],
        title="Test SOP",
        sections=[
            CanonicalSection(
                id="sec1",
                heading="H1",
                heading_level=1,
                heading_path=["H1"],
                stable_key="sec1-key",
                content_hash="sec1-hash",
                blocks=[
                    CanonicalBlock(
                        id="b1", kind=BlockKind.TABLE, text=None, table=table, source=dummy_source
                    )
                ],
                source=dummy_source,
                access=AccessScope(
                    departments=AccessDimension(mode="all", values=frozenset()),
                    locations=AccessDimension(mode="all", values=frozenset()),
                    roles=AccessDimension(mode="all", values=frozenset()),
                ),
            )
        ],
    )

    chunks = chunker.chunk(doc, "published")
    assert len(chunks) == 2
    # Verify header is in both chunks
    assert "**Large Table**" in chunks[0].text
    assert "| Header A | Header B |" in chunks[0].text
    assert "Row 1 Data" in chunks[0].text

    assert "**Large Table**" in chunks[1].text
    assert "| Header A | Header B |" in chunks[1].text
    assert "Row 2 Data" in chunks[1].text


def test_nested_list_serialization():
    # Scenario 5: Nested-list hierarchy question
    dummy_source = SourceLocator(source_document_id="doc1")
    items = [
        CanonicalListItem(
            text="Step 1",
            children=[CanonicalListItem(text="Substep A", children=[], source=dummy_source)],
            source=dummy_source,
        )
    ]
    lines = serialize_list(items)
    assert "Step 1" in lines
    assert "Step 1 > Substep A" in lines


def test_long_section_chunking():
    chunker = SemanticChunker()
    # Test line splitting
    long_line = "word " * (SemanticChunker.MAX_WORDS + 10)
    lines = f"Line 1\n{long_line}\nLine 3"

    from packages.contracts.access import AccessDimension
    from packages.contracts.canonical import (
        AccessScope,
        BlockKind,
        CanonicalBlock,
        CanonicalSection,
        CanonicalSOP,
        SourceLocator,
    )

    dummy_source = SourceLocator(source_document_id="doc1")
    doc = CanonicalSOP(
        id="sop1",
        organization_id="org1",
        policy_id="pol1",
        version_id="v1",
        source_document_ids=["doc1"],
        title="Test SOP",
        sections=[
            CanonicalSection(
                id="sec1",
                heading="H1",
                heading_level=1,
                heading_path=["H1"],
                stable_key="sec1-key",
                content_hash="sec1-hash",
                blocks=[
                    CanonicalBlock(
                        id="b1", kind=BlockKind.PARAGRAPH, text=lines, source=dummy_source
                    )
                ],
                source=dummy_source,
                access=AccessScope(
                    departments=AccessDimension(mode="all", values=frozenset()),
                    locations=AccessDimension(mode="all", values=frozenset()),
                    roles=AccessDimension(mode="all", values=frozenset()),
                ),
            )
        ],
    )

    chunks = chunker.chunk(doc, "published")
    assert len(chunks) > 1
    assert "Line 1" in chunks[0].text
    assert "Line 3" in chunks[-1].text
