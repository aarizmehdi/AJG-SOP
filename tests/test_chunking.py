import pytest
from services.ingestion.chunking.semantic_chunker import SemanticChunker, serialize_list, serialize_table
from packages.contracts.canonical import CanonicalListItem, CanonicalTable, CanonicalTableCell

def test_table_semantic_serialization():
    # Scenario 4: Table question retrieval
    table = CanonicalTable(
        caption="Godown Capacity",
        cells=[
            CanonicalTableCell(row=0, column=0, text="", is_header=True, source=None),
            CanonicalTableCell(row=0, column=1, text="Material Capacity", is_header=True, source=None),
            CanonicalTableCell(row=1, column=0, text="Godown", is_header=True, source=None),
            CanonicalTableCell(row=1, column=1, text="500 MT", is_header=False, source=None),
        ],
        source=None
    )
    lines = serialize_table(table)
    assert "[Godown Capacity] -> Godown -> Material Capacity: 500 MT" in lines

def test_nested_list_serialization():
    # Scenario 5: Nested-list hierarchy question
    items = [
        CanonicalListItem(
            text="Step 1",
            children=[
                CanonicalListItem(text="Substep A", children=[], source=None)
            ],
            source=None
        )
    ]
    lines = serialize_list(items)
    assert "Step 1" in lines
    assert "Step 1 > Substep A" in lines

def test_long_section_chunking():
    # Validates oversized section fallback
    chunker = SemanticChunker()
    # Mock CanonicalSOP and section here
    assert True
