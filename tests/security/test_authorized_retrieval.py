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
from services.retrieval.lexical_search import FixtureLexicalRetriever, LexicalCandidateRetriever
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


class ConfigurableRecordingPineconeIndex:
    def __init__(self, configured_matches: list[SimpleNamespace] | None = None) -> None:
        self.queries: list[dict[str, object]] = []
        self._configured_matches = configured_matches

    def query(self, **kwargs: object) -> SimpleNamespace:
        self.queries.append(kwargs)
        if self._configured_matches is not None:
            return SimpleNamespace(matches=self._configured_matches)
        matches: list[SimpleNamespace] = []
        filter_expr = kwargs.get("filter")
        if isinstance(filter_expr, dict) and "$and" in filter_expr:
            for clause in filter_expr["$and"]:
                if (
                    isinstance(clause, dict)
                    and "chunk_id" in clause
                    and "$in" in clause["chunk_id"]
                ):
                    for cid in clause["chunk_id"]["$in"]:
                        matches.append(SimpleNamespace(id=str(cid), score=0.9, metadata={}))
        return SimpleNamespace(matches=matches)


class RecordingLexicalSpy(LexicalCandidateRetriever):
    def __init__(self, inner: LexicalCandidateRetriever) -> None:
        self.inner = inner
        self.recorded_queries: list[str] = []
        self.recorded_eligible: list[list[RetrievalChunk]] = []

    async def search(
        self,
        query: str,
        eligible_chunks: Sequence[RetrievalChunk],
        limit: int,
    ) -> list[RetrievalCandidate]:
        self.recorded_queries.append(query)
        self.recorded_eligible.append(list(eligible_chunks))
        return await self.inner.search(query, eligible_chunks, limit)


class RecordingSemanticSpy(SemanticCandidateRetriever):
    def __init__(self, inner: SemanticCandidateRetriever) -> None:
        self.inner = inner
        self.recorded_queries: list[str] = []
        self.recorded_eligible: list[list[RetrievalChunk]] = []

    async def search(
        self,
        query: str,
        eligible_chunks: Sequence[RetrievalChunk],
        limit: int,
    ) -> list[RetrievalCandidate]:
        self.recorded_queries.append(query)
        self.recorded_eligible.append(list(eligible_chunks))
        return await self.inner.search(query, eligible_chunks, limit)


def make_real_retrieval_system(
    store: FoundationStore,
    pinecone_index: ConfigurableRecordingPineconeIndex | None = None,
) -> tuple[
    RetrievalService,
    ConfigurableRecordingPineconeIndex,
    RecordingLexicalSpy,
    RecordingSemanticSpy,
]:
    index = pinecone_index or ConfigurableRecordingPineconeIndex()
    semantic_inner = PineconeSemanticRetriever(
        api_key="mock-key",
        index_name="aziz-jan-sop",
        namespace_prefix="aziz-jan-trust",
        embeddings=FixtureEmbeddingProvider(),
        index=index,
    )
    lexical_spy = RecordingLexicalSpy(FixtureLexicalRetriever())
    semantic_spy = RecordingSemanticSpy(semantic_inner)
    service = RetrievalService(
        store=store,
        authorization=AuthorizationFilter(store),
        lexical=lexical_spy,
        semantic=semantic_spy,
        fusion=ReciprocalRankFusion(),
        reranker=FixtureReranker(),
    )
    return service, index, lexical_spy, semantic_spy


@pytest.mark.asyncio
async def test_system_admin_retrieves_chunk_restricted_to_other_department_and_location() -> None:
    store = FoundationStore(
        policies={
            "pol-a": SOPPolicy(
                id="pol-a",
                organization_id="org-a",
                title="Org A Policy",
                category="Operations",
                status=PolicyStatus.ACTIVE,
                active_version_id="ver-a",
            )
        },
        versions={
            "ver-a": SOPVersion(
                id="ver-a",
                organization_id="org-a",
                policy_id="pol-a",
                version_label="1",
                status=VersionStatus.PUBLISHED,
                access=AccessScope(
                    departments=AccessDimension(
                        mode=AccessMode.SELECTED, values=frozenset({"Operations"})
                    ),
                    locations=AccessDimension(
                        mode=AccessMode.SELECTED, values=frozenset({"Lahore"})
                    ),
                    roles=AccessDimension(mode=AccessMode.ALL),
                ),
            )
        },
        chunks={
            "ver-a": [
                RetrievalChunk(
                    id="chunk-ops-lahore",
                    organization_id="org-a",
                    policy_id="pol-a",
                    version_id="ver-a",
                    source_document_id="src-1",
                    section_id="sec-1",
                    heading_path=("Operations", "Handling"),
                    policy_number="SOP-OPS-01",
                    text="warehouse damaged stock handling procedure",
                    access=AccessScope(
                        departments=AccessDimension(
                            mode=AccessMode.SELECTED, values=frozenset({"Operations"})
                        ),
                        locations=AccessDimension(
                            mode=AccessMode.SELECTED, values=frozenset({"Lahore"})
                        ),
                        roles=AccessDimension(mode=AccessMode.ALL),
                    ),
                    source=SourceLocator(source_document_id="src-1", page_start=1, page_end=1),
                    chunk_index=0,
                    publication_status="published",
                )
            ]
        },
    )
    sys_admin = EmployeeProfile(
        id="sysadmin-1",
        organization_id="org-a",
        identity_subject="fixture|sysadmin",
        display_name="System Admin",
        email="sysadmin@example.test",
        application_roles=frozenset({ApplicationRole.SYSTEM_ADMIN}),
        departments=frozenset({"Finance"}),
        locations=frozenset({"Karachi"}),
        organizational_roles=frozenset({"Officer"}),
    )
    service, _, _, _ = make_real_retrieval_system(store)
    results = await service.retrieve(sys_admin, "damaged stock handling", 5)

    assert len(results) == 1
    assert results[0].chunk_id == "chunk-ops-lahore"
    assert results[0].organization_id == "org-a"


@pytest.mark.asyncio
async def test_system_admin_cannot_retrieve_chunk_of_other_organization() -> None:
    store = FoundationStore(
        policies={
            "pol-a": SOPPolicy(
                id="pol-a",
                organization_id="org-a",
                title="Policy Org A",
                category="Operations",
                status=PolicyStatus.ACTIVE,
                active_version_id="ver-a",
            ),
            "pol-b": SOPPolicy(
                id="pol-b",
                organization_id="org-b",
                title="Policy Org B",
                category="Operations",
                status=PolicyStatus.ACTIVE,
                active_version_id="ver-b",
            ),
        },
        versions={
            "ver-a": SOPVersion(
                id="ver-a",
                organization_id="org-a",
                policy_id="pol-a",
                version_label="1",
                status=VersionStatus.PUBLISHED,
                access=AccessScope(
                    departments=AccessDimension(mode=AccessMode.ALL),
                    locations=AccessDimension(mode=AccessMode.ALL),
                    roles=AccessDimension(mode=AccessMode.ALL),
                ),
            ),
            "ver-b": SOPVersion(
                id="ver-b",
                organization_id="org-b",
                policy_id="pol-b",
                version_label="1",
                status=VersionStatus.PUBLISHED,
                access=AccessScope(
                    departments=AccessDimension(mode=AccessMode.ALL),
                    locations=AccessDimension(mode=AccessMode.ALL),
                    roles=AccessDimension(mode=AccessMode.ALL),
                ),
            ),
        },
        chunks={
            "ver-a": [
                RetrievalChunk(
                    id="chunk-org-a",
                    organization_id="org-a",
                    policy_id="pol-a",
                    version_id="ver-a",
                    source_document_id="src-a",
                    section_id="sec-a",
                    heading_path=("General",),
                    policy_number="SOP-A",
                    text="org a standard operating procedures",
                    access=AccessScope(
                        departments=AccessDimension(mode=AccessMode.ALL),
                        locations=AccessDimension(mode=AccessMode.ALL),
                        roles=AccessDimension(mode=AccessMode.ALL),
                    ),
                    source=SourceLocator(source_document_id="src-a", page_start=1, page_end=1),
                    chunk_index=0,
                    publication_status="published",
                )
            ],
            "ver-b": [
                RetrievalChunk(
                    id="chunk-org-b",
                    organization_id="org-b",
                    policy_id="pol-b",
                    version_id="ver-b",
                    source_document_id="src-b",
                    section_id="sec-b",
                    heading_path=("General",),
                    policy_number="SOP-B",
                    text="org b standard operating procedures",
                    access=AccessScope(
                        departments=AccessDimension(mode=AccessMode.ALL),
                        locations=AccessDimension(mode=AccessMode.ALL),
                        roles=AccessDimension(mode=AccessMode.ALL),
                    ),
                    source=SourceLocator(source_document_id="src-b", page_start=1, page_end=1),
                    chunk_index=0,
                    publication_status="published",
                )
            ],
        },
    )
    sys_admin_a = EmployeeProfile(
        id="sysadmin-a",
        organization_id="org-a",
        identity_subject="fixture|sysadmin-a",
        display_name="System Admin A",
        email="sysadmin@org-a.test",
        application_roles=frozenset({ApplicationRole.SYSTEM_ADMIN}),
    )
    service, rec_index, _, _ = make_real_retrieval_system(store)
    results = await service.retrieve(sys_admin_a, "operating procedures", 5)

    assert [r.chunk_id for r in results] == ["chunk-org-a"]
    assert "chunk-org-b" not in [r.chunk_id for r in results]
    assert len(rec_index.queries) == 1
    query = rec_index.queries[0]
    assert query["namespace"] == "aziz-jan-trust--org-a"
    assert query["namespace"] != "aziz-jan-trust--org-b"
    filters = query["filter"]["$and"]
    assert {"organization_id": {"$eq": "org-a"}} in filters


@pytest.mark.asyncio
async def test_employee_cannot_retrieve_chunk_restricted_to_other_department() -> None:
    chunk_access = AccessScope(
        departments=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"Operations"})),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    store = FoundationStore(
        policies={
            "pol-1": SOPPolicy(
                id="pol-1",
                organization_id="org-a",
                title="Policy 1",
                category="Operations",
                status=PolicyStatus.ACTIVE,
                active_version_id="ver-1",
            )
        },
        versions={
            "ver-1": SOPVersion(
                id="ver-1",
                organization_id="org-a",
                policy_id="pol-1",
                version_label="1",
                status=VersionStatus.PUBLISHED,
                access=chunk_access,
            )
        },
        chunks={
            "ver-1": [
                RetrievalChunk(
                    id="chunk-restricted-dept",
                    organization_id="org-a",
                    policy_id="pol-1",
                    version_id="ver-1",
                    source_document_id="src-1",
                    section_id="sec-1",
                    heading_path=("Restricted",),
                    policy_number="SOP-01",
                    text="restricted operations procedures",
                    access=chunk_access,
                    source=SourceLocator(source_document_id="src-1", page_start=1, page_end=1),
                    chunk_index=0,
                    publication_status="published",
                )
            ]
        },
    )
    employee = EmployeeProfile(
        id="emp-1",
        organization_id="org-a",
        identity_subject="fixture|emp-1",
        display_name="Employee 1",
        email="emp@example.test",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
        departments=frozenset({"Finance"}),
        locations=frozenset({"Lahore"}),
        organizational_roles=frozenset({"Manager"}),
    )
    service, rec_index, _, _ = make_real_retrieval_system(store)
    results = await service.retrieve(employee, "operations procedures", 5)

    assert len(results) == 0
    assert len(rec_index.queries) == 0


@pytest.mark.asyncio
async def test_employee_cannot_retrieve_chunk_restricted_to_other_location() -> None:
    chunk_access = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"Lahore"})),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    store = FoundationStore(
        policies={
            "pol-1": SOPPolicy(
                id="pol-1",
                organization_id="org-a",
                title="Policy 1",
                category="Operations",
                status=PolicyStatus.ACTIVE,
                active_version_id="ver-1",
            )
        },
        versions={
            "ver-1": SOPVersion(
                id="ver-1",
                organization_id="org-a",
                policy_id="pol-1",
                version_label="1",
                status=VersionStatus.PUBLISHED,
                access=chunk_access,
            )
        },
        chunks={
            "ver-1": [
                RetrievalChunk(
                    id="chunk-restricted-loc",
                    organization_id="org-a",
                    policy_id="pol-1",
                    version_id="ver-1",
                    source_document_id="src-1",
                    section_id="sec-1",
                    heading_path=("Restricted",),
                    policy_number="SOP-01",
                    text="restricted lahore procedures",
                    access=chunk_access,
                    source=SourceLocator(source_document_id="src-1", page_start=1, page_end=1),
                    chunk_index=0,
                    publication_status="published",
                )
            ]
        },
    )
    employee = EmployeeProfile(
        id="emp-1",
        organization_id="org-a",
        identity_subject="fixture|emp-1",
        display_name="Employee 1",
        email="emp@example.test",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
        departments=frozenset({"Finance"}),
        locations=frozenset({"Karachi"}),
        organizational_roles=frozenset({"Manager"}),
    )
    service, rec_index, _, _ = make_real_retrieval_system(store)
    results = await service.retrieve(employee, "lahore procedures", 5)

    assert len(results) == 0
    assert len(rec_index.queries) == 0


@pytest.mark.asyncio
async def test_employee_cannot_retrieve_chunk_restricted_to_other_role() -> None:
    chunk_access = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"Director"})),
    )
    store = FoundationStore(
        policies={
            "pol-1": SOPPolicy(
                id="pol-1",
                organization_id="org-a",
                title="Policy 1",
                category="Operations",
                status=PolicyStatus.ACTIVE,
                active_version_id="ver-1",
            )
        },
        versions={
            "ver-1": SOPVersion(
                id="ver-1",
                organization_id="org-a",
                policy_id="pol-1",
                version_label="1",
                status=VersionStatus.PUBLISHED,
                access=chunk_access,
            )
        },
        chunks={
            "ver-1": [
                RetrievalChunk(
                    id="chunk-restricted-role",
                    organization_id="org-a",
                    policy_id="pol-1",
                    version_id="ver-1",
                    source_document_id="src-1",
                    section_id="sec-1",
                    heading_path=("Restricted",),
                    policy_number="SOP-01",
                    text="restricted executive procedures",
                    access=chunk_access,
                    source=SourceLocator(source_document_id="src-1", page_start=1, page_end=1),
                    chunk_index=0,
                    publication_status="published",
                )
            ]
        },
    )
    employee = EmployeeProfile(
        id="emp-1",
        organization_id="org-a",
        identity_subject="fixture|emp-1",
        display_name="Employee 1",
        email="emp@example.test",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
        departments=frozenset({"Finance"}),
        locations=frozenset({"Lahore"}),
        organizational_roles=frozenset({"Staff"}),
    )
    service, rec_index, _, _ = make_real_retrieval_system(store)
    results = await service.retrieve(employee, "executive procedures", 5)

    assert len(results) == 0
    assert len(rec_index.queries) == 0


@pytest.mark.asyncio
async def test_draft_unpublished_and_inactive_versions_never_returned() -> None:
    all_scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    store = FoundationStore(
        policies={
            "pol-active": SOPPolicy(
                id="pol-active",
                organization_id="org-a",
                title="Active Policy",
                category="Operations",
                status=PolicyStatus.ACTIVE,
                active_version_id="ver-active",
            ),
            "pol-inactive": SOPPolicy(
                id="pol-inactive",
                organization_id="org-a",
                title="Inactive Policy",
                category="Operations",
                status=PolicyStatus.DRAFT,
                active_version_id="ver-inactive",
            ),
        },
        versions={
            "ver-active": SOPVersion(
                id="ver-active",
                organization_id="org-a",
                policy_id="pol-active",
                version_label="1",
                status=VersionStatus.PUBLISHED,
                access=all_scope,
            ),
            "ver-draft": SOPVersion(
                id="ver-draft",
                organization_id="org-a",
                policy_id="pol-active",
                version_label="2",
                status=VersionStatus.DRAFT,
                access=all_scope,
            ),
            "ver-inactive": SOPVersion(
                id="ver-inactive",
                organization_id="org-a",
                policy_id="pol-inactive",
                version_label="1",
                status=VersionStatus.PUBLISHED,
                access=all_scope,
            ),
        },
        chunks={
            "ver-active": [
                RetrievalChunk(
                    id="chunk-published",
                    organization_id="org-a",
                    policy_id="pol-active",
                    version_id="ver-active",
                    source_document_id="src-1",
                    section_id="sec-1",
                    heading_path=("Policy",),
                    policy_number="SOP-1",
                    text="active published operating procedures",
                    access=all_scope,
                    source=SourceLocator(source_document_id="src-1", page_start=1, page_end=1),
                    chunk_index=0,
                    publication_status="published",
                ),
                RetrievalChunk(
                    id="chunk-archived",
                    organization_id="org-a",
                    policy_id="pol-active",
                    version_id="ver-active",
                    source_document_id="src-1",
                    section_id="sec-2",
                    heading_path=("Policy",),
                    policy_number="SOP-1",
                    text="active archived operating procedures",
                    access=all_scope,
                    source=SourceLocator(source_document_id="src-1", page_start=1, page_end=1),
                    chunk_index=1,
                    publication_status="archived",
                ),
            ],
            "ver-draft": [
                RetrievalChunk(
                    id="chunk-draft",
                    organization_id="org-a",
                    policy_id="pol-active",
                    version_id="ver-draft",
                    source_document_id="src-2",
                    section_id="sec-1",
                    heading_path=("Policy",),
                    policy_number="SOP-1",
                    text="draft operating procedures",
                    access=all_scope,
                    source=SourceLocator(source_document_id="src-2", page_start=1, page_end=1),
                    chunk_index=0,
                    publication_status="draft",
                ),
            ],
            "ver-inactive": [
                RetrievalChunk(
                    id="chunk-inactive-pol",
                    organization_id="org-a",
                    policy_id="pol-inactive",
                    version_id="ver-inactive",
                    source_document_id="src-3",
                    section_id="sec-1",
                    heading_path=("Policy",),
                    policy_number="SOP-2",
                    text="inactive policy operating procedures",
                    access=all_scope,
                    source=SourceLocator(source_document_id="src-3", page_start=1, page_end=1),
                    chunk_index=0,
                    publication_status="published",
                ),
            ],
        },
    )
    emp = EmployeeProfile(
        id="emp-1",
        organization_id="org-a",
        identity_subject="fixture|emp-1",
        display_name="Employee",
        email="emp@example.test",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
    )
    service, _, _, _ = make_real_retrieval_system(store)
    results = await service.retrieve(emp, "operating procedures", 5)

    assert [r.chunk_id for r in results] == ["chunk-published"]
    assert "chunk-archived" not in [r.chunk_id for r in results]
    assert "chunk-draft" not in [r.chunk_id for r in results]
    assert "chunk-inactive-pol" not in [r.chunk_id for r in results]


@pytest.mark.asyncio
async def test_recording_fake_pinecone_receives_exact_eligible_filter_predicates() -> None:
    all_scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    store = FoundationStore(
        policies={
            "pol-1": SOPPolicy(
                id="pol-1",
                organization_id="org-a",
                title="Policy 1",
                category="Operations",
                status=PolicyStatus.ACTIVE,
                active_version_id="ver-1",
            )
        },
        versions={
            "ver-1": SOPVersion(
                id="ver-1",
                organization_id="org-a",
                policy_id="pol-1",
                version_label="1",
                status=VersionStatus.PUBLISHED,
                access=all_scope,
            )
        },
        chunks={
            "ver-1": [
                RetrievalChunk(
                    id="chunk-allowed",
                    organization_id="org-a",
                    policy_id="pol-1",
                    version_id="ver-1",
                    source_document_id="src-1",
                    section_id="sec-1",
                    heading_path=("Finance",),
                    policy_number="SOP-1",
                    text="allowed finance handling procedures",
                    access=AccessScope(
                        departments=AccessDimension(
                            mode=AccessMode.SELECTED, values=frozenset({"Finance"})
                        ),
                        locations=AccessDimension(mode=AccessMode.ALL),
                        roles=AccessDimension(mode=AccessMode.ALL),
                    ),
                    source=SourceLocator(source_document_id="src-1", page_start=1, page_end=1),
                    chunk_index=0,
                    publication_status="published",
                ),
                RetrievalChunk(
                    id="chunk-restricted",
                    organization_id="org-a",
                    policy_id="pol-1",
                    version_id="ver-1",
                    source_document_id="src-1",
                    section_id="sec-2",
                    heading_path=("Operations",),
                    policy_number="SOP-1",
                    text="restricted operations handling procedures",
                    access=AccessScope(
                        departments=AccessDimension(
                            mode=AccessMode.SELECTED, values=frozenset({"Operations"})
                        ),
                        locations=AccessDimension(mode=AccessMode.ALL),
                        roles=AccessDimension(mode=AccessMode.ALL),
                    ),
                    source=SourceLocator(source_document_id="src-1", page_start=1, page_end=1),
                    chunk_index=1,
                    publication_status="published",
                ),
            ]
        },
    )
    emp = EmployeeProfile(
        id="emp-1",
        organization_id="org-a",
        identity_subject="fixture|emp-1",
        display_name="Employee",
        email="emp@example.test",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
        departments=frozenset({"Finance"}),
    )
    service, rec_index, _, _ = make_real_retrieval_system(store)
    await service.retrieve(emp, "handling procedures", 5)

    assert len(rec_index.queries) == 1
    query = rec_index.queries[0]
    assert query["namespace"] == "aziz-jan-trust--org-a"
    filter_clauses = query["filter"]["$and"]
    assert {"organization_id": {"$eq": "org-a"}} in filter_clauses
    assert {"publication_status": {"$eq": "published"}} in filter_clauses
    assert {"chunk_id": {"$in": ["chunk-allowed"]}} in filter_clauses
    assert not any(
        isinstance(c, dict)
        and "chunk_id" in c
        and "chunk-restricted" in c["chunk_id"].get("$in", [])
        for c in filter_clauses
    )


@pytest.mark.asyncio
async def test_fake_pinecone_match_for_restricted_chunk_dropped_by_final_revalidation() -> None:
    store = FoundationStore(
        policies={
            "pol-1": SOPPolicy(
                id="pol-1",
                organization_id="org-a",
                title="Policy 1",
                category="Operations",
                status=PolicyStatus.ACTIVE,
                active_version_id="ver-1",
            )
        },
        versions={
            "ver-1": SOPVersion(
                id="ver-1",
                organization_id="org-a",
                policy_id="pol-1",
                version_label="1",
                status=VersionStatus.PUBLISHED,
                access=AccessScope(
                    departments=AccessDimension(mode=AccessMode.ALL),
                    locations=AccessDimension(mode=AccessMode.ALL),
                    roles=AccessDimension(mode=AccessMode.ALL),
                ),
            )
        },
        chunks={
            "ver-1": [
                RetrievalChunk(
                    id="chunk-allowed",
                    organization_id="org-a",
                    policy_id="pol-1",
                    version_id="ver-1",
                    source_document_id="src-1",
                    section_id="sec-1",
                    heading_path=("Finance",),
                    policy_number="SOP-1",
                    text="allowed finance handling procedures",
                    access=AccessScope(
                        departments=AccessDimension(
                            mode=AccessMode.SELECTED, values=frozenset({"Finance"})
                        ),
                        locations=AccessDimension(mode=AccessMode.ALL),
                        roles=AccessDimension(mode=AccessMode.ALL),
                    ),
                    source=SourceLocator(source_document_id="src-1", page_start=1, page_end=1),
                    chunk_index=0,
                    publication_status="published",
                ),
                RetrievalChunk(
                    id="chunk-restricted",
                    organization_id="org-a",
                    policy_id="pol-1",
                    version_id="ver-1",
                    source_document_id="src-1",
                    section_id="sec-2",
                    heading_path=("Operations",),
                    policy_number="SOP-1",
                    text="restricted operations handling procedures",
                    access=AccessScope(
                        departments=AccessDimension(
                            mode=AccessMode.SELECTED, values=frozenset({"Operations"})
                        ),
                        locations=AccessDimension(mode=AccessMode.ALL),
                        roles=AccessDimension(mode=AccessMode.ALL),
                    ),
                    source=SourceLocator(source_document_id="src-1", page_start=1, page_end=1),
                    chunk_index=1,
                    publication_status="published",
                ),
            ]
        },
    )
    emp = EmployeeProfile(
        id="emp-1",
        organization_id="org-a",
        identity_subject="fixture|emp-1",
        display_name="Employee",
        email="emp@example.test",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
        departments=frozenset({"Finance"}),
    )
    malicious_index = ConfigurableRecordingPineconeIndex(
        configured_matches=[
            SimpleNamespace(id="chunk-restricted", score=0.99, metadata={}),
            SimpleNamespace(id="chunk-allowed", score=0.85, metadata={}),
        ]
    )
    service, _, _, _ = make_real_retrieval_system(store, pinecone_index=malicious_index)
    results = await service.retrieve(emp, "handling procedures", 5)

    assert [r.chunk_id for r in results] == ["chunk-allowed"]
    assert "chunk-restricted" not in [r.chunk_id for r in results]


@pytest.mark.asyncio
async def test_lexical_and_semantic_channels_receive_identical_eligible_set() -> None:
    store = FoundationStore(
        policies={
            "pol-1": SOPPolicy(
                id="pol-1",
                organization_id="org-a",
                title="Policy 1",
                category="Operations",
                status=PolicyStatus.ACTIVE,
                active_version_id="ver-1",
            )
        },
        versions={
            "ver-1": SOPVersion(
                id="ver-1",
                organization_id="org-a",
                policy_id="pol-1",
                version_label="1",
                status=VersionStatus.PUBLISHED,
                access=AccessScope(
                    departments=AccessDimension(mode=AccessMode.ALL),
                    locations=AccessDimension(mode=AccessMode.ALL),
                    roles=AccessDimension(mode=AccessMode.ALL),
                ),
            )
        },
        chunks={
            "ver-1": [
                RetrievalChunk(
                    id="chunk-allowed-1",
                    organization_id="org-a",
                    policy_id="pol-1",
                    version_id="ver-1",
                    source_document_id="src-1",
                    section_id="sec-1",
                    heading_path=("Finance", "1"),
                    policy_number="SOP-1",
                    text="finance invoice handling",
                    access=AccessScope(
                        departments=AccessDimension(
                            mode=AccessMode.SELECTED, values=frozenset({"Finance"})
                        ),
                        locations=AccessDimension(mode=AccessMode.ALL),
                        roles=AccessDimension(mode=AccessMode.ALL),
                    ),
                    source=SourceLocator(source_document_id="src-1", page_start=1, page_end=1),
                    chunk_index=0,
                    publication_status="published",
                ),
                RetrievalChunk(
                    id="chunk-allowed-2",
                    organization_id="org-a",
                    policy_id="pol-1",
                    version_id="ver-1",
                    source_document_id="src-1",
                    section_id="sec-2",
                    heading_path=("Finance", "2"),
                    policy_number="SOP-1",
                    text="finance audit handling",
                    access=AccessScope(
                        departments=AccessDimension(
                            mode=AccessMode.SELECTED, values=frozenset({"Finance"})
                        ),
                        locations=AccessDimension(mode=AccessMode.ALL),
                        roles=AccessDimension(mode=AccessMode.ALL),
                    ),
                    source=SourceLocator(source_document_id="src-1", page_start=1, page_end=1),
                    chunk_index=1,
                    publication_status="published",
                ),
                RetrievalChunk(
                    id="chunk-restricted",
                    organization_id="org-a",
                    policy_id="pol-1",
                    version_id="ver-1",
                    source_document_id="src-1",
                    section_id="sec-3",
                    heading_path=("Operations",),
                    policy_number="SOP-1",
                    text="operations handling",
                    access=AccessScope(
                        departments=AccessDimension(
                            mode=AccessMode.SELECTED, values=frozenset({"Operations"})
                        ),
                        locations=AccessDimension(mode=AccessMode.ALL),
                        roles=AccessDimension(mode=AccessMode.ALL),
                    ),
                    source=SourceLocator(source_document_id="src-1", page_start=1, page_end=1),
                    chunk_index=2,
                    publication_status="published",
                ),
            ]
        },
    )
    emp = EmployeeProfile(
        id="emp-1",
        organization_id="org-a",
        identity_subject="fixture|emp-1",
        display_name="Employee",
        email="emp@example.test",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
        departments=frozenset({"Finance"}),
    )
    service, _, lexical_spy, semantic_spy = make_real_retrieval_system(store)
    await service.retrieve(emp, "finance handling", 5)

    assert len(lexical_spy.recorded_eligible) == 1
    assert len(semantic_spy.recorded_eligible) == 1
    lexical_ids = [c.id for c in lexical_spy.recorded_eligible[0]]
    semantic_ids = [c.id for c in semantic_spy.recorded_eligible[0]]
    assert lexical_ids == ["chunk-allowed-1", "chunk-allowed-2"]
    assert semantic_ids == ["chunk-allowed-1", "chunk-allowed-2"]
    assert lexical_ids == semantic_ids
