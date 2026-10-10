import pytest

from apps.api.app.config import Settings
from apps.api.app.models.organization import ApplicationRole, EmployeeProfile
from packages.contracts.canonical import RetrievalChunk
from packages.contracts.retrieval import CandidateChannel, RetrievalCandidate
from services.retrieval.authorization_filter import AuthorizationFilter
from services.retrieval.fusion import ReciprocalRankFusion
from services.retrieval.lexical_search import FixtureLexicalRetriever
from services.retrieval.semantic_search import pinecone_authorization_filter


def test_exact_sop_number_lookup():
    assert "sop-014" in FixtureLexicalRetriever._extract_sop_codes("Where is SOP-014?")
    assert "hr-pol-2024" in FixtureLexicalRetriever._extract_sop_codes("Fetch HR-POL-2024")


def test_urdu_and_roman_urdu_normalization():
    query = "Mujhe apni chutti ki manzoori chahiye"
    normalized = FixtureLexicalRetriever._normalize_urdu(query)
    assert "leave" in normalized
    assert "approval" in normalized


def test_system_admin_org_wide_access_pinecone_filter():
    profile = EmployeeProfile(
        id="admin-1",
        organization_id="tenant-1",
        identity_subject="auth0|123",
        display_name="Admin",
        email="admin@test.com",
        application_roles=frozenset({ApplicationRole.SYSTEM_ADMIN}),
        departments=frozenset(),
        locations=frozenset(),
        organizational_roles=frozenset(),
    )
    is_admin = AuthorizationFilter.is_organization_wide_reader(profile)

    filter_expr = pinecone_authorization_filter(
        organization_id=profile.organization_id,
        active_version_ids=["v1"],
        chunk_ids=["chunk-1"],
        departments=list(profile.departments),
        locations=list(profile.locations),
        roles=list(profile.organizational_roles),
        is_organization_wide_reader=is_admin,
    )

    # System admin filter must assert exact org, active versions, and publication status
    assert any(
        "organization_id" in c and c["organization_id"]["$eq"] == "tenant-1"
        for c in filter_expr["$and"]
    )
    assert any("version_id" in c and c["version_id"]["$in"] == ["v1"] for c in filter_expr["$and"])
    assert any(
        "publication_status" in c and c["publication_status"]["$eq"] == "published"
        for c in filter_expr["$and"]
    )

    # And MUST NOT contain $or clauses for departments/locations/roles
    for clause in filter_expr["$and"]:
        assert "$or" not in clause, (
            "System Admin filter should not restrict by departments/locations/roles"
        )


def test_employee_restricted_pinecone_filter():
    profile = EmployeeProfile(
        id="emp-1",
        organization_id="tenant-1",
        identity_subject="auth0|456",
        display_name="Emp",
        email="emp@test.com",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
        departments=frozenset({"finance"}),
        locations=frozenset({"karachi"}),
        organizational_roles=frozenset(),
    )
    is_admin = AuthorizationFilter.is_organization_wide_reader(profile)

    filter_expr = pinecone_authorization_filter(
        organization_id=profile.organization_id,
        active_version_ids=["v1"],
        chunk_ids=["chunk-1"],
        departments=list(profile.departments),
        locations=list(profile.locations),
        roles=list(profile.organizational_roles),
        is_organization_wide_reader=is_admin,
    )

    assert any(
        "organization_id" in c and c["organization_id"]["$eq"] == "tenant-1"
        for c in filter_expr["$and"]
    )

    # Should contain exact predicates for departments
    dept_clause = next(
        (
            c
            for c in filter_expr["$and"]
            if "$or" in c and any("departments" in d for d in c["$or"])
        ),
        None,
    )
    assert dept_clause is not None
    assert dept_clause["$or"][1]["departments"]["$in"] == ["finance"]


def test_fusion_preserves_same_section_distinct_chunks():
    profile = EmployeeProfile(
        id="emp-1",
        organization_id="tenant-1",
        identity_subject="auth0|456",
        display_name="Emp",
        email="emp@test.com",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
        departments=frozenset(),
        locations=frozenset(),
        organizational_roles=frozenset(),
    )

    # Two chunks from the same section (e.g. preamble and table)
    lexical = [
        RetrievalCandidate(
            tenant_id="tenant-1",
            organization_id="tenant-1",
            chunk_id="v1:sec1:0",
            channel=CandidateChannel.LEXICAL,
            score=10.0,
            rank=1,
            text="Preamble",
            policy_number="P-1",
            heading_path=["Heading 1"],
            allowed_roles=[],
            department=None,
        )
    ]
    semantic = [
        RetrievalCandidate(
            tenant_id="tenant-1",
            organization_id="tenant-1",
            chunk_id="v1:sec1:1",
            channel=CandidateChannel.SEMANTIC,
            score=0.9,
            rank=1,
            text="Table data",
            policy_number="P-1",
            heading_path=["Heading 1"],
            allowed_roles=[],
            department=None,
        )
    ]

    fusion = ReciprocalRankFusion()
    fused = fusion.fuse(lexical, semantic, profile)

    # Both unique chunks must survive
    assert len(fused) == 2
    chunk_ids = [c[0] for c in fused]
    assert "v1:sec1:0" in chunk_ids
    assert "v1:sec1:1" in chunk_ids


def test_fusion_same_channel_distinct_chunks_both_survive():
    profile = EmployeeProfile(
        id="emp-1",
        organization_id="tenant-1",
        identity_subject="auth0|456",
        display_name="Emp",
        email="emp@test.com",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
        departments=frozenset(),
        locations=frozenset(),
        organizational_roles=frozenset(),
    )

    def lexical_candidate(chunk_id: str, rank: int) -> RetrievalCandidate:
        return RetrievalCandidate(
            tenant_id="tenant-1",
            organization_id="tenant-1",
            chunk_id=chunk_id,
            channel=CandidateChannel.LEXICAL,
            score=10.0 - rank,
            rank=rank,
            text=f"text of {chunk_id}",
            policy_number="P-1",
            heading_path=["Heading 1"],
            allowed_roles=[],
            department=None,
        )

    lexical = [lexical_candidate("v1:sec1:0", 1), lexical_candidate("v1:sec1:1", 2)]

    fused = ReciprocalRankFusion().fuse(lexical, [], profile)

    assert [item[0] for item in fused] == ["v1:sec1:0", "v1:sec1:1"]


def test_fusion_exact_same_chunk_merges_and_scores():
    profile = EmployeeProfile(
        id="emp-1",
        organization_id="tenant-1",
        identity_subject="auth0|456",
        display_name="Emp",
        email="emp@test.com",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
        departments=frozenset(),
        locations=frozenset(),
        organizational_roles=frozenset(),
    )

    lexical = [
        RetrievalCandidate(
            tenant_id="tenant-1",
            organization_id="tenant-1",
            chunk_id="chunk-same",
            channel=CandidateChannel.LEXICAL,
            score=10.0,
            rank=1,
            text="Same exact chunk",
            policy_number="P-1",
            heading_path=["Heading 1"],
            allowed_roles=[],
            department=None,
        )
    ]
    semantic = [
        RetrievalCandidate(
            tenant_id="tenant-1",
            organization_id="tenant-1",
            chunk_id="chunk-same",
            channel=CandidateChannel.SEMANTIC,
            score=0.9,
            rank=1,
            text="Same exact chunk",
            policy_number="P-1",
            heading_path=["Heading 1"],
            allowed_roles=[],
            department=None,
        )
    ]

    fusion = ReciprocalRankFusion(rank_constant=60)
    fused = fusion.fuse(lexical, semantic, profile)

    # Must be merged into a single candidate
    assert len(fused) == 1
    assert fused[0][0] == "chunk-same"

    # RRF score = 1/(60 + 1) + 1/(60 + 1)
    expected_score = (1.0 / 61) + (1.0 / 61)
    assert fused[0][1] == pytest.approx(expected_score)


def test_live_configuration_validation():
    # Should raise ValueError for missing deepseek/pinecone credentials
    with pytest.raises(ValueError, match="Missing required live configuration"):
        Settings(app_mode="live", embedding_provider="e5", llm_provider="deepseek")

    # Should raise ValueError if embedding_provider is invalid for live
    with pytest.raises(ValueError, match="EMBEDDING_PROVIDER must be .* in live mode"):
        Settings(
            app_mode="live",
            embedding_provider="fixture",
            llm_provider="deepseek",
            pinecone_api_key="key",
            deepseek_api_key="key",
            s3_access_key_id="key",
            s3_secret_access_key="key",
            firebase_project_id="pid",
            firebase_service_account_json="{}",
            mongodb_uri="mongodb://remote:27017",
        )

    # Valid alias pinecone_e5
    settings = Settings(
        app_mode="live",
        embedding_provider="pinecone_e5",
        llm_provider="deepseek",
        pinecone_api_key="key",
        deepseek_api_key="key",
        s3_access_key_id="key",
        s3_secret_access_key="key",
        firebase_project_id="pid",
        firebase_service_account_json="{}",
        mongodb_uri="mongodb://remote:27017",
        web_origin="https://production.vercel.app",
    )
    assert settings.embedding_provider == "pinecone_e5"


def test_lexical_heading_vs_body_match():
    # Heading-only match vs body-content match retrieval.
    from packages.contracts.access import AccessDimension, AccessMode, AccessScope
    from packages.contracts.canonical import SourceLocator

    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    dummy_source = SourceLocator(source_document_id="doc1")

    chunk_heading = RetrievalChunk(
        id="chunk-heading",
        organization_id="tenant-1",
        policy_id="pol1",
        version_id="v1",
        source_document_id="doc1",
        section_id="sec1",
        heading_path=("Special Secret Project Alpha",),
        text="Special Secret Project Alpha\nThis section discusses general things.",
        access=scope,
        source=dummy_source,
        chunk_index=0,
        publication_status="published",
    )
    chunk_body = RetrievalChunk(
        id="chunk-body",
        organization_id="tenant-1",
        policy_id="pol1",
        version_id="v1",
        source_document_id="doc1",
        section_id="sec2",
        heading_path=("General",),
        text="This text discusses Special Secret Project Alpha in detail.",
        access=scope,
        source=dummy_source,
        chunk_index=0,
        publication_status="published",
    )

    retriever = FixtureLexicalRetriever()

    import asyncio

    candidates = asyncio.run(
        retriever.search("Special Secret Project Alpha", [chunk_heading, chunk_body], 10)
    )

    assert len(candidates) == 2
    # Body match ranks first: it has the exact phrase and repeated terms.
    assert candidates[0].chunk_id == "chunk-body"
    assert candidates[1].chunk_id == "chunk-heading"


@pytest.mark.asyncio
async def test_urdu_script_and_roman_urdu_retrieval():
    from packages.contracts.access import AccessDimension, AccessMode, AccessScope
    from packages.contracts.canonical import SourceLocator

    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    dummy_source = SourceLocator(source_document_id="doc1")

    chunk_urdu = RetrievalChunk(
        id="chunk-urdu",
        organization_id="tenant-1",
        policy_id="pol1",
        version_id="v1",
        source_document_id="doc1",
        section_id="sec1",
        heading_path=("Leave",),
        text="Employees are entitled to annual leave.",
        access=scope,
        source=dummy_source,
        chunk_index=0,
        publication_status="published",
    )

    retriever = FixtureLexicalRetriever()

    # Roman Urdu query
    candidates_roman = await retriever.search("Mujhe chutti chahiye", [chunk_urdu], 10)
    assert len(candidates_roman) == 1
    assert candidates_roman[0].chunk_id == "chunk-urdu"
    # Urdu script query retrieves only the chunk with the Urdu term.
    chunk_urdu_script = RetrievalChunk(
        id="chunk-urdu-script",
        organization_id="tenant-1",
        policy_id="pol1",
        version_id="v1",
        source_document_id="doc1",
        section_id="sec2",
        heading_path=("Leave",),
        text="ملازمین کو سالانہ چھٹی کا حق حاصل ہے۔",
        access=scope,
        source=dummy_source,
        chunk_index=0,
        publication_status="published",
    )
    candidates_script = await retriever.search("مجھے چھٹی چاہیے", [chunk_urdu_script], 10)
    assert len(candidates_script) == 1
    assert candidates_script[0].chunk_id == "chunk-urdu-script"


@pytest.mark.asyncio
async def test_broad_query_returns_multiple_sections():
    # Broad query that must return chunks from at least two different sections.
    from packages.contracts.access import AccessDimension, AccessMode, AccessScope
    from packages.contracts.canonical import SourceLocator

    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    dummy_source = SourceLocator(source_document_id="doc1")

    chunk_1 = RetrievalChunk(
        id="chunk-1",
        organization_id="tenant-1",
        policy_id="pol1",
        version_id="v1",
        source_document_id="doc1",
        section_id="sec1",
        heading_path=("Safety",),
        text="General safety guidelines for the company.",
        access=scope,
        source=dummy_source,
        chunk_index=0,
        publication_status="published",
    )
    chunk_2 = RetrievalChunk(
        id="chunk-2",
        organization_id="tenant-1",
        policy_id="pol1",
        version_id="v1",
        source_document_id="doc1",
        section_id="sec2",
        heading_path=("Safety", "Fire"),
        text="Fire safety rules and evacuation plan.",
        access=scope,
        source=dummy_source,
        chunk_index=0,
        publication_status="published",
    )

    retriever = FixtureLexicalRetriever()

    candidates = await retriever.search("safety guidelines rules", [chunk_1, chunk_2], 10)
    assert len(candidates) == 2
    assert {c.chunk_id for c in candidates} == {"chunk-1", "chunk-2"}


@pytest.mark.asyncio
async def test_long_section_late_chunk_retrieval():
    # Target chunk with answer is late in sequence; full retrieval still finds it.
    from apps.api.app.services.foundation_store import FoundationStore
    from packages.contracts.access import AccessDimension, AccessMode, AccessScope
    from packages.contracts.canonical import SourceLocator
    from packages.contracts.policy import PolicyStatus, SOPPolicy, SOPVersion, VersionStatus
    from services.ingestion.embeddings.base import FixtureEmbeddingProvider
    from services.retrieval.reranker import LexicalHeuristicReranker
    from services.retrieval.retriever import RetrievalService
    from services.retrieval.semantic_search import FixtureSemanticRetriever

    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    dummy_source = SourceLocator(source_document_id="doc1")

    chunk_early = RetrievalChunk(
        id="chunk-early",
        organization_id="tenant-1",
        policy_id="pol1",
        version_id="v1",
        source_document_id="doc1",
        section_id="sec1",
        heading_path=("Very Long Section",),
        text="This is the early part of the section with filler text.",
        access=scope,
        source=dummy_source,
        chunk_index=0,
        publication_status="published",
    )
    chunk_late = RetrievalChunk(
        id="chunk-late",
        organization_id="tenant-1",
        policy_id="pol1",
        version_id="v1",
        source_document_id="doc1",
        section_id="sec1",
        heading_path=("Very Long Section",),
        text="Here is the target fact you seek regarding the specific issue.",
        access=scope,
        source=dummy_source,
        chunk_index=1,
        publication_status="published",
    )

    store = FoundationStore(
        policies={
            "pol1": SOPPolicy(
                id="pol1",
                organization_id="tenant-1",
                title="Pol",
                category="Ops",
                status=PolicyStatus.ACTIVE,
                active_version_id="v1",
            )
        },
        versions={
            "v1": SOPVersion(
                id="v1",
                organization_id="tenant-1",
                policy_id="pol1",
                version_label="1",
                status=VersionStatus.PUBLISHED,
                access=scope,
            )
        },
        chunks={"v1": [chunk_early, chunk_late]},
    )

    profile = EmployeeProfile(
        id="emp",
        organization_id="tenant-1",
        identity_subject="sub",
        display_name="Emp",
        email="a@b.com",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
    )

    service = RetrievalService(
        store=store,
        authorization=AuthorizationFilter(store),
        lexical=FixtureLexicalRetriever(),
        semantic=FixtureSemanticRetriever(FixtureEmbeddingProvider()),
        fusion=ReciprocalRankFusion(),
        reranker=LexicalHeuristicReranker(),
    )

    results = await service.retrieve(profile, "target fact specific issue", limit=5)

    assert len(results) > 0
    # Assert the late chunk is returned as evidence
    assert any(ev.chunk_id == "chunk-late" for ev in results)


@pytest.mark.asyncio
async def test_table_row_value_retrieval():
    # Assert row value queries retrieve correctly from tables split across multiple chunks.
    from apps.api.app.services.foundation_store import FoundationStore
    from packages.contracts.access import AccessDimension, AccessMode, AccessScope
    from packages.contracts.canonical import SourceLocator
    from packages.contracts.policy import PolicyStatus, SOPPolicy, SOPVersion, VersionStatus
    from services.ingestion.embeddings.base import FixtureEmbeddingProvider
    from services.retrieval.reranker import LexicalHeuristicReranker
    from services.retrieval.retriever import RetrievalService
    from services.retrieval.semantic_search import FixtureSemanticRetriever

    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    dummy_source = SourceLocator(source_document_id="doc1")

    chunk_1 = RetrievalChunk(
        id="chunk-t1",
        organization_id="tenant-1",
        policy_id="pol1",
        version_id="v1",
        source_document_id="doc1",
        section_id="sec1",
        heading_path=("Table Section",),
        text="**Large Table**\n| Header A | Header B |\n|---|---|\n| Row 1 Data | Values 1 |",
        access=scope,
        source=dummy_source,
        chunk_index=0,
        publication_status="published",
    )
    chunk_2 = RetrievalChunk(
        id="chunk-t2",
        organization_id="tenant-1",
        policy_id="pol1",
        version_id="v1",
        source_document_id="doc1",
        section_id="sec1",
        heading_path=("Table Section",),
        text="**Large Table**\n| Header A | Header B |\n|---|---|\n| Row 2 Data | Values 2 |",
        access=scope,
        source=dummy_source,
        chunk_index=1,
        publication_status="published",
    )

    store = FoundationStore(
        policies={
            "pol1": SOPPolicy(
                id="pol1",
                organization_id="tenant-1",
                title="Pol",
                category="Ops",
                status=PolicyStatus.ACTIVE,
                active_version_id="v1",
            )
        },
        versions={
            "v1": SOPVersion(
                id="v1",
                organization_id="tenant-1",
                policy_id="pol1",
                version_label="1",
                status=VersionStatus.PUBLISHED,
                access=scope,
            )
        },
        chunks={"v1": [chunk_1, chunk_2]},
    )

    profile = EmployeeProfile(
        id="emp",
        organization_id="tenant-1",
        identity_subject="sub",
        display_name="Emp",
        email="a@b.com",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
    )

    service = RetrievalService(
        store=store,
        authorization=AuthorizationFilter(store),
        lexical=FixtureLexicalRetriever(),
        semantic=FixtureSemanticRetriever(FixtureEmbeddingProvider()),
        fusion=ReciprocalRankFusion(),
        reranker=LexicalHeuristicReranker(),
    )

    results = await service.retrieve(profile, "Header B Values 2", limit=5)

    assert len(results) > 0
    # Must retrieve the chunk that has the row value
    assert any(ev.chunk_id == "chunk-t2" for ev in results)


async def test_nested_list_retrieval():
    from apps.api.app.models.organization import ApplicationRole, EmployeeProfile
    from apps.api.app.services.foundation_store import FoundationStore
    from packages.contracts.access import AccessDimension, AccessMode, AccessScope
    from packages.contracts.canonical import (
        BlockKind,
        CanonicalBlock,
        CanonicalListItem,
        CanonicalSection,
        CanonicalSOP,
        SourceLocator,
    )
    from packages.contracts.policy import PolicyStatus, SOPPolicy, SOPVersion, VersionStatus
    from services.ingestion.chunking.semantic_chunker import SectionAwareFixtureChunker
    from services.ingestion.embeddings.base import FixtureEmbeddingProvider
    from services.retrieval.authorization_filter import AuthorizationFilter
    from services.retrieval.fusion import ReciprocalRankFusion
    from services.retrieval.lexical_search import FixtureLexicalRetriever
    from services.retrieval.reranker import LexicalHeuristicReranker
    from services.retrieval.retriever import RetrievalService
    from services.retrieval.semantic_search import FixtureSemanticRetriever

    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    dummy_source = SourceLocator(source_document_id="doc1")

    doc = CanonicalSOP(
        id="doc1",
        organization_id="tenant-1",
        policy_id="pol1",
        version_id="v1",
        source_document_ids=["doc1"],
        title="Test SOP",
        sections=[
            CanonicalSection(
                id="sec1",
                heading="List Section",
                heading_level=1,
                heading_path=["List Section"],
                stable_key="sec1-key",
                content_hash="sec1-hash",
                blocks=[
                    CanonicalBlock(
                        id="b1",
                        kind=BlockKind.UNORDERED_LIST,
                        list_items=[
                            CanonicalListItem(
                                text="Parent Item",
                                children=[
                                    CanonicalListItem(
                                        text="Child Item A",
                                        children=[
                                            CanonicalListItem(
                                                text="Deep Item B", children=[], source=dummy_source
                                            )
                                        ],
                                        source=dummy_source,
                                    )
                                ],
                                source=dummy_source,
                            )
                        ],
                        source=dummy_source,
                    )
                ],
                source=dummy_source,
                access=scope,
            )
        ],
    )

    chunker = SectionAwareFixtureChunker()
    chunks = chunker.chunk(doc, "published")

    store = FoundationStore(
        policies={
            "pol1": SOPPolicy(
                id="pol1",
                organization_id="tenant-1",
                title="Pol",
                category="Ops",
                status=PolicyStatus.ACTIVE,
                active_version_id="v1",
            )
        },
        versions={
            "v1": SOPVersion(
                id="v1",
                organization_id="tenant-1",
                policy_id="pol1",
                version_label="1",
                status=VersionStatus.PUBLISHED,
                access=scope,
            )
        },
        chunks={"v1": chunks},
    )

    profile = EmployeeProfile(
        id="user1",
        organization_id="tenant-1",
        identity_subject="auth0|user1",
        display_name="Emp",
        email="a@b.com",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
    )

    service = RetrievalService(
        store=store,
        authorization=AuthorizationFilter(store),
        lexical=FixtureLexicalRetriever(),
        semantic=FixtureSemanticRetriever(FixtureEmbeddingProvider()),
        fusion=ReciprocalRankFusion(),
        reranker=LexicalHeuristicReranker(),
    )

    results = await service.retrieve(profile, "Deep Item B", limit=5)
    assert len(results) == 1
    assert "Parent Item" in results[0].excerpt
    assert "Deep Item B" in results[0].excerpt


async def test_retrieval_abstains_when_no_evidence_matches():
    from apps.api.app.models.organization import ApplicationRole, EmployeeProfile
    from apps.api.app.services.foundation_store import FoundationStore
    from packages.contracts.access import AccessDimension, AccessMode, AccessScope
    from packages.contracts.canonical import RetrievalChunk, SourceLocator
    from packages.contracts.policy import PolicyStatus, SOPPolicy, SOPVersion, VersionStatus
    from services.ingestion.embeddings.base import FixtureEmbeddingProvider
    from services.retrieval.authorization_filter import AuthorizationFilter
    from services.retrieval.fusion import ReciprocalRankFusion
    from services.retrieval.lexical_search import FixtureLexicalRetriever
    from services.retrieval.reranker import LexicalHeuristicReranker
    from services.retrieval.retriever import RetrievalService
    from services.retrieval.semantic_search import FixtureSemanticRetriever

    scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    dummy_source = SourceLocator(source_document_id="doc1")

    chunk = RetrievalChunk(
        id="chunk-unrelated",
        organization_id="tenant-1",
        policy_id="pol1",
        version_id="v1",
        source_document_id="doc1",
        section_id="sec1",
        heading_path=("Unrelated",),
        text="This is a perfectly normal chunk about office supplies and staplers.",
        access=scope,
        source=dummy_source,
        chunk_index=0,
        publication_status="published",
    )

    store = FoundationStore(
        policies={
            "pol1": SOPPolicy(
                id="pol1",
                organization_id="tenant-1",
                title="Pol",
                category="Ops",
                status=PolicyStatus.ACTIVE,
                active_version_id="v1",
            )
        },
        versions={
            "v1": SOPVersion(
                id="v1",
                organization_id="tenant-1",
                policy_id="pol1",
                version_label="1",
                status=VersionStatus.PUBLISHED,
                access=scope,
            )
        },
        chunks={"v1": [chunk]},
    )
    profile = EmployeeProfile(
        id="user1",
        organization_id="tenant-1",
        identity_subject="auth0|user1",
        display_name="Emp",
        email="a@b.com",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
    )

    embeddings = FixtureEmbeddingProvider()
    # Mock to prevent random hash collisions in testing
    import unittest.mock

    embeddings._vector = unittest.mock.MagicMock(return_value=[0.0] * 32)

    service = RetrievalService(
        store=store,
        authorization=AuthorizationFilter(store),
        lexical=FixtureLexicalRetriever(),
        semantic=FixtureSemanticRetriever(embeddings),
        fusion=ReciprocalRankFusion(),
        reranker=LexicalHeuristicReranker(),
    )

    results = await service.retrieve(profile, "Completely random nonsense", limit=5)
    assert len(results) == 0
