import pytest

from apps.api.app.models.organization import ApplicationRole, EmployeeProfile
from apps.api.app.services.assistant_service import AssistantService
from apps.api.app.services.foundation_store import FoundationStore
from packages.contracts.access import AccessDimension, AccessMode, AccessScope
from packages.contracts.canonical import RetrievalChunk, SourceLocator
from packages.contracts.common import Language
from packages.contracts.policy import PolicyStatus, SOPPolicy, SOPVersion, VersionStatus
from services.assistant.answer_generator import FixtureLLMProvider
from services.assistant.answerability import FixtureAnswerabilityGate
from services.assistant.citations import CitationValidator
from services.assistant.grounding import GroundingVerifier
from services.ingestion.embeddings.base import FixtureEmbeddingProvider
from services.retrieval.authorization_filter import AuthorizationFilter
from services.retrieval.fusion import ReciprocalRankFusion
from services.retrieval.lexical_search import FixtureLexicalRetriever
from services.retrieval.reranker import FixtureReranker
from services.retrieval.retriever import RetrievalService
from services.retrieval.semantic_search import FixtureSemanticRetriever


@pytest.mark.asyncio
async def test_assistant_retrieval_and_citations_strictly_exclude_unauthorized_chunks() -> None:
    # 1. Setup store with one allowed chunk (Operations) and one restricted chunk (Executive)
    dummy_source = SourceLocator(source_document_id="doc-ops-1", page_start=1, page_end=2)
    ops_scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"Operations"})),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    exec_scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"Executive"})),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )

    allowed_text = (
        "General receiving protocol: inspect bills of lading and verify carton count upon delivery."
    )
    restricted_text = (
        "Executive confidential compensation protocol: "
        "discretionary bonus allocations are strictly private."
    )

    allowed_chunk = RetrievalChunk(
        id="chunk-ops-allowed",
        organization_id="ajt",
        policy_id="pol-ops",
        version_id="ver-ops-1",
        source_document_id="doc-ops-1",
        section_id="sec-general",
        heading_path=("Operations", "General Receiving"),
        policy_number="SOP-OPS-101",
        text=allowed_text,
        access=ops_scope,
        source=dummy_source,
        chunk_index=0,
        publication_status="published",
    )
    restricted_chunk = RetrievalChunk(
        id="chunk-exec-restricted",
        organization_id="ajt",
        policy_id="pol-ops",
        version_id="ver-ops-1",
        source_document_id="doc-ops-1",
        section_id="sec-confidential",
        heading_path=("Operations", "Executive Confidential Compensation"),
        policy_number="SOP-OPS-101",
        text=restricted_text,
        access=exec_scope,
        source=dummy_source,
        chunk_index=1,
        publication_status="published",
    )

    store = FoundationStore(
        policies={
            "pol-ops": SOPPolicy(
                id="pol-ops",
                organization_id="ajt",
                title="Operations and Governance SOP",
                category="Operations",
                status=PolicyStatus.ACTIVE,
                active_version_id="ver-ops-1",
            )
        },
        versions={
            "ver-ops-1": SOPVersion(
                id="ver-ops-1",
                organization_id="ajt",
                policy_id="pol-ops",
                version_label="1",
                status=VersionStatus.PUBLISHED,
                access=AccessScope(
                    departments=AccessDimension(mode=AccessMode.ALL),
                    locations=AccessDimension(mode=AccessMode.ALL),
                    roles=AccessDimension(mode=AccessMode.ALL),
                ),
            )
        },
        chunks={"ver-ops-1": [allowed_chunk, restricted_chunk]},
    )

    # 2. Build real RetrievalService
    auth_filter = AuthorizationFilter(store)
    retrieval_service = RetrievalService(
        store,
        auth_filter,
        FixtureLexicalRetriever(),
        FixtureSemanticRetriever(FixtureEmbeddingProvider()),
        ReciprocalRankFusion(),
        FixtureReranker(),
    )

    # 3. Build real AssistantService in fixture mode
    assistant = AssistantService(
        retrieval_service,
        FixtureAnswerabilityGate(),
        FixtureLLMProvider(),
        CitationValidator(),
        GroundingVerifier(),
    )

    # 4. Profile is an Operations employee (NOT Executive)
    employee = EmployeeProfile(
        id="emp-ops-01",
        organization_id="ajt",
        identity_subject="fixture|emp-ops-01",
        display_name="Operations Staff",
        email="ops@example.test",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
        departments=frozenset({"Operations"}),
        locations=frozenset({"Lahore"}),
        organizational_roles=frozenset({"Staff"}),
    )

    # 5. Query asking about executive compensation
    question = "What is the confidential compensation and bonus allocation protocol?"
    result, context = await assistant.answer_with_context(employee, question, Language.ENGLISH)

    # Assert that the restricted chunk never reached assistant context/evidence
    context_chunk_ids = [c.chunk_id for c in context]
    assert "chunk-exec-restricted" not in context_chunk_ids

    # Assert that citations do not reference the restricted chunk
    citation_ids = [c.chunk_id for c in result.citations]
    assert "chunk-exec-restricted" not in citation_ids

    # Assert answer text contains no confidential content from the restricted chunk
    assert "discretionary bonus" not in result.answer.lower()
    assert "strictly private" not in result.answer.lower()

    # 6. Verify that an allowed question DOES succeed and returns allowed chunk
    allowed_question = "How is general receiving conducted?"
    allowed_result, allowed_context = await assistant.answer_with_context(
        employee, allowed_question, Language.ENGLISH
    )
    assert any(c.chunk_id == "chunk-ops-allowed" for c in allowed_context)
    assert "chunk-exec-restricted" not in [c.chunk_id for c in allowed_context]
