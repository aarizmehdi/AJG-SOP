import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
from time import perf_counter

from apps.api.app.models.organization import EmployeeProfile
from apps.api.app.services.foundation_store import FoundationStore
from apps.api.app.services.metrics import MetricsRegistry
from packages.contracts.canonical import RetrievalChunk
from packages.contracts.retrieval import AssistantEvidence, SearchEvidence
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
        cache_refresh: Callable[[], Awaitable[set[str]]] | None = None,
    ) -> None:
        self.store = store
        self.authorization = authorization
        self.lexical = lexical
        self.semantic = semantic
        self.fusion = fusion
        self.reranker = reranker
        self.metrics = metrics
        self.cache_refresh = cache_refresh
        self._traces: defaultdict[str, list[dict[str, object]]] = defaultdict(list)

    def evict_chunks(self, chunk_ids: set[str]) -> None:
        """Drop only runtime traces with exact structured chunk references."""

        def linked(value: object, key: str = "") -> bool:
            if isinstance(value, dict):
                return any(linked(v, k) for k, v in value.items())
            if isinstance(value, list):
                return any(linked(v, key) for v in value)
            return (
                key
                in {
                    "chunk_id",
                    "eligible_chunk_ids",
                    "selected_context",
                    "fused_order",
                    "reranked_order",
                }
                and isinstance(value, str)
                and value in chunk_ids
            )

        for org, traces in self._traces.items():
            self._traces[org] = [trace for trace in traces if not linked(trace)]

    async def retrieve(
        self, profile: EmployeeProfile, query: str, limit: int
    ) -> list[SearchEvidence]:
        started = perf_counter()
        await self._refresh()
        eligible = self.authorization.eligible_chunks(profile)
        try:
            lexical, semantic = await asyncio.gather(
                self.lexical.search(query, profile, eligible, limit * 3),
                self.semantic.search(query, profile, eligible, limit * 3),
            )
        except Exception:
            if self.metrics:
                self.metrics.observe("retrieval", (perf_counter() - started) * 1000, failed=True)
            raise
        fused = self.fusion.fuse(lexical, semantic, profile)
        chunks = {chunk.id: chunk for chunk in eligible}
        ranked = await self.reranker.rerank(query, fused, chunks)
        await self._refresh()
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
            "query_chars": len(query),
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

    async def _refresh(self) -> None:
        if self.cache_refresh is not None:
            self.evict_chunks(await self.cache_refresh())

    async def revalidate_evidence(
        self, profile: EmployeeProfile, evidence: Sequence[SearchEvidence]
    ) -> bool:
        """Check again before releasing an answer, including answers already generating at purge."""
        await self._refresh()
        allowed = {c.id: c for c in self.authorization.eligible_chunks(profile)}
        return all(
            item.chunk_id in allowed
            and allowed[item.chunk_id].policy_id == item.policy_id
            and allowed[item.chunk_id].version_id == item.version_id
            and self.authorization.revalidate(profile, allowed[item.chunk_id])
            for item in evidence
        )

    async def assistant_context(
        self, profile: EmployeeProfile, evidence: Sequence[SearchEvidence]
    ) -> list[AssistantEvidence]:
        """Expand only currently authorized candidates, within a bounded model budget."""
        await self._refresh()
        allowed = {chunk.id: chunk for chunk in self.authorization.eligible_chunks(profile)}
        remaining = 16000
        context: list[AssistantEvidence] = []
        for item in evidence:
            chunk = allowed.get(item.chunk_id)
            if (
                not chunk
                or chunk.policy_id != item.policy_id
                or chunk.version_id != item.version_id
                or not self.authorization.revalidate(profile, chunk)
            ):
                continue
            text = chunk.text[: min(5000, remaining)]
            if not text:
                break
            context.append(AssistantEvidence(**item.model_dump(), full_text=text))
            remaining -= len(text)
            if remaining <= 0:
                break
        return context

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
