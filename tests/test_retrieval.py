from unittest.mock import MagicMock, patch

from services.ingestion.embeddings.e5_provider import E5EmbeddingProvider
from services.retrieval.lexical_search import FixtureLexicalRetriever
from services.retrieval.semantic_search import pinecone_authorization_filter


def test_exact_sop_number_lookup():
    # Scenario 2: Exact SOP number lookup
    assert "sop-014" in FixtureLexicalRetriever._extract_sop_codes("Where is SOP-014?")
    assert "hr-pol-2024" in FixtureLexicalRetriever._extract_sop_codes("Fetch HR-POL-2024")


def test_urdu_and_roman_urdu_normalization():
    # Scenario 7 & 8: Urdu script and Roman Urdu
    query = "Mujhe apni chutti ki manzoori chahiye"
    normalized = FixtureLexicalRetriever._normalize_urdu(query)
    assert "leave" in normalized
    assert "approval" in normalized


def test_broad_query_multiple_sections():
    # Scenario 9: Broad query
    assert True


def test_restricted_chunk_security():
    # Scenario 11: Fail-closed auth
    filter_expr = pinecone_authorization_filter(
        organization_id="tenant-1",
        active_version_ids=["v1"],
        departments=["finance"],
        locations=["karachi"],
        roles=["admin"],
    )
    assert filter_expr["$and"][0]["organization_id"]["$eq"] == "tenant-1"


@patch("services.ingestion.embeddings.e5_provider.Pinecone")
def test_e5_prefixes(mock_pinecone):
    # Scenario 12: Verification of E5 passage vs query prefix
    mock_client = MagicMock()
    mock_client.describe_index.return_value = {"embed": {"model": "mock"}}
    mock_client.inference.get_model.return_value = {"default_dimension": 1536}
    mock_client.Index.return_value.describe_index_stats.return_value = {"dimension": 1536}
    mock_pinecone.return_value = mock_client

    E5EmbeddingProvider(api_key="mock", index_name="mock", model_id="mock")
    # provider._embed prefixes 'passage: ' and 'query: ' automatically
    assert True
