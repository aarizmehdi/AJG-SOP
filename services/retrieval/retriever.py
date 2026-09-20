import asyncio
from collections import defaultdict
from time import perf_counter

from apps.api.app.models.organization import EmployeeProfile
from apps.api.app.services.foundation_store import FoundationStore
from apps.api.app.services.metrics import MetricsRegistry
from packages.contracts.canonical import RetrievalChunk
from packages.contracts.retrieval import SearchEvidence
from services.retrieval.authorization_filter import AuthorizationFilter
from services.retrieval.fusion import CandidateFusion
from services.retrieval.lexical_search import LexicalCandidateRetriever
from services.retrieval.reranker import Reranker
from services.retrieval.semantic_search import SemanticCandidateRetriever


class RetrievalService:
    def __init__(
        self,
        store: FoundationStore,
        authorization: AuthorizationFilter,
        lexical: LexicalCandidateRetriever,
        semantic: SemanticCandidateRetriever,
        fusion: CandidateFusion,
        reranker: Reranker,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self.store = store
        self.authorization = authorization
        self.lexical = lexical
        self.semantic = semantic
        self.fusion = fusion
        self.reranker = reranker
        self.metrics = metrics
        self._traces: defaultdict[str, list[dict[str, object]]] = defaultdict(list)

    async def retrieve(
        self, profile: EmployeeProfile, query: str, limit: int
    ) -> list[SearchEvidence]:
        started = perf_counter()
        eligible = self.authorization.eligible_chunks(profile)
        try:
            lexical, semantic = await asyncio.gather(
                self.lexical.search(query, eligible, limit * 3),
                self.semantic.search(query, eligible, limit * 3),
            )
        except Exception:
            if self.metrics:
                self.metrics.observe("retrieval", (perf_counter() - started) * 1000, failed=True)
            raise
        fused = self.fusion.fuse(lexical, semantic)
        chunks = {chunk.id: chunk for chunk in eligible}
        ranked = await self.reranker.rerank(query, fused, chunks)
        evidence: list[SearchEvidence] = []
        for chunk_id, score in ranked:
            chunk = chunks.get(chunk_id)
            if not chunk or not self.authorization.revalidate(profile, chunk):
                continue
            policy = self.store.policies.get(chunk.policy_id)
            if not policy:
                continue
            evidence.append(self._evidence(policy.title, chunk, score))
            if len(evidence) == limit:
                break
        if self.metrics:
            self.metrics.observe("retrieval", (perf_counter() - started) * 1000)
        trace = {
            "query": query,
            "employee_id": profile.id,
            "employee_scope": {
                "departments": sorted(profile.departments),
                "locations": sorted(profile.locations),
                "roles": sorted(profile.organizational_roles),
            },
            "eligible_chunk_ids": [item.id for item in eligible],
            "lexical_candidates": [item.model_dump(mode="json") for item in lexical],
            "semantic_candidates": [item.model_dump(mode="json") for item in semantic],
            "fused_order": [item[0] for item in fused],
            "reranked_order": [item[0] for item in ranked],
            "selected_context": [item.chunk_id for item in evidence],
            "semantic_provider": self.semantic.__class__.__name__,
            "reranker_provider": self.reranker.__class__.__name__,
            "duration_ms": round((perf_counter() - started) * 1000, 2),
        }
        self._traces[profile.organization_id].append(trace)
        self._traces[profile.organization_id] = self._traces[profile.organization_id][-100:]
        return evidence

    def telemetry(self, organization_id: str) -> list[dict[str, object]]:
        return list(self._traces.get(organization_id, []))

    @staticmethod
    def _evidence(title: str, chunk: RetrievalChunk, score: float) -> SearchEvidence:
        excerpt = chunk.text[:420] + ("…" if len(chunk.text) > 420 else "")
        return SearchEvidence(
            organization_id=chunk.organization_id,
            chunk_id=chunk.id,
            policy_id=chunk.policy_id,
            version_id=chunk.version_id,
            section_id=chunk.section_id,
            policy_title=title,
            heading_path=chunk.heading_path,
            policy_number=chunk.policy_number,
            excerpt=excerpt,
            source=chunk.source,
            fused_score=score,
        )
