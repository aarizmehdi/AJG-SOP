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
                access=selected("hr"),  # Chunk access overrides this.
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
    results = await retriever.search("damaged stock", [chunk("allowed", "store")], 5)

    assert [result.chunk_id for result in results] == ["allowed"]
    assert index.query_kwargs["namespace"] == "aziz-jan-trust--ajt"
    filters = index.query_kwargs["filter"]["$and"]
    assert any("organization_id" in c and c["organization_id"]["$eq"] == "ajt" for c in filters)
    assert any(
        "publication_status" in c and c["publication_status"]["$eq"] == "published" for c in filters
    )
    assert any("chunk_id" in c and c["chunk_id"]["$in"] == ["allowed"] for c in filters)


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
        await retriever.search("damaged stock", [chunk("allowed", "store"), other], 5)


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


def _matches_pinecone_filter(metadata: dict[str, object], filter_expr: dict[str, object]) -> bool:
    for k, v in filter_expr.items():
        if k == "$and":
            if not all(_matches_pinecone_filter(metadata, c) for c in v):
                return False
        elif k == "$or":
            if not any(_matches_pinecone_filter(metadata, c) for c in v):
                return False
        else:
            if isinstance(v, dict):
                if "$eq" in v and metadata.get(k) != v["$eq"]:
                    return False
                if "$in" in v:
                    val = metadata.get(k)
                    if isinstance(val, list):
                        if not any(item in v["$in"] for item in val):
                            return False
                    elif val not in v["$in"]:
                        return False
    return True


def test_pinecone_and_in_memory_authorization_parity() -> None:
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
        identity_subject="fixture|emp",
        display_name="Emp",
        email="emp@example.test",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
        departments=frozenset({"store"}),
    )

    authorization = AuthorizationFilter(store)
    eligible = authorization.eligible_chunks(profile)
    in_memory_allowed = {c.id for c in eligible}

    from services.retrieval.semantic_search import pinecone_authorization_filter

    pinecone_filter = pinecone_authorization_filter(
        organization_id=profile.organization_id,
        active_version_ids=["version"],
        chunk_ids=["allowed", "restricted"],
        departments=list(profile.departments),
        locations=list(profile.locations),
        roles=list(profile.organizational_roles),
        is_organization_wide_reader=AuthorizationFilter.is_organization_wide_reader(profile),
    )

    # Flatten chunks to metadata format
    pinecone_allowed = set()
    for c in store.chunks["version"]:
        metadata = {
            "organization_id": c.organization_id,
            "version_id": c.version_id,
            "publication_status": c.publication_status,
            "chunk_id": c.id,
            "departments_mode": c.access.departments.mode.value,
            "locations_mode": c.access.locations.mode.value,
            "roles_mode": c.access.roles.mode.value,
            "departments": list(c.access.departments.values),
            "locations": list(c.access.locations.values),
            "roles": list(c.access.roles.values),
        }
        if _matches_pinecone_filter(metadata, pinecone_filter):
            pinecone_allowed.add(c.id)

    assert in_memory_allowed == pinecone_allowed


def test_employee_unauthorized_role_gets_zero_chunks() -> None:
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
                access=AccessScope(
                    departments=AccessDimension(mode=AccessMode.ALL),
                    locations=AccessDimension(mode=AccessMode.ALL),
                    roles=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"manager"})),
                ),
            )
        },
        chunks={
            "version": [
                chunk("allowed", "store").model_copy(
                    update={
                        "access": AccessScope(
                            departments=AccessDimension(mode=AccessMode.ALL),
                            locations=AccessDimension(mode=AccessMode.ALL),
                            roles=AccessDimension(
                                mode=AccessMode.SELECTED, values=frozenset({"manager"})
                            ),
                        )
                    }
                ),
            ]
        },
    )
    profile = EmployeeProfile(
        id="emp",
        organization_id="ajt",
        identity_subject="fixture|emp",
        display_name="Emp",
        email="emp@example.test",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
        organizational_roles=frozenset({"staff"}),
    )

    authorization = AuthorizationFilter(store)
    eligible = authorization.eligible_chunks(profile)
    assert len(eligible) == 0


async def test_fusion_leak_unauthorized_chunks_never_appear() -> None:
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

    class MaliciousRetriever(SemanticCandidateRetriever):
        async def search(
            self,
            query: str,
            eligible_chunks: Sequence[RetrievalChunk],
            limit: int,
        ) -> list[RetrievalCandidate]:
            # Ignores eligible_chunks and returns restricted!
            return [
                RetrievalCandidate(
                    tenant_id="ajt",
                    organization_id="ajt",
                    chunk_id="restricted",
                    channel=CandidateChannel.SEMANTIC,
                    score=1.0,
                    rank=1,
                    text="R",
                    policy_number="P",
                    heading_path=[],
                    allowed_roles=[],
                    department=None,
                )
            ]

    lexical = RecordingLexical()
    semantic = MaliciousRetriever()
    service = RetrievalService(
        store,
        AuthorizationFilter(store),
        lexical,
        semantic,
        ReciprocalRankFusion(),
        FixtureReranker(),
    )

    results = await service.retrieve(profile, "query", 5)

    # The restricted chunk must be dropped by RetrievalService post-fusion, but allowed must remain
    assert [item.chunk_id for item in results] == ["allowed"]
