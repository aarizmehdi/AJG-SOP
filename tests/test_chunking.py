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

    concatenated = " ".join(c.text for c in chunks)
    for word in long_line.split():
        assert word in concatenated


def test_chunk_metadata_and_id_stability():
    chunker = SemanticChunker()
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
    scope = AccessScope(
        departments=AccessDimension(mode="all", values=frozenset()),
        locations=AccessDimension(mode="all", values=frozenset()),
        roles=AccessDimension(mode="selected", values=frozenset({"role1"})),
    )
    doc = CanonicalSOP(
        id="sop1",
        organization_id="org1",
        policy_id="pol1",
        version_id="v1",
        policy_number="SOP-123",
        source_document_ids=["doc1"],
        title="Test SOP",
        sections=[
            CanonicalSection(
                id="sec1",
                heading="H1",
                heading_level=1,
                heading_path=("Policy Title", "H1"),
                stable_key="sec1-key",
                content_hash="sec1-hash",
                policy_number="SOP-123",
                blocks=[
                    CanonicalBlock(
                        id="b1", kind=BlockKind.PARAGRAPH, text="Block content", source=dummy_source
                    )
                ],
                source=dummy_source,
                access=scope,
            )
        ],
    )

    chunks_first = chunker.chunk(doc, "published")
    chunks_second = chunker.chunk(doc, "published")

    assert len(chunks_first) == len(chunks_second) == 1

    # Assert ID stability
    assert chunks_first[0].id == chunks_second[0].id

    # Assert metadata retained
    assert chunks_first[0].policy_number == "SOP-123"
    assert chunks_first[0].heading_path == ("Policy Title", "H1")
    assert chunks_first[0].access == scope


def test_late_chunk_answer_retrieval():
    chunker = SemanticChunker()
    chunker.MAX_WORDS = 10

    from packages.contracts.access import AccessDimension
    from packages.contracts.canonical import (
        AccessScope,
        BlockKind,
        CanonicalBlock,
        CanonicalSection,
        CanonicalSOP,
        SourceLocator,
    )

    dummy_source = SourceLocator(source_document_id="doc1", page_start=2, page_end=3)
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
                heading_path=("H1",),
                stable_key="sec1-key",
                content_hash="sec1-hash",
                blocks=[
                    CanonicalBlock(
                        id="b1",
                        kind=BlockKind.PARAGRAPH,
                        text="Early words that consume space",
                        source=dummy_source,
                    ),
                    CanonicalBlock(
                        id="b2",
                        kind=BlockKind.PARAGRAPH,
                        text="Here is the target fact you seek",
                        source=dummy_source,
                    ),
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

    # The fact should end up in a later chunk, but retain full source/locator context
    assert len(chunks) > 1

    target_chunk = next(c for c in chunks if "target fact" in c.text)
    assert target_chunk.chunk_index > 0
    assert target_chunk.source.page_start == 2
    assert target_chunk.source.page_end == 3
    assert target_chunk.section_id == "sec1"

    # Check ID distinctness
    assert len(set(c.id for c in chunks)) == len(chunks)


def test_safe_index_rebuild_diff_computation():
    from packages.contracts.access import AccessDimension, AccessScope
    from packages.contracts.canonical import (
        CanonicalSection,
        CanonicalSOP,
        SourceLocator,
        CanonicalBlock,
        BlockKind
    )
    from services.ingestion.chunking.semantic_chunker import SectionAwareFixtureChunker

    chunker = SectionAwareFixtureChunker()
    dummy_source = SourceLocator(source_document_id="doc1", page_start=1, page_end=1)
    doc = CanonicalSOP(
        id="doc1",
        organization_id="tenant-1",
        policy_id="pol1",
        version_id="v1",
        source_document_ids=["doc1"],
        title="Test Doc",
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
                        id="b1", kind=BlockKind.PARAGRAPH, text="This is the original text.", source=dummy_source
                    )
                ],
                source=dummy_source,
                access=AccessScope(
                    departments=AccessDimension(mode="all", values=frozenset()),
                    locations=AccessDimension(mode="all", values=frozenset()),
                    roles=AccessDimension(mode="all", values=frozenset()),
                ),
            ),
            CanonicalSection(
                id="sec2",
                heading="H2",
                heading_level=1,
                heading_path=["H2"],
                stable_key="sec2-key",
                content_hash="sec2-hash",
                blocks=[
                    CanonicalBlock(
                        id="b2", kind=BlockKind.PARAGRAPH, text="Section to be deleted.", source=dummy_source
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

    old_chunks = chunker.chunk(doc, "published")
    old_ids = {c.id for c in old_chunks}

    # Simulate re-chunking identically
    new_chunks = chunker.chunk(doc, "published")
    new_ids = {c.id for c in new_chunks}

    assert old_ids == new_ids

    # Simulate content change: remove sec2, add sec3
    doc2 = CanonicalSOP(
        id="doc1",
        organization_id="tenant-1",
        policy_id="pol1",
        version_id="v1",
        source_document_ids=["doc1"],
        title="Test Doc",
        sections=[
            CanonicalSection(
                id="sec1",
                heading="H1",
                heading_level=1,
                heading_path=["H1"],
                stable_key="sec1-key",
                content_hash="sec1-hash-changed",
                blocks=[
                    CanonicalBlock(
                        id="b1", kind=BlockKind.PARAGRAPH, text="This is the new text.", source=dummy_source
                    )
                ],
                source=dummy_source,
                access=AccessScope(
                    departments=AccessDimension(mode="all", values=frozenset()),
                    locations=AccessDimension(mode="all", values=frozenset()),
                    roles=AccessDimension(mode="all", values=frozenset()),
                ),
            ),
            CanonicalSection(
                id="sec3",
                heading="H3",
                heading_level=1,
                heading_path=["H3"],
                stable_key="sec3-key",
                content_hash="sec3-hash",
                blocks=[
                    CanonicalBlock(
                        id="b3", kind=BlockKind.PARAGRAPH, text="A new section.", source=dummy_source
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

    newer_chunks = chunker.chunk(doc2, "published")
    newer_ids = {c.id for c in newer_chunks}
    
    assert old_ids != newer_ids
    # Prove diff computation is possible without Pinecone calls
    to_delete = old_ids - newer_ids
    to_upsert = newer_ids - old_ids
    assert len(to_delete) > 0
    assert len(to_upsert) > 0

