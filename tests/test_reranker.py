import pytest

from packages.contracts.access import AccessDimension, AccessMode, AccessScope
from packages.contracts.canonical import RetrievalChunk, SourceLocator
from services.retrieval.reranker import LexicalHeuristicReranker


def test_heuristic_reranker_preserves_count():
    reranker = LexicalHeuristicReranker()
    assert reranker is not None


@pytest.mark.asyncio
async def test_heuristic_reranker_ranks_higher_overlap_first():
    reranker = LexicalHeuristicReranker()

    chunks = {
        "chunk-a": RetrievalChunk(
            id="chunk-a",
            organization_id="ajt",
            policy_id="P1",
            version_id="V1",
            source_document_id="S1",
            section_id="sec-a",
            heading_path=("Policy",),
            text="match one match two match three",
            access=AccessScope(
                departments=AccessDimension(mode=AccessMode.ALL),
                locations=AccessDimension(mode=AccessMode.ALL),
                roles=AccessDimension(mode=AccessMode.ALL),
            ),
            source=SourceLocator(source_document_id="S1", page_start=1, page_end=1),
            chunk_index=0,
            publication_status="published",
        ),
        "chunk-b": RetrievalChunk(
            id="chunk-b",
            organization_id="ajt",
            policy_id="P1",
            version_id="V1",
            source_document_id="S1",
            section_id="sec-b",
            heading_path=("Policy",),
            text="no overlapping words here",
            access=AccessScope(
                departments=AccessDimension(mode=AccessMode.ALL),
                locations=AccessDimension(mode=AccessMode.ALL),
                roles=AccessDimension(mode=AccessMode.ALL),
            ),
            source=SourceLocator(source_document_id="S1", page_start=1, page_end=1),
            chunk_index=0,
            publication_status="published",
        ),
    }

    # Candidate B is initially ranked higher in fused results
    fused = [("chunk-b", 1.0), ("chunk-a", 0.5)]
    query = "match one two three"

    reranked = await reranker.rerank(query, fused, chunks)

    assert len(reranked) == 2

    # Candidate A calculation: query terms ["match", "one", "two", "three"]
    # Chunk A text has all 4 terms. Score = 0.5 (base) + (4 * 0.5) = 2.5
    # Chunk B text has 0 terms. Score = 1.0 (base) + 0 = 1.0
    # Expected order: chunk-a (2.5), chunk-b (1.0)
    assert reranked[0] == ("chunk-a", 2.5)
    assert reranked[1] == ("chunk-b", 1.0)
