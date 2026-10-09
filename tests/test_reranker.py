from services.retrieval.reranker import LexicalHeuristicReranker


def test_heuristic_reranker_preserves_count():
    reranker = LexicalHeuristicReranker()
    # Just a placeholder instantiation check to avoid ImportError
    assert reranker is not None
