from packages.contracts.access import AccessDimension, AccessMode, AccessScope
from packages.contracts.canonical import (
    BlockKind,
    CanonicalBlock,
    CanonicalListItem,
    CanonicalSection,
    CanonicalSOP,
    CanonicalTable,
    CanonicalTableCell,
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
    chunker.MAX_WORDS = 25
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
                row=1, column=1, text="Row 1 B word " * 8, is_header=False, source=dummy
            ),
            CanonicalTableCell(row=2, column=0, text="Row 2 A", is_header=False, source=dummy),
            CanonicalTableCell(
                row=2, column=1, text="Row 2 B word " * 8, is_header=False, source=dummy
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
        "| Row 1 A | Row 1 B word Row 1 B word Row 1 B word Row 1 B word "
        "Row 1 B word Row 1 B word Row 1 B word Row 1 B word  |"
    )
    expected_chunk1 = (
        "Audit\n**Audit**\n| H A | H B |\n|---|---|\n"
        "| Row 2 A | Row 2 B word Row 2 B word Row 2 B word Row 2 B word "
        "Row 2 B word Row 2 B word Row 2 B word Row 2 B word  |"
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

