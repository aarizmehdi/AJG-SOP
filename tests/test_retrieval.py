import pytest

from apps.api.app.config import Settings
from apps.api.app.models.organization import ApplicationRole, EmployeeProfile
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
    with pytest.raises(
        ValueError, match="EMBEDDING_PROVIDER must be e5 or pinecone_e5 in live mode"
    ):
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
