from packages.contracts.access import AccessDimension, AccessMode, AccessScope
from packages.contracts.canonical import (
    BlockKind,
    CanonicalBlock,
    CanonicalListItem,
    CanonicalSection,
    CanonicalSOP,
    CanonicalTable,
    CanonicalTableCell,
    RetrievalChunk,
    SourceLocator,
)
from services.ingestion.chunking.semantic_chunker import (
    SectionAwareFixtureChunker,
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
        BlockKind,
        CanonicalBlock,
        CanonicalSection,
        CanonicalSOP,
        SourceLocator,
    )
    from services.ingestion.chunking.semantic_chunker import SectionAwareFixtureChunker

    chunker = SectionAwareFixtureChunker()
    dummy_source = SourceLocator(source_document_id="doc1", page_start=1, page_end=1)

    scope = AccessScope(
        departments=AccessDimension(mode="all", values=frozenset()),
        locations=AccessDimension(mode="all", values=frozenset()),
        roles=AccessDimension(mode="all", values=frozenset()),
    )

    sec1 = CanonicalSection(
        id="sec1",
        heading="H1",
        heading_level=1,
        heading_path=["H1"],
        stable_key="sec1-key",
        content_hash="hash1",
        blocks=[
            CanonicalBlock(id="b1", kind=BlockKind.PARAGRAPH, text="text1", source=dummy_source)
        ],
        source=dummy_source,
        access=scope,
    )
    sec2 = CanonicalSection(
        id="sec2",
        heading="H2",
        heading_level=1,
        heading_path=["H2"],
        stable_key="sec2-key",
        content_hash="hash2",
        blocks=[
            CanonicalBlock(id="b2", kind=BlockKind.PARAGRAPH, text="text2", source=dummy_source)
        ],
        source=dummy_source,
        access=scope,
    )
    sec3 = CanonicalSection(
        id="sec3",
        heading="H3",
        heading_level=1,
        heading_path=["H3"],
        stable_key="sec3-key",
        content_hash="hash3",
        blocks=[
            CanonicalBlock(id="b3", kind=BlockKind.PARAGRAPH, text="text3", source=dummy_source)
        ],
        source=dummy_source,
        access=scope,
    )

    doc1 = CanonicalSOP(
        id="doc1",
        organization_id="tenant-1",
        policy_id="pol1",
        version_id="v1",
        source_document_ids=["doc1"],
        title="Doc",
        sections=[sec1, sec2, sec3],
    )

    sec1_changed = CanonicalSection(
        id="sec1_v2",
        heading="H1",
        heading_level=1,
        heading_path=["H1"],
        stable_key="sec1-key",
        content_hash="hash1_v2",
        blocks=[
            CanonicalBlock(
                id="b1", kind=BlockKind.PARAGRAPH, text="changed text1", source=dummy_source
            )
        ],
        source=dummy_source,
        access=scope,
    )

    doc2 = CanonicalSOP(
        id="doc1",
        organization_id="tenant-1",
        policy_id="pol1",
        version_id="v1",
        source_document_ids=["doc1"],
        title="Doc",
        sections=[sec1_changed, sec2, sec3],
    )

    old_chunks = chunker.chunk(doc1, "published")
    new_chunks = chunker.chunk(doc2, "published")

    {c.id for c in old_chunks}
    {c.id for c in new_chunks}

    old_sec2_3 = {c.id for c in old_chunks if c.section_id in ("sec2", "sec3")}
    new_sec2_3 = {c.id for c in new_chunks if c.section_id in ("sec2", "sec3")}

    assert old_sec2_3 == new_sec2_3

    old_sec1 = {c.id for c in old_chunks if c.section_id == "sec1"}
    new_sec1 = {c.id for c in new_chunks if c.section_id == "sec1_v2"}

    assert len(old_sec1) > 0
    assert len(new_sec1) > 0
    assert old_sec1.isdisjoint(new_sec1)


def test_table_continuation_repeats_headers_and_data_rows_distinct() -> None:
    chunker = SectionAwareFixtureChunker()
    chunker.MAX_WORDS = 10  # Force multi-chunk split across data rows

    dummy_source = SourceLocator(source_document_id="doc-tbl")
    table = CanonicalTable(
        caption="Inventory Audit",
        cells=[
            CanonicalTableCell(
                row=0, column=0, text="Item Name", is_header=True, source=dummy_source
            ),
            CanonicalTableCell(
                row=0, column=1, text="Quantity In Stock", is_header=True, source=dummy_source
            ),
            CanonicalTableCell(
                row=1, column=0, text="Warehouse Item Alpha", is_header=False, source=dummy_source
            ),
            CanonicalTableCell(
                row=1,
                column=1,
                text="100 Units Stored Safely",
                is_header=False,
                source=dummy_source,
            ),
            CanonicalTableCell(
                row=2, column=0, text="Warehouse Item Beta", is_header=False, source=dummy_source
            ),
            CanonicalTableCell(
                row=2,
                column=1,
                text="200 Units Stored Safely",
                is_header=False,
                source=dummy_source,
            ),
            CanonicalTableCell(
                row=3, column=0, text="Warehouse Item Gamma", is_header=False, source=dummy_source
            ),
            CanonicalTableCell(
                row=3,
                column=1,
                text="300 Units Stored Safely",
                is_header=False,
                source=dummy_source,
            ),
        ],
        source=dummy_source,
    )
    doc = CanonicalSOP(
        id="sop-table",
        organization_id="org-ajt",
        policy_id="pol-table",
        version_id="ver-1",
        source_document_ids=["doc-tbl"],
        title="Inventory Policy",
        sections=[
            CanonicalSection(
                id="sec-tbl",
                heading="Inventory Levels",
                heading_level=1,
                heading_path=("Inventory Levels",),
                stable_key="sec-tbl-key",
                content_hash="sec-tbl-hash",
                blocks=[
                    CanonicalBlock(
                        id="b-tbl",
                        kind=BlockKind.TABLE,
                        text=None,
                        table=table,
                        source=dummy_source,
                    )
                ],
                source=dummy_source,
                access=AccessScope(
                    departments=AccessDimension(mode=AccessMode.ALL),
                    locations=AccessDimension(mode=AccessMode.ALL),
                    roles=AccessDimension(mode=AccessMode.ALL),
                ),
            )
        ],
    )
    chunks = chunker.chunk(doc, "published")
    assert len(chunks) >= 3

    # Headers repeated on second and later chunks
    for i in range(1, len(chunks)):
        assert "**Inventory Audit**" in chunks[i].text
        assert "| Item Name | Quantity In Stock |" in chunks[i].text

    # Every data row appears in exactly one chunk
    data_rows = [
        "Warehouse Item Alpha",
        "Warehouse Item Beta",
        "Warehouse Item Gamma",
    ]
    for row in data_rows:
        appearances = sum(row in c.text for c in chunks)
        assert appearances == 1, f"Expected {row} in exactly 1 chunk, found in {appearances}"


def test_nested_list_chunking_preserves_hierarchy() -> None:
    chunker = SectionAwareFixtureChunker()
    dummy_source = SourceLocator(source_document_id="doc-list")
    items = [
        CanonicalListItem(
            text="Phase 1: Initiation",
            children=[
                CanonicalListItem(
                    text="Step 1.1: Document Verification",
                    children=[
                        CanonicalListItem(
                            text="Action 1.1.1: Verify Employee CNIC",
                            children=[],
                            source=dummy_source,
                        )
                    ],
                    source=dummy_source,
                )
            ],
            source=dummy_source,
        )
    ]
    doc = CanonicalSOP(
        id="sop-list",
        organization_id="org-ajt",
        policy_id="pol-list",
        version_id="ver-1",
        source_document_ids=["doc-list"],
        title="Onboarding Policy",
        sections=[
            CanonicalSection(
                id="sec-list",
                heading="Employee Verification",
                heading_level=1,
                heading_path=("Onboarding", "Verification"),
                stable_key="sec-list-key",
                content_hash="sec-list-hash",
                blocks=[
                    CanonicalBlock(
                        id="b-list",
                        kind=BlockKind.ORDERED_LIST,
                        text=None,
                        list_items=items,
                        source=dummy_source,
                    )
                ],
                source=dummy_source,
                access=AccessScope(
                    departments=AccessDimension(mode=AccessMode.ALL),
                    locations=AccessDimension(mode=AccessMode.ALL),
                    roles=AccessDimension(mode=AccessMode.ALL),
                ),
            )
        ],
    )
    chunks = chunker.chunk(doc, "published")
    assert len(chunks) == 1
    assert (
        "Phase 1: Initiation > Step 1.1: Document Verification > Action 1.1.1: Verify Employee CNIC"
        in chunks[0].text
    )


def test_chunk_deterministic_id_and_text_stability() -> None:
    chunker = SectionAwareFixtureChunker()
    dummy_source = SourceLocator(source_document_id="doc-stable")
    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"HR"})),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    doc = CanonicalSOP(
        id="sop-stable",
        organization_id="org-ajt",
        policy_id="pol-stable",
        version_id="ver-stable",
        source_document_ids=["doc-stable"],
        title="Leave Policy",
        sections=[
            CanonicalSection(
                id="sec-1",
                heading="Annual Leave",
                heading_level=1,
                heading_path=("Leave Policy", "Annual Leave"),
                stable_key="sec-1-key",
                content_hash="sec-1-hash",
                policy_number="SOP-HR-01",
                blocks=[
                    CanonicalBlock(
                        id="b-1",
                        kind=BlockKind.PARAGRAPH,
                        text="Annual leave entitlement is 20 working days.",
                        source=dummy_source,
                    )
                ],
                source=dummy_source,
                access=scope,
            ),
            CanonicalSection(
                id="sec-2",
                heading="Sick Leave",
                heading_level=1,
                heading_path=("Leave Policy", "Sick Leave"),
                stable_key="sec-2-key",
                content_hash="sec-2-hash",
                policy_number="SOP-HR-01",
                blocks=[
                    CanonicalBlock(
                        id="b-2",
                        kind=BlockKind.PARAGRAPH,
                        text="Sick leave requires medical certificate after 2 days.",
                        source=dummy_source,
                    )
                ],
                source=dummy_source,
                access=scope,
            ),
        ],
    )
    run1 = chunker.chunk(doc, "published")
    run2 = chunker.chunk(doc, "published")

    assert len(run1) == len(run2) == 2
    assert [c.id for c in run1] == [c.id for c in run2]
    assert [c.text for c in run1] == [c.text for c in run2]


def test_every_chunk_preserves_organization_and_access_metadata() -> None:
    chunker = SectionAwareFixtureChunker()
    dummy_source = SourceLocator(source_document_id="doc-meta")
    scope_a = AccessScope(
        departments=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"Operations"})),
        locations=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"Lahore"})),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    scope_b = AccessScope(
        departments=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"Finance"})),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"Manager"})),
    )
    sec_a = CanonicalSection(
        id="sec-a",
        heading="Operations SOP",
        heading_level=1,
        heading_path=("Operations", "Handling"),
        stable_key="sec-a-key",
        content_hash="sec-a-hash",
        policy_number="SOP-OPS-100",
        blocks=[
            CanonicalBlock(
                id="b-a",
                kind=BlockKind.PARAGRAPH,
                text="Operations section text line",
                source=dummy_source,
            )
        ],
        source=dummy_source,
        access=scope_a,
    )
    sec_b = CanonicalSection(
        id="sec-b",
        heading="Finance SOP",
        heading_level=1,
        heading_path=("Finance", "Invoicing"),
        stable_key="sec-b-key",
        content_hash="sec-b-hash",
        policy_number="SOP-FIN-200",
        blocks=[
            CanonicalBlock(
                id="b-b",
                kind=BlockKind.PARAGRAPH,
                text="Finance section text line",
                source=dummy_source,
            )
        ],
        source=dummy_source,
        access=scope_b,
    )
    doc = CanonicalSOP(
        id="sop-multi-meta",
        organization_id="tenant-ajg",
        policy_id="pol-multi",
        version_id="ver-multi",
        source_document_ids=["doc-meta"],
        title="Multi Domain SOP",
        sections=[sec_a, sec_b],
    )
    chunks = chunker.chunk(doc, "published")
    assert len(chunks) == 2

    chunk_a = next(c for c in chunks if c.section_id == "sec-a")
    assert chunk_a.organization_id == "tenant-ajg"
    assert chunk_a.access == scope_a
    assert chunk_a.heading_path == ("Operations", "Handling")
    assert chunk_a.policy_number == "SOP-OPS-100"

    chunk_b = next(c for c in chunks if c.section_id == "sec-b")
    assert chunk_b.organization_id == "tenant-ajg"
    assert chunk_b.access == scope_b
    assert chunk_b.heading_path == ("Finance", "Invoicing")
    assert chunk_b.policy_number == "SOP-FIN-200"


def test_golden_small_single_chunk_section() -> None:
    chunker = SemanticChunker()
    dummy = SourceLocator(source_document_id="doc1")
    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    section = CanonicalSection(
        id="sec1",
        heading="Login",
        heading_level=1,
        heading_path=("Security", "Login"),
        stable_key="k1",
        content_hash="h1",
        blocks=[
            CanonicalBlock(
                id="b1",
                kind=BlockKind.PARAGRAPH,
                text="Simple login text.",
                source=dummy,
            )
        ],
        source=dummy,
        access=scope,
    )
    sop = CanonicalSOP(
        id="sop1",
        organization_id="org1",
        policy_id="pol1",
        version_id="v1",
        source_document_ids=["doc1"],
        title="SOP",
        sections=[section],
    )
    chunks = chunker.chunk(sop, "published")
    assert len(chunks) == 1
    assert chunks[0].id == "v1:sec1:0"
    assert chunks[0].text == "Security > Login\nSimple login text."


def test_golden_table_that_fits() -> None:
    chunker = SemanticChunker()
    dummy = SourceLocator(source_document_id="doc1")
    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    table = CanonicalTable(
        caption="Roles",
        cells=[
            CanonicalTableCell(row=0, column=0, text="Role", is_header=True, source=dummy),
            CanonicalTableCell(row=0, column=1, text="Level", is_header=True, source=dummy),
            CanonicalTableCell(row=1, column=0, text="Admin", is_header=False, source=dummy),
            CanonicalTableCell(row=1, column=1, text="Tier 1", is_header=False, source=dummy),
        ],
        source=dummy,
    )
    section = CanonicalSection(
        id="sec2",
        heading="Roles",
        heading_level=1,
        heading_path=("Roles",),
        stable_key="k2",
        content_hash="h2",
        blocks=[
            CanonicalBlock(
                id="b2",
                kind=BlockKind.TABLE,
                table=table,
                source=dummy,
            )
        ],
        source=dummy,
        access=scope,
    )
    sop = CanonicalSOP(
        id="sop2",
        organization_id="org1",
        policy_id="pol1",
        version_id="v1",
        source_document_ids=["doc1"],
        title="SOP",
        sections=[section],
    )
    chunks = chunker.chunk(sop, "published")
    assert len(chunks) == 1
    assert chunks[0].id == "v1:sec2:0"
    expected_text = "Roles\n**Roles**\n| Role | Level |\n|---|---|\n| Admin | Tier 1 |"
    assert chunks[0].text == expected_text


def test_golden_table_split_at_row_boundaries() -> None:
    chunker = SemanticChunker()
    chunker.MAX_WORDS = 15
    dummy = SourceLocator(source_document_id="doc1")
    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    table = CanonicalTable(
        caption="Audit",
        cells=[
            CanonicalTableCell(row=0, column=0, text="H A", is_header=True, source=dummy),
            CanonicalTableCell(row=0, column=1, text="H B", is_header=True, source=dummy),
            CanonicalTableCell(row=1, column=0, text="Row 1 A", is_header=False, source=dummy),
            CanonicalTableCell(
                row=1,
                column=1,
                text="Row 1 B data words here for testing",
                is_header=False,
                source=dummy,
            ),
            CanonicalTableCell(row=2, column=0, text="Row 2 A", is_header=False, source=dummy),
            CanonicalTableCell(
                row=2,
                column=1,
                text="Row 2 B data words here for testing",
                is_header=False,
                source=dummy,
            ),
        ],
        source=dummy,
    )
    section = CanonicalSection(
        id="sec3",
        heading="Audit",
        heading_level=1,
        heading_path=("Audit",),
        stable_key="k3",
        content_hash="h3",
        blocks=[
            CanonicalBlock(
                id="b3",
                kind=BlockKind.TABLE,
                table=table,
                source=dummy,
            )
        ],
        source=dummy,
        access=scope,
    )
    sop = CanonicalSOP(
        id="sop3",
        organization_id="org1",
        policy_id="pol1",
        version_id="v1",
        source_document_ids=["doc1"],
        title="SOP",
        sections=[section],
    )
    chunks = chunker.chunk(sop, "published")
    assert len(chunks) == 2
    assert chunks[0].id == "v1:sec3:0"
    assert chunks[1].id == "v1:sec3:1"
    expected_chunk0 = (
        "Audit\n**Audit**\n| H A | H B |\n|---|---|\n"
        "| Row 1 A | Row 1 B data words here for testing |"
    )
    expected_chunk1 = (
        "Audit\n**Audit**\n| H A | H B |\n|---|---|\n"
        "| Row 2 A | Row 2 B data words here for testing |"
    )
    assert chunks[0].text == expected_chunk0
    assert chunks[1].text == expected_chunk1


def test_golden_nested_list() -> None:
    chunker = SemanticChunker()
    dummy = SourceLocator(source_document_id="doc1")
    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    items = [
        CanonicalListItem(
            text="Top Level",
            children=[CanonicalListItem(text="Child Item", children=[], source=dummy)],
            source=dummy,
        )
    ]
    section = CanonicalSection(
        id="sec4",
        heading="Hierarchy",
        heading_level=1,
        heading_path=("Hierarchy",),
        stable_key="k4",
        content_hash="h4",
        blocks=[
            CanonicalBlock(
                id="b4",
                kind=BlockKind.ORDERED_LIST,
                list_items=items,
                source=dummy,
            )
        ],
        source=dummy,
        access=scope,
    )
    sop = CanonicalSOP(
        id="sop4",
        organization_id="org1",
        policy_id="pol1",
        version_id="v1",
        source_document_ids=["doc1"],
        title="SOP",
        sections=[section],
    )
    chunks = chunker.chunk(sop, "published")
    assert len(chunks) == 1
    assert chunks[0].id == "v1:sec4:0"
    assert chunks[0].text == "Hierarchy\nTop Level\nTop Level > Child Item"


def test_golden_long_paragraph_over_max_words() -> None:
    chunker = SemanticChunker()
    chunker.MAX_WORDS = 20
    dummy = SourceLocator(source_document_id="doc1")
    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    words = [f"word{i}" for i in range(50)]
    para_text = " ".join(words)
    section = CanonicalSection(
        id="sec5",
        heading="Long",
        heading_level=1,
        heading_path=("Long",),
        stable_key="k5",
        content_hash="h5",
        blocks=[
            CanonicalBlock(
                id="b5",
                kind=BlockKind.PARAGRAPH,
                text=para_text,
                source=dummy,
            )
        ],
        source=dummy,
        access=scope,
    )
    sop = CanonicalSOP(
        id="sop5",
        organization_id="org1",
        policy_id="pol1",
        version_id="v1",
        source_document_ids=["doc1"],
        title="SOP",
        sections=[section],
    )
    chunks = chunker.chunk(sop, "published")
    assert len(chunks) == 3
    assert chunks[0].id == "v1:sec5:0"
    assert chunks[1].id == "v1:sec5:1"
    assert chunks[2].id == "v1:sec5:2"
    assert chunks[0].text == "Long\n" + " ".join(words[:20])
    assert chunks[1].text == "Long\n" + " ".join(words[20:40])
    assert chunks[2].text == "Long\n" + " ".join(words[40:50])


def test_oversized_table_row_splits_at_cell_boundaries_with_header_repeat() -> None:
    chunker = SemanticChunker()
    chunker.MAX_WORDS = 15
    dummy = SourceLocator(source_document_id="doc-ovr")
    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"Warehouse"})),
        locations=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"Mill-1"})),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    table = CanonicalTable(
        caption="Godown Capacity Audit",
        cells=[
            CanonicalTableCell(row=0, column=0, text="Godown", is_header=True, source=dummy),
            CanonicalTableCell(row=0, column=1, text="Material", is_header=True, source=dummy),
            CanonicalTableCell(row=0, column=2, text="Capacity", is_header=True, source=dummy),
            CanonicalTableCell(row=0, column=3, text="Status", is_header=True, source=dummy),
            CanonicalTableCell(row=1, column=0, text="Godown 9", is_header=False, source=dummy),
            CanonicalTableCell(
                row=1,
                column=1,
                text="Raw Cotton Grade A with long description of packaging",
                is_header=False,
                source=dummy,
            ),
            CanonicalTableCell(
                row=1,
                column=2,
                text="Capacity 4824 Metric Tonnes stored safely in warehouse shelf",
                is_header=False,
                source=dummy,
            ),
            CanonicalTableCell(
                row=1,
                column=3,
                text="Status Active and verified by supervisor",
                is_header=False,
                source=dummy,
            ),
        ],
        source=dummy,
    )
    section = CanonicalSection(
        id="sec-ovr",
        heading="Storage",
        heading_level=1,
        heading_path=("Warehouse", "Inventory"),
        policy_number="SOP-WH-001",
        stable_key="sec-ovr-key",
        content_hash="sec-ovr-hash",
        blocks=[CanonicalBlock(id="b-ovr", kind=BlockKind.TABLE, table=table, source=dummy)],
        source=dummy,
        access=scope,
    )
    sop = CanonicalSOP(
        id="sop-ovr",
        organization_id="tenant-ajg",
        policy_id="pol-wh",
        version_id="ver-tbl",
        source_document_ids=["doc-ovr"],
        title="Warehouse Inventory SOP",
        sections=[section],
    )
    chunks = chunker.chunk(sop, "published")
    assert len(chunks) == 3

    # Consecutive deterministic IDs
    assert [c.id for c in chunks] == [
        "ver-tbl:sec-ovr:0",
        "ver-tbl:sec-ovr:1",
        "ver-tbl:sec-ovr:2",
    ]

    # Every part repeats caption, table header, context cell, and preserves metadata
    for c in chunks:
        assert "**Godown Capacity Audit**" in c.text
        assert "| Godown | Material | Capacity | Status |" in c.text
        assert "Godown 9" in c.text
        assert c.access == scope
        assert c.organization_id == "tenant-ajg"
        assert c.heading_path == ("Warehouse", "Inventory")
        assert c.policy_number == "SOP-WH-001"

    # Every data row cell appears in exactly one part
    cell_texts = [
        "Raw Cotton Grade A with long description of packaging",
        "Capacity 4824 Metric Tonnes stored safely in warehouse shelf",
        "Status Active and verified by supervisor",
    ]
    for cell_text in cell_texts:
        appearances = sum(cell_text in c.text for c in chunks)
        assert appearances == 1, f"Expected '{cell_text}' in 1 chunk, found in {appearances}"

    # Stable and deterministic across runs
    run2 = chunker.chunk(sop, "published")
    assert [c.id for c in chunks] == [c.id for c in run2]
    assert [c.text for c in chunks] == [c.text for c in run2]


def test_oversized_single_cell_splits_at_word_boundaries_without_content_loss() -> None:
    chunker = SemanticChunker()
    chunker.MAX_WORDS = 20
    dummy = SourceLocator(source_document_id="doc-cell")
    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    desc_words = [f"desc_token_{i}" for i in range(45)]
    long_desc = " ".join(desc_words)

    table = CanonicalTable(
        caption="Chemical Safety",
        cells=[
            CanonicalTableCell(row=0, column=0, text="Chemical", is_header=True, source=dummy),
            CanonicalTableCell(row=0, column=1, text="Safety Notes", is_header=True, source=dummy),
            CanonicalTableCell(row=1, column=0, text="Solvent-X", is_header=False, source=dummy),
            CanonicalTableCell(row=1, column=1, text=long_desc, is_header=False, source=dummy),
        ],
        source=dummy,
    )
    section = CanonicalSection(
        id="sec-cell",
        heading="Hazards",
        heading_level=1,
        heading_path=("Safety", "Hazards"),
        policy_number="SOP-SAFE-01",
        stable_key="sec-cell-key",
        content_hash="sec-cell-hash",
        blocks=[CanonicalBlock(id="b-cell", kind=BlockKind.TABLE, table=table, source=dummy)],
        source=dummy,
        access=scope,
    )
    sop = CanonicalSOP(
        id="sop-cell",
        organization_id="tenant-ajg",
        policy_id="pol-safe",
        version_id="ver-cell",
        source_document_ids=["doc-cell"],
        title="Safety SOP",
        sections=[section],
    )
    chunks = chunker.chunk(sop, "published")
    assert len(chunks) == 3

    # All parts repeat header and context
    for c in chunks:
        assert "**Chemical Safety**" in c.text
        assert "| Chemical | Safety Notes |" in c.text
        assert "Solvent-X" in c.text

    # Concatenation of split cell parts recovers all words with no loss
    recovered_words: list[str] = []
    for c in chunks:
        for line in c.text.split("\n"):
            if line.startswith("| Solvent-X |"):
                cell_part = line.split("|")[2].strip()
                recovered_words.extend(cell_part.split())

    assert recovered_words == desc_words


def test_header_only_table_does_not_crash() -> None:
    chunker = SemanticChunker()
    dummy = SourceLocator(source_document_id="doc-hdr")
    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    table = CanonicalTable(
        caption="Empty Table Structure",
        cells=[
            CanonicalTableCell(row=0, column=0, text="Column Alpha", is_header=True, source=dummy),
            CanonicalTableCell(row=0, column=1, text="Column Beta", is_header=True, source=dummy),
        ],
        source=dummy,
    )
    section = CanonicalSection(
        id="sec-hdr",
        heading="Definitions",
        heading_level=1,
        heading_path=("Appendix", "Definitions"),
        policy_number="SOP-APP-01",
        stable_key="sec-hdr-key",
        content_hash="sec-hdr-hash",
        blocks=[CanonicalBlock(id="b-hdr", kind=BlockKind.TABLE, table=table, source=dummy)],
        source=dummy,
        access=scope,
    )
    sop = CanonicalSOP(
        id="sop-hdr",
        organization_id="tenant-ajg",
        policy_id="pol-hdr",
        version_id="ver-hdr",
        source_document_ids=["doc-hdr"],
        title="Appendix SOP",
        sections=[section],
    )
    chunks = chunker.chunk(sop, "published")
    assert len(chunks) == 1
    assert "**Empty Table Structure**" in chunks[0].text
    assert "| Column Alpha | Column Beta |" in chunks[0].text


def test_oversized_table_row_edge_case_header_context_exceeds_budget() -> None:
    chunker = SemanticChunker()
    chunker.MAX_WORDS = 5  # Artificially low budget where header + context exceeds budget
    dummy = SourceLocator(source_document_id="doc-edge")
    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    table = CanonicalTable(
        caption="Large Header Edge Case",
        cells=[
            CanonicalTableCell(row=0, column=0, text="Godown Header", is_header=True, source=dummy),
            CanonicalTableCell(
                row=0, column=1, text="Capacity Header", is_header=True, source=dummy
            ),
            CanonicalTableCell(
                row=1, column=0, text="Godown Nine Alpha", is_header=False, source=dummy
            ),
            CanonicalTableCell(
                row=1, column=1, text="One Hundred Tons", is_header=False, source=dummy
            ),
        ],
        source=dummy,
    )
    section = CanonicalSection(
        id="sec-edge",
        heading="Edge Heading",
        heading_level=1,
        heading_path=("Edge", "Section"),
        policy_number="SOP-EDGE-01",
        stable_key="sec-edge-key",
        content_hash="sec-edge-hash",
        blocks=[CanonicalBlock(id="b-edge", kind=BlockKind.TABLE, table=table, source=dummy)],
        source=dummy,
        access=scope,
    )
    sop = CanonicalSOP(
        id="sop-edge",
        organization_id="tenant-ajg",
        policy_id="pol-edge",
        version_id="ver-edge",
        source_document_ids=["doc-edge"],
        title="Edge SOP",
        sections=[section],
    )
    # Does not crash or drop content
    chunks = chunker.chunk(sop, "published")
    assert len(chunks) >= 1
    assert any("One Hundred Tons" in c.text for c in chunks)


def test_table_with_many_short_numeric_cells() -> None:
    chunker = SemanticChunker()
    dummy = SourceLocator(source_document_id="doc-num")
    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    headers = ["Item", "Bin", "Qty", "Min", "Max"]
    cells = [
        CanonicalTableCell(row=0, column=i, text=h, is_header=True, source=dummy)
        for i, h in enumerate(headers)
    ]
    expected_skus: list[str] = []
    for r in range(1, 35):
        sku = f"SKU-{1000 + r}"
        expected_skus.append(sku)
        cells.extend(
            [
                CanonicalTableCell(row=r, column=0, text=sku, is_header=False, source=dummy),
                CanonicalTableCell(
                    row=r, column=1, text=f"B-{r:02d}", is_header=False, source=dummy
                ),
                CanonicalTableCell(
                    row=r, column=2, text=str(r * 25), is_header=False, source=dummy
                ),
                CanonicalTableCell(row=r, column=3, text="50", is_header=False, source=dummy),
                CanonicalTableCell(row=r, column=4, text="1000", is_header=False, source=dummy),
            ]
        )

    table = CanonicalTable(
        caption="Spare Parts Inventory Levels",
        cells=cells,
        source=dummy,
    )
    section = CanonicalSection(
        id="sec-num",
        heading="Parts Inventory",
        heading_level=1,
        heading_path=("Maintenance", "Parts Inventory"),
        policy_number="SOP-MAINT-42",
        stable_key="sec-num-key",
        content_hash="sec-num-hash",
        blocks=[CanonicalBlock(id="b-num", kind=BlockKind.TABLE, table=table, source=dummy)],
        source=dummy,
        access=scope,
    )
    sop = CanonicalSOP(
        id="sop-num",
        organization_id="ajt",
        policy_id="pol-maint",
        version_id="ver-num-v1",
        source_document_ids=["doc-num"],
        title="Maintenance Inventory SOP",
        sections=[section],
    )

    chunks = chunker.chunk(sop, "published")
    assert len(chunks) >= 1

    # Every chunk repeats caption, header, and separator
    for c in chunks:
        assert "**Spare Parts Inventory Levels**" in c.text
        assert "| Item | Bin | Qty | Min | Max |" in c.text
        assert "|---|---|---|---|---|" in c.text
        assert c.policy_number == "SOP-MAINT-42"
        assert c.organization_id == "ajt"

    # All SKUs are present across chunks with no loss and no unintended duplication
    found_skus: list[str] = []
    for c in chunks:
        for line in c.text.splitlines():
            for sku in expected_skus:
                if f"| {sku} |" in line:
                    found_skus.append(sku)

    assert sorted(found_skus) == sorted(expected_skus)
    assert len(found_skus) == len(expected_skus)


def test_headings_with_deep_heading_paths() -> None:
    chunker = SemanticChunker()
    dummy = SourceLocator(source_document_id="doc-deep")
    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    deep_path = (
        "Aziz Jan Group",
        "Manufacturing Operations",
        "Textile Division",
        "Weaving Unit 3",
        "Safety Guidelines",
        "Emergency Shutdown Protocols",
    )
    long_words = [f"emergency_step_{i}" for i in range(500)]
    section = CanonicalSection(
        id="sec-deep",
        heading="Emergency Shutdown Protocols",
        heading_level=6,
        heading_path=deep_path,
        policy_number="SOP-WEAVE-SEC-99",
        stable_key="sec-deep-key",
        content_hash="sec-deep-hash",
        blocks=[
            CanonicalBlock(
                id="b-deep",
                kind=BlockKind.PARAGRAPH,
                text=" ".join(long_words),
                source=dummy,
            )
        ],
        source=dummy,
        access=scope,
    )
    sop = CanonicalSOP(
        id="sop-deep",
        organization_id="ajt",
        policy_id="pol-weave",
        version_id="ver-deep-v1",
        source_document_ids=["doc-deep"],
        title="Weaving Safety SOP",
        sections=[section],
    )

    chunks = chunker.chunk(sop, "published")
    # Under 480-token budget, 500 emergency_step tokens split into 6 chunks (exact tokenizer)
    # or 7 chunks (conservative fallback estimator), all strictly <= 480 tokens
    assert len(chunks) in {6, 7}
    expected_header_prefix = " > ".join(deep_path)

    for idx, c in enumerate(chunks):
        assert c.id == f"ver-deep-v1:sec-deep:{idx}"
        assert c.heading_path == deep_path
        assert c.policy_number == "SOP-WEAVE-SEC-99"
        assert c.organization_id == "ajt"
        assert c.text.startswith(expected_header_prefix)
        assert c.chunk_index == idx


def test_deterministic_generated_input_budget_and_no_loss() -> None:
    import random

    rng = random.Random(42)
    dummy = SourceLocator(source_document_id="doc-gen")
    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )

    english_words = [
        "standard",
        "operating",
        "procedure",
        "warehouse",
        "inventory",
        "control",
        "safety",
        "audit",
        "management",
        "dispatch",
        "material",
        "inspection",
        "calibration",
        "compliance",
        "verification",
        "authorization",
        "supervisor",
        "temperature",
        "humidity",
        "storage",
        "tolerance",
        "threshold",
        "critical",
    ]

    sections: list[CanonicalSection] = []
    all_source_words: list[str] = []

    for s_idx in range(12):
        sec_id = f"sec-gen-{s_idx}"
        heading_len = rng.randint(2, 4)
        h_words = [rng.choice(english_words) for _ in range(heading_len)]
        h_path = tuple(h_words)

        blocks: list[CanonicalBlock] = []
        kind_choice = s_idx % 3

        if kind_choice == 0:
            # Paragraph
            word_count = rng.randint(50, 420)
            p_words = [f"{rng.choice(english_words)}_{w}" for w in range(word_count)]
            all_source_words.extend(p_words)
            blocks.append(
                CanonicalBlock(
                    id=f"b-p-{s_idx}",
                    kind=BlockKind.PARAGRAPH,
                    text=" ".join(p_words),
                    source=dummy,
                )
            )
        elif kind_choice == 1:
            # Table
            cols = rng.randint(2, 4)
            rows = rng.randint(3, 10)
            t_cells: list[CanonicalTableCell] = []
            for col_i in range(cols):
                t_cells.append(
                    CanonicalTableCell(
                        row=0, column=col_i, text=f"Head_{col_i}", is_header=True, source=dummy
                    )
                )
            for row_i in range(1, rows):
                for col_i in range(cols):
                    cell_word = f"cell_{s_idx}_{row_i}_{col_i}"
                    all_source_words.append(cell_word)
                    t_cells.append(
                        CanonicalTableCell(
                            row=row_i, column=col_i, text=cell_word, is_header=False, source=dummy
                        )
                    )
            blocks.append(
                CanonicalBlock(
                    id=f"b-t-{s_idx}",
                    kind=BlockKind.TABLE,
                    table=CanonicalTable(caption=f"Table {s_idx}", cells=t_cells, source=dummy),
                    source=dummy,
                )
            )
        else:
            # Nested list
            l_items: list[CanonicalListItem] = []
            for item_i in range(3):
                w_parent = f"list_{s_idx}_parent_{item_i}"
                all_source_words.append(w_parent)
                w_child = f"list_{s_idx}_child_{item_i}"
                all_source_words.append(w_child)
                l_items.append(
                    CanonicalListItem(
                        text=w_parent,
                        children=[CanonicalListItem(text=w_child, children=[], source=dummy)],
                        source=dummy,
                    )
                )
            blocks.append(
                CanonicalBlock(
                    id=f"b-l-{s_idx}",
                    kind=BlockKind.ORDERED_LIST,
                    list_items=l_items,
                    source=dummy,
                )
            )

        sections.append(
            CanonicalSection(
                id=sec_id,
                heading=h_words[-1],
                heading_level=len(h_words),
                heading_path=h_path,
                policy_number=f"SOP-GEN-{s_idx:02d}",
                stable_key=f"key-{s_idx}",
                content_hash=f"hash-{s_idx}",
                blocks=blocks,
                source=dummy,
                access=scope,
            )
        )

    sop = CanonicalSOP(
        id="sop-generated",
        organization_id="ajt",
        policy_id="pol-gen",
        version_id="ver-gen-1",
        source_document_ids=["doc-gen"],
        title="Generated Test SOP",
        sections=sections,
    )

    chunker = SemanticChunker()
    run1 = chunker.chunk(sop, "published")
    run2 = chunker.chunk(sop, "published")

    # Prove byte-identical output across two runs
    assert len(run1) == len(run2)
    for c1, c2 in zip(run1, run2, strict=True):
        assert c1.id == c2.id
        assert c1.text == c2.text
        assert c1.heading_path == c2.heading_path
        assert c1.policy_number == c2.policy_number
        assert c1.organization_id == c2.organization_id

    # Prove no text loss: all generated data tokens are present across chunks
    combined_text = " ".join(c.text for c in run1)
    for word in all_source_words:
        assert word in combined_text, f"Missing token {word} from chunked output"

    # Prove chunk IDs are strictly consecutive within each section
    by_section: dict[str, list[RetrievalChunk]] = {}
    for c in run1:
        by_section.setdefault(c.section_id, []).append(c)

    for sec_id, s_chunks in by_section.items():
        for expected_idx, c in enumerate(s_chunks):
            assert c.id == f"ver-gen-1:{sec_id}:{expected_idx}"
            assert c.chunk_index == expected_idx


def test_token_estimator_conservative_bounds() -> None:
    chunker = SemanticChunker()

    # Plain text
    text1 = "This is a standard operating procedure for warehouse management."
    est1 = chunker.estimate_tokens(text1)
    assert est1 >= len(text1.split())

    # Table text with pipes and codes
    text2 = "| SKU-1042 | PES-01 | 450 | 50 | 1000 | ACTIVE |"
    est2 = chunker.estimate_tokens(text2)
    assert est2 >= len(text2.split())
    assert est2 >= int(len(text2) / 3.8)


def test_strict_token_budget_enforcement():
    """Verify that every chunk produced strictly respects the 480 target and 507 hard maximum."""
    chunker = SemanticChunker()
    dummy = SourceLocator(source_document_id="doc-budget")
    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )

    # Construct a section with heavy markdown table
    cells = [
        CanonicalTableCell(row=0, column=0, text="Code", is_header=True, source=dummy),
        CanonicalTableCell(row=0, column=1, text="Description", is_header=True, source=dummy),
        CanonicalTableCell(row=0, column=2, text="Specification", is_header=True, source=dummy),
    ]
    for r in range(1, 35):
        cells.extend(
            [
                CanonicalTableCell(
                    row=r, column=0, text=f"SKU-{r:04d}", is_header=False, source=dummy
                ),
                CanonicalTableCell(
                    row=r,
                    column=1,
                    text=f"Raw material batch allocation item for sector {r} testing standard",
                    is_header=False,
                    source=dummy,
                ),
                CanonicalTableCell(
                    row=r,
                    column=2,
                    text=f"Tolerance threshold +-0.{r % 9 + 1}mm at 25C operating condition",
                    is_header=False,
                    source=dummy,
                ),
            ]
        )
    table = CanonicalTable(caption="Batch Specifications", cells=cells, source=dummy)

    section = CanonicalSection(
        id="sec-budget",
        heading="Batch Control",
        heading_level=2,
        heading_path=("Production Operations", "Batch Control"),
        policy_number="SOP-MFG-002",
        stable_key="key-sec-budget",
        content_hash="hash-sec-budget",
        blocks=[CanonicalBlock(id="b-tbl", kind=BlockKind.TABLE, table=table, source=dummy)],
        source=dummy,
        access=scope,
    )
    sop = CanonicalSOP(
        id="sop-budget",
        organization_id="ajt",
        policy_id="pol-mfg",
        version_id="ver-mfg-v1",
        source_document_ids=["doc-budget"],
        title="Manufacturing SOP",
        sections=[section],
    )

    chunks = chunker.chunk(sop, "published")
    assert len(chunks) > 1

    for c in chunks:
        tok_count = chunker.count_embedding_tokens(c.text)
        assert tok_count <= chunker.SOFT_TARGET_TOKENS, (
            f"Chunk {c.id} exceeded soft target 480 tokens: observed {tok_count}"
        )
        assert tok_count <= chunker.HARD_MAX_TOKENS, (
            f"Chunk {c.id} exceeded hard limit 507 tokens: observed {tok_count}"
        )


def test_hard_max_token_guard_failure():
    """Verify that if a chunk exceeds HARD_MAX_TOKENS (507), a ValueError is raised."""
    import pytest

    chunker = SemanticChunker()
    original_count = chunker.count_embedding_tokens
    chunker.SOFT_TARGET_TOKENS = 600  # Force final hard-limit guard, independently of splitting.

    def failing_counter(text: str) -> int:
        if "OVERSIZED_TOKEN_BLOB" in text:
            return 515
        return original_count(text)

    chunker.count_embedding_tokens = failing_counter  # type: ignore[method-assign]

    dummy = SourceLocator(source_document_id="doc-fail")
    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    section = CanonicalSection(
        id="sec-fail",
        heading="Failure Test",
        heading_level=1,
        heading_path=("Failure Test",),
        stable_key="key-fail",
        content_hash="hash-fail",
        blocks=[
            CanonicalBlock(
                id="b-fail",
                kind=BlockKind.PARAGRAPH,
                text="OVERSIZED_TOKEN_BLOB",
                source=dummy,
            )
        ],
        source=dummy,
        access=scope,
    )
    sop = CanonicalSOP(
        id="sop-fail",
        organization_id="ajt",
        policy_id="pol-fail",
        version_id="ver-fail-1",
        source_document_ids=["doc-fail"],
        title="Fail SOP",
        sections=[section],
    )

    with pytest.raises(ValueError, match="exceeds hard maximum of 507 tokens"):
        chunker.chunk(sop, "published")


def test_hard_max_token_boundary_507_and_508():
    """Verify that an input of exactly 507 tokens passes, while 508 fails with ValueError."""
    import pytest

    chunker = SemanticChunker()
    dummy = SourceLocator(source_document_id="doc-boundary")
    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )

    def make_sop(token_target: int) -> CanonicalSOP:
        section = CanonicalSection(
            id=f"sec-boundary-{token_target}",
            heading="Boundary",
            heading_level=1,
            heading_path=("Boundary",),
            stable_key=f"k-{token_target}",
            content_hash=f"h-{token_target}",
            blocks=[
                CanonicalBlock(id="b1", kind=BlockKind.PARAGRAPH, text="content", source=dummy)
            ],
            source=dummy,
            access=scope,
        )
        return CanonicalSOP(
            id=f"sop-boundary-{token_target}",
            organization_id="org",
            policy_id="pol",
            version_id="ver",
            source_document_ids=["doc-boundary"],
            title="Boundary SOP",
            sections=[section],
        )

    # Force the final guard rather than a tokenizer that claims even empty context is full.
    chunker.SOFT_TARGET_TOKENS = 600
    original_count = chunker.count_embedding_tokens
    # 1. Exactly 507 tokens must pass
    chunker.count_embedding_tokens = (
        lambda text: 507 if "\ncontent" in text else original_count(text)
    )  # type: ignore[method-assign]
    chunks = chunker.chunk(make_sop(507), "published")
    assert len(chunks) == 1
    assert chunks[0].id == "ver:sec-boundary-507:0"

    # 2. Exactly 508 tokens must fail with ValueError
    chunker.count_embedding_tokens = (
        lambda text: 508 if "\ncontent" in text else original_count(text)
    )  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="exceeds hard maximum of 507 tokens"):
        chunker.chunk(make_sop(508), "published")


def test_table_row_reassembly_and_header_replication():
    """Verify that split tables replicate caption/headers on each fragment and preserve all rows."""
    chunker = SemanticChunker()
    dummy = SourceLocator(source_document_id="doc-tbl")
    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )

    headers = ["Item ID", "Category", "Threshold Level", "Responsible Party"]
    total_rows = 25
    expected_row_ids: list[str] = []

    cells = [
        CanonicalTableCell(row=0, column=c_idx, text=h, is_header=True, source=dummy)
        for c_idx, h in enumerate(headers)
    ]
    for r in range(1, total_rows + 1):
        item_id = f"ITEM-{r:03d}"
        expected_row_ids.append(item_id)
        cells.extend(
            [
                CanonicalTableCell(row=r, column=0, text=item_id, is_header=False, source=dummy),
                CanonicalTableCell(
                    row=r, column=1, text=f"Category-{r % 4}", is_header=False, source=dummy
                ),
                CanonicalTableCell(
                    row=r,
                    column=2,
                    text=f"Value {r * 10} units per hour",
                    is_header=False,
                    source=dummy,
                ),
                CanonicalTableCell(
                    row=r,
                    column=3,
                    text=f"Officer {r % 3} supervisor",
                    is_header=False,
                    source=dummy,
                ),
            ]
        )

    table = CanonicalTable(caption="Threshold Matrix", cells=cells, source=dummy)
    section = CanonicalSection(
        id="sec-tbl",
        heading="Matrix",
        heading_level=1,
        heading_path=("Inventory", "Matrix"),
        policy_number="SOP-INV-001",
        stable_key="key-sec-tbl",
        content_hash="hash-sec-tbl",
        blocks=[CanonicalBlock(id="b-tbl", kind=BlockKind.TABLE, table=table, source=dummy)],
        source=dummy,
        access=scope,
    )
    sop = CanonicalSOP(
        id="sop-tbl",
        organization_id="ajt",
        policy_id="pol-inv",
        version_id="ver-inv-1",
        source_document_ids=["doc-tbl"],
        title="Inventory SOP",
        sections=[section],
    )

    chunks = chunker.chunk(sop, "published")
    assert len(chunks) > 1

    # Verify every chunk contains repeated table header and caption
    found_row_ids: list[str] = []
    for c in chunks:
        assert "**Threshold Matrix**" in c.text
        assert "| Item ID | Category | Threshold Level | Responsible Party |" in c.text
        assert "|---|---|---|---|" in c.text
        for line in c.text.splitlines():
            for item_id in expected_row_ids:
                if f"| {item_id} |" in line:
                    found_row_ids.append(item_id)

    # Exact 1-to-1 preservation: no row omitted, no duplicate data rows
    assert sorted(found_row_ids) == sorted(expected_row_ids)
    assert len(found_row_ids) == len(expected_row_ids)


def test_heading_shortening_preserves_sop_identifier_and_parent_leaf():
    """Verify deterministic heading shortening preserves primary SOP identifier,
    while keeping the complete original heading path recoverable in chunk metadata."""
    chunker = SemanticChunker()

    # Case 1: Heading fits within budget <= 75 tokens -> preserved exactly
    short_path = ("Aziz Jan Group", "Store Operations", "4.3 Damaged Stock")
    formatted_short = chunker._format_heading_prefix(short_path, policy_number="SOP-STORE-04")
    assert formatted_short == "Aziz Jan Group > Store Operations > 4.3 Damaged Stock"

    # Case 2: Deep path with intermediate SOP identifier that exceeds budget
    deep_long_path = (
        "Aziz Jan Group Holding Corporate Operational Standard Manual 2026",
        "Division of Textile Manufacturing and Industrial Yarn Quality Assurance",
        "SOP-TEXTILE-042 High Speed Loom Automated Safety Interlocks Protocol",
        "Subclause 4.2 Mechanical Emergency Braking Calibration and Tolerance Thresholds",
        "Section 4.2.1 Immediate Manual Override and Secondary Emergency Cutoff Switch Procedure",
    )
    formatted_deep = chunker._format_heading_prefix(deep_long_path, policy_number=None)

    # Must be deterministic across calls
    assert formatted_deep == chunker._format_heading_prefix(deep_long_path, policy_number=None)

    # Must preserve root, SOP identifier, parent, and leaf
    assert "Aziz Jan Group" in formatted_deep
    assert "SOP-TEXTILE-042" in formatted_deep
    assert "..." in formatted_deep
    assert "Subclause 4.2" in formatted_deep
    assert "Section 4.2.1" in formatted_deep

    # Case 3: Policy number provided externally and not in heading path
    deep_no_sop_in_path = (
        "Aziz Jan Group Holding Corporate Operational Standard Manual 2026",
        "Division of Textile Manufacturing and Industrial Yarn Quality Assurance",
        "Departmental Safety Review Framework for Critical Machinery and Loom Infrastructure",
        "Subclause 4.2 Mechanical Emergency Braking Calibration and Tolerance Thresholds",
        "Section 4.2.1 Immediate Manual Override and Secondary Emergency Cutoff Switch Procedure",
    )
    formatted_with_pol = chunker._format_heading_prefix(
        deep_no_sop_in_path, policy_number="SOP-EXT-999"
    )
    assert "[SOP-EXT-999]" in formatted_with_pol
    assert "Section 4.2.1" in formatted_with_pol

    # Case 4: Verify chunk metadata stores full recoverable path
    dummy = SourceLocator(source_document_id="doc-head")
    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    section = CanonicalSection(
        id="sec-head",
        heading="Immediate Manual Override and Secondary Emergency Cutoff Switch Procedure",
        heading_level=5,
        heading_path=deep_long_path,
        policy_number="SOP-TEXTILE-042",
        stable_key="key-sec-head",
        content_hash="hash-sec-head",
        blocks=[
            CanonicalBlock(
                id="b-head",
                kind=BlockKind.PARAGRAPH,
                text="Execute emergency cutoff switch immediately upon hearing abnormal vibration.",
                source=dummy,
            )
        ],
        source=dummy,
        access=scope,
    )
    sop = CanonicalSOP(
        id="sop-head",
        organization_id="ajt",
        policy_id="pol-textile",
        version_id="ver-textile-1",
        source_document_ids=["doc-head"],
        title="Textile SOP",
        sections=[section],
    )
    chunks = chunker.chunk(sop, "published")
    assert len(chunks) == 1
    # Full unshortened path is completely preserved in chunk metadata
    assert chunks[0].heading_path == deep_long_path
    assert chunks[0].policy_number == "SOP-TEXTILE-042"


def test_small_sections_invariance_and_id_stability():
    """Verify that sections fitting in token budget produce 1 chunk with identical IDs."""
    chunker = SemanticChunker()
    dummy = SourceLocator(source_document_id="doc-small")
    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )

    section = CanonicalSection(
        id="sec-small",
        heading="Scope and Purpose",
        heading_level=1,
        heading_path=("Policy", "Scope and Purpose"),
        policy_number="SOP-001",
        stable_key="key-sec-small",
        content_hash="hash-sec-small",
        blocks=[
            CanonicalBlock(
                id="b-small",
                kind=BlockKind.PARAGRAPH,
                text="This policy applies to all personnel within the organization.",
                source=dummy,
            )
        ],
        source=dummy,
        access=scope,
    )
    sop = CanonicalSOP(
        id="sop-small",
        organization_id="ajt",
        policy_id="pol-001",
        version_id="ver-001",
        source_document_ids=["doc-small"],
        title="Small SOP",
        sections=[section],
    )

    chunks1 = chunker.chunk(sop, "published")
    chunks2 = chunker.chunk(sop, "published")

    assert len(chunks1) == 1
    assert len(chunks2) == 1
    assert chunks1[0].id == "ver-001:sec-small:0"
    assert chunks1[0].id == chunks2[0].id
    assert chunks1[0].text == chunks2[0].text
    assert chunks1[0].chunk_index == 0


def test_semantic_chunker_fallback_without_tokenizer():
    """Verify chunker operates reliably and conservatively in fallback mode without a tokenizer."""
    chunker = SemanticChunker(tokenizer=None)
    # Ensure fallback mode is active (no external tokenizer object)
    assert chunker._tokenizer is None

    # 1. Conservative estimator checks on diverse text patterns
    plain_text = "Standard Operating Procedure for warehouse dispatch operations."
    table_text = "| SKU-001 | 500 MT | ACTIVE |\n| SKU-002 | 250 MT | PENDING |"
    dense_codes = "PO#994821-A / Model: XL-240V / Serial: 8839-2049-1102"

    plain_est = chunker.count_embedding_tokens(plain_text)
    table_est = chunker.count_embedding_tokens(table_text)
    code_est = chunker.count_embedding_tokens(dense_codes)

    assert plain_est >= len(plain_text.split())
    assert table_est >= len(table_text.split())
    assert code_est >= len(dense_codes.split())

    # 2. End-to-end chunking in fallback mode
    dummy = SourceLocator(source_document_id="doc-fallback-test")
    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )

    section = CanonicalSection(
        id="sec-fallback",
        heading="Fallback Safety & Quality",
        heading_level=1,
        heading_path=("SOP", "Fallback Safety & Quality"),
        policy_number="SOP-FALLBACK-01",
        stable_key="key-sec-fallback",
        content_hash="hash-sec-fallback",
        blocks=[
            CanonicalBlock(
                id="b-fallback-1",
                kind=BlockKind.PARAGRAPH,
                text="This is an operational guideline verified under pure fallback token bounds.",
                source=dummy,
            ),
            CanonicalBlock(
                id="b-fallback-2",
                kind=BlockKind.PARAGRAPH,
                text="Specifications: Parameter A = 100, Parameter B = 200, Tolerance = +/- 2.5%.",
                source=dummy,
            ),
        ],
        source=dummy,
        access=scope,
    )
    sop = CanonicalSOP(
        id="sop-fallback",
        organization_id="ajt",
        policy_id="pol-fallback",
        version_id="ver-fallback",
        source_document_ids=["doc-fallback-test"],
        title="Fallback Verification SOP",
        sections=[section],
    )

    chunks = chunker.chunk(sop, "published")
    assert len(chunks) == 1
    assert chunks[0].id == "ver-fallback:sec-fallback:0"
    assert chunks[0].section_id == "sec-fallback"
    
    # Token count of the resulting chunk must obey limits in fallback mode
    tokens = chunker.count_embedding_tokens(chunks[0].text)
    assert tokens <= SemanticChunker.SOFT_TARGET_TOKENS
    assert tokens <= SemanticChunker.HARD_MAX_TOKENS

