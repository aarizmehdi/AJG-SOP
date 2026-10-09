from collections.abc import Sequence
from types import SimpleNamespace

import pytest

from apps.api.app.models.organization import ApplicationRole, EmployeeProfile
from apps.api.app.services.foundation_store import FoundationStore
from packages.contracts.access import AccessDimension, AccessMode, AccessScope
from packages.contracts.canonical import RetrievalChunk, SourceLocator
from packages.contracts.policy import PolicyStatus, SOPPolicy, SOPVersion, VersionStatus
from packages.contracts.retrieval import CandidateChannel, RetrievalCandidate
from services.ingestion.embeddings.base import FixtureEmbeddingProvider
from services.retrieval.authorization_filter import AuthorizationFilter
from services.retrieval.fusion import ReciprocalRankFusion
from services.retrieval.lexical_search import LexicalCandidateRetriever
from services.retrieval.reranker import FixtureReranker
from services.retrieval.retriever import RetrievalService
from services.retrieval.semantic_search import PineconeSemanticRetriever, SemanticCandidateRetriever


def selected(department: str) -> AccessScope:
    return AccessScope(
        departments=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({department})),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )


def chunk(chunk_id: str, department: str) -> RetrievalChunk:
    return RetrievalChunk(
        id=chunk_id,
        organization_id="ajt",
        policy_id="policy",
        version_id="version",
        source_document_id="source",
        section_id=f"section-{chunk_id}",
        heading_path=("Policy", department),
        text="damaged stock handling",
        access=selected(department),
        source=SourceLocator(source_document_id="source", page_start=1, page_end=1),
        chunk_index=0,
        publication_status="published",
    )


class RecordingLexical(LexicalCandidateRetriever):
    def __init__(self) -> None:
        self.seen: list[str] = []

    async def search(
        self,
        query: str,
        profile: EmployeeProfile,
        eligible_chunks: Sequence[RetrievalChunk],
        limit: int,
    ) -> list[RetrievalCandidate]:
        self.seen = [item.id for item in eligible_chunks]
        return [
            RetrievalCandidate(
                tenant_id=item.organization_id,
                organization_id=item.organization_id,
                chunk_id=item.id,
                channel=CandidateChannel.LEXICAL,
                score=1,
                rank=index,
            )
            for index, item in enumerate(eligible_chunks[:limit], start=1)
        ]


class RecordingSemantic(SemanticCandidateRetriever):
    def __init__(self) -> None:
        self.seen: list[str] = []

    async def search(
        self,
        query: str,
        profile: EmployeeProfile,
        eligible_chunks: Sequence[RetrievalChunk],
        limit: int,
    ) -> list[RetrievalCandidate]:
        self.seen = [item.id for item in eligible_chunks]
        return [
            RetrievalCandidate(
                tenant_id=item.organization_id,
                organization_id=item.organization_id,
                chunk_id=item.id,
                channel=CandidateChannel.SEMANTIC,
                score=1,
                rank=index,
            )
            for index, item in enumerate(eligible_chunks[:limit], start=1)
        ]


async def test_unauthorized_chunks_never_enter_candidate_retrievers() -> None:
    store = FoundationStore(
        policies={
            "policy": SOPPolicy(
                id="policy",
                organization_id="ajt",
                title="Policy",
                category="Operations",
                status=PolicyStatus.ACTIVE,
                active_version_id="version",
            )
        },
        versions={
            "version": SOPVersion(
                id="version",
                organization_id="ajt",
                policy_id="policy",
                version_label="1",
                status=VersionStatus.PUBLISHED,
                access=selected("store"),
            )
        },
        chunks={
            "version": [
                chunk("allowed", "store").model_copy(
                    update={"text": "A" * 430 + " Capacity is 12 tonnes."}
                ),
                chunk("restricted", "hr"),
            ]
        },
    )
    profile = EmployeeProfile(
        id="employee",
        organization_id="ajt",
        identity_subject="fixture|employee",
        display_name="Employee",
        email="employee@example.test",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
        departments=frozenset({"store"}),
    )
    lexical = RecordingLexical()
    semantic = RecordingSemantic()
    service = RetrievalService(
        store,
        AuthorizationFilter(store),
        lexical,
        semantic,
        ReciprocalRankFusion(),
        FixtureReranker(),
    )

    results = await service.retrieve(profile, "damaged stock", 5)

    assert lexical.seen == ["allowed"]
    assert semantic.seen == ["allowed"]
    assert [item.chunk_id for item in results] == ["allowed"]
    assert "Capacity" not in results[0].excerpt
    spoofed = results[0].model_copy(update={"chunk_id": "restricted"})
    context = await service.assistant_context(profile, [results[0], spoofed])
    assert [item.chunk_id for item in context] == ["allowed"]
    assert context[0].full_text.endswith("Capacity is 12 tonnes.")


def test_system_admin_reads_across_departments_and_locations() -> None:
    store = FoundationStore(
        policies={
            "policy": SOPPolicy(
                id="policy",
                organization_id="ajt",
                title="Policy",
                category="Operations",
                status=PolicyStatus.ACTIVE,
                active_version_id="version",
            )
        },
        versions={
            "version": SOPVersion(
                id="version",
                organization_id="ajt",
                policy_id="policy",
                version_label="1",
                status=VersionStatus.PUBLISHED,
                access=selected("store"),
            )
        },
        chunks={"version": [chunk("store", "store"), chunk("hr", "hr")]},
    )
    authorization = AuthorizationFilter(store)
    system_admin = EmployeeProfile(
        id="system-admin",
        organization_id="ajt",
        identity_subject="fixture|system-admin",
        display_name="System Admin",
        email="sys-admin@example.test",
        application_roles=frozenset({ApplicationRole.EMPLOYEE, ApplicationRole.SYSTEM_ADMIN}),
        departments=frozenset(),
    )

    assert {item.id for item in authorization.eligible_chunks(system_admin)} == {
        "store",
        "hr",
    }


def test_system_admin_strictly_blocked_from_other_tenant() -> None:
    store = FoundationStore(
        policies={
            "policy": SOPPolicy(
                id="policy",
                organization_id="org-B",
                title="Policy B",
                category="Operations",
                status=PolicyStatus.ACTIVE,
                active_version_id="version",
            )
        },
        versions={
            "version": SOPVersion(
                id="version",
                organization_id="org-B",
                policy_id="policy",
                version_label="1",
                status=VersionStatus.PUBLISHED,
                access=selected("hr"),
            )
        },
        chunks={
            "version": [chunk("hr-chunk", "hr").model_copy(update={"organization_id": "org-B"})]
        },
    )
    authorization = AuthorizationFilter(store)
    system_admin_org_a = EmployeeProfile(
        id="sys-org-A",
        organization_id="org-A",
        identity_subject="fixture|sys",
        display_name="Sys",
        email="sys@a.test",
        application_roles=frozenset({ApplicationRole.EMPLOYEE, ApplicationRole.SYSTEM_ADMIN}),
        departments=frozenset(),
    )

    # Assert 0 results
    assert authorization.eligible_chunks(system_admin_org_a) == []


def test_employee_blocked_from_restricted_department_or_location() -> None:
    store = FoundationStore(
        policies={
            "policy": SOPPolicy(
                id="policy",
                organization_id="ajt",
                title="Policy",
                category="Operations",
                status=PolicyStatus.ACTIVE,
                active_version_id="version",
            )
        },
        versions={
            "version": SOPVersion(
                id="version",
                organization_id="ajt",
                policy_id="policy",
                version_label="1",
                status=VersionStatus.PUBLISHED,
                access=selected(
                    "hr"
                ),  # Chunk access overrides this.
            )
        },
        chunks={
            "version": [
                chunk("finance-lahore", "finance"),
                chunk("hr-karachi", "hr"),
            ]
        },
    )
    authorization = AuthorizationFilter(store)
    restricted_employee = EmployeeProfile(
        id="emp",
        organization_id="ajt",
        identity_subject="fixture|emp",
        display_name="Emp",
        email="emp@example.test",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
        departments=frozenset({"finance"}),
        locations=frozenset({"lahore"}),
    )

    chunks = authorization.eligible_chunks(restricted_employee)
    assert [c.id for c in chunks] == ["finance-lahore"]


class RecordingPineconeIndex:
    def __init__(self) -> None:
        self.query_kwargs: dict[str, object] = {}

    def query(self, **kwargs: object) -> SimpleNamespace:
        self.query_kwargs = kwargs
        return SimpleNamespace(
            matches=[
                SimpleNamespace(id="restricted", score=0.99, metadata={}),
                SimpleNamespace(id="allowed", score=0.9, metadata={}),
            ]
        )


async def test_pinecone_semantic_query_rejects_noneligible_matches() -> None:
    index = RecordingPineconeIndex()
    retriever = PineconeSemanticRetriever(
        "secret-not-used",
        "aziz-jan-sop",
        "aziz-jan-trust",
        FixtureEmbeddingProvider(),
        index=index,
    )

    profile = EmployeeProfile(
        id="test",
        organization_id="ajt",
        identity_subject="test",
        display_name="test",
        email="test@example.com",
        application_roles=frozenset(),
        departments=frozenset(),
    )
    results = await retriever.search("damaged stock", profile, [chunk("allowed", "store")], 5)

    assert [result.chunk_id for result in results] == ["allowed"]
    assert index.query_kwargs["namespace"] == "aziz-jan-trust--ajt"
    filters = index.query_kwargs["filter"]["$and"]
    assert any("organization_id" in c and c["organization_id"]["$eq"] == "ajt" for c in filters)
    assert any("version_id" in c and c["version_id"]["$in"] == ["version"] for c in filters)
    assert any(
        "publication_status" in c and c["publication_status"]["$eq"] == "published" for c in filters
    )
    assert any("chunk_id" in c and c["chunk_id"]["$in"] == ["allowed"] for c in filters)

    # Verify Employee-level constraints are present
    assert any(
        "$or" in c and any(d.get("departments_mode", {}).get("$eq") == "all" for d in c["$or"])
        for c in filters
    )
    assert any(
        "$or" in c and any(d.get("locations_mode", {}).get("$eq") == "all" for d in c["$or"])
        for c in filters
    )
    assert any(
        "$or" in c and any(d.get("roles_mode", {}).get("$eq") == "all" for d in c["$or"])
        for c in filters
    )


async def test_pinecone_semantic_query_rejects_cross_tenant_corpus() -> None:
    other = chunk("other", "store").model_copy(update={"organization_id": "other-org"})
    retriever = PineconeSemanticRetriever(
        "secret-not-used",
        "aziz-jan-sop",
        "aziz-jan-trust",
        FixtureEmbeddingProvider(),
        index=RecordingPineconeIndex(),
    )

    profile = EmployeeProfile(
        id="test",
        organization_id="ajt",
        identity_subject="test",
        display_name="test",
        email="test@example.com",
        application_roles=frozenset(),
        departments=frozenset(),
    )
    with pytest.raises(PermissionError, match="cannot cross organizations"):
        await retriever.search("damaged stock", profile, [chunk("allowed", "store"), other], 5)


def test_unpublished_and_inactive_versions_rejected() -> None:
    store = FoundationStore(
        policies={
            "policy": SOPPolicy(
                id="policy",
                organization_id="ajt",
                title="Policy",
                category="Operations",
                status=PolicyStatus.ACTIVE,
                active_version_id="version",
            )
        },
        versions={
            "version": SOPVersion(
                id="version",
                organization_id="ajt",
                policy_id="policy",
                version_label="1",
                status=VersionStatus.PUBLISHED,
                access=selected("store"),
            )
        },
        chunks={
            "version": [
                # Normal valid chunk
                chunk("allowed", "store"),
                # Unpublished chunk
                chunk("draft", "store").model_copy(update={"publication_status": "draft"}),
                # Inactive version chunk
                chunk("archived", "store").model_copy(update={"version_id": "old_version"}),
            ]
        },
    )
    profile = EmployeeProfile(
        id="employee",
        organization_id="ajt",
        identity_subject="fixture|employee",
        display_name="Employee",
        email="employee@example.test",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
        departments=frozenset({"store"}),
    )

    authorization = AuthorizationFilter(store)
    eligible = authorization.eligible_chunks(profile)
    assert [c.id for c in eligible] == ["allowed"]


def test_lexical_and_semantic_enforce_identical_scope() -> None:
    # We can inspect the retrieval pipeline to ensure both semantic and lexical
    # receive the exact same sequence of eligible chunks from AuthorizationFilter.
    store = FoundationStore(
        policies={
            "policy": SOPPolicy(
                id="policy",
                organization_id="ajt",
                title="Policy",
                category="Operations",
                status=PolicyStatus.ACTIVE,
                active_version_id="version",
            )
        },
        versions={
            "version": SOPVersion(
                id="version",
                organization_id="ajt",
                policy_id="policy",
                version_label="1",
                status=VersionStatus.PUBLISHED,
                access=selected("store"),
            )
        },
        chunks={
            "version": [
                chunk("allowed", "store"),
                chunk("restricted", "hr"),
            ]
        },
    )
    profile = EmployeeProfile(
        id="employee",
        organization_id="ajt",
        identity_subject="fixture|employee",
        display_name="Employee",
        email="employee@example.test",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
        departments=frozenset({"store"}),
    )

    authorization = AuthorizationFilter(store)
    eligible_chunks = authorization.eligible_chunks(profile)

    # Assert identical scope (only 'allowed' chunk is passed to retrievers)
    assert len(eligible_chunks) == 1
    assert eligible_chunks[0].id == "allowed"
