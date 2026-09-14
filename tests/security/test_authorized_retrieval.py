from collections.abc import Sequence

from apps.api.app.models.organization import ApplicationRole, EmployeeProfile
from apps.api.app.services.foundation_store import FoundationStore
from packages.contracts.access import AccessDimension, AccessMode, AccessScope
from packages.contracts.canonical import RetrievalChunk, SourceLocator
from packages.contracts.policy import PolicyStatus, SOPPolicy, SOPVersion, VersionStatus
from packages.contracts.retrieval import CandidateChannel, RetrievalCandidate
from services.retrieval.authorization_filter import AuthorizationFilter
from services.retrieval.fusion import ReciprocalRankFusion
from services.retrieval.lexical_search import LexicalCandidateRetriever
from services.retrieval.reranker import FixtureReranker
from services.retrieval.retriever import RetrievalService
from services.retrieval.semantic_search import SemanticCandidateRetriever


def selected(department: str) -> AccessScope:
    return AccessScope(
        departments=AccessDimension(
            mode=AccessMode.SELECTED, values=frozenset({department})
        ),
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
        self, query: str, eligible_chunks: Sequence[RetrievalChunk], limit: int
    ) -> list[RetrievalCandidate]:
        self.seen = [item.id for item in eligible_chunks]
        return [
            RetrievalCandidate(
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
        self, query: str, eligible_chunks: Sequence[RetrievalChunk], limit: int
    ) -> list[RetrievalCandidate]:
        self.seen = [item.id for item in eligible_chunks]
        return [
            RetrievalCandidate(
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
        chunks={"version": [chunk("allowed", "store"), chunk("restricted", "hr")]},
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
