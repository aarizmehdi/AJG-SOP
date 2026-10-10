"""Runs benchmark configurations against the production retrieval and assistant code.

Everything runs in memory. The real ``AuthorizationFilter``, ``RetrievalService``,
``ReciprocalRankFusion`` and (for the assistant section) ``AssistantService`` are exercised
unchanged; only providers differ per configuration. Authorization is additionally checked by an
oracle that reads the corpus access labels directly, so a bug in the production filter cannot
hide its own leak.
"""

import hashlib
import subprocess
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from apps.api.app.models.organization import ApplicationRole, EmployeeProfile
from apps.api.app.services.assistant_service import AssistantService
from apps.api.app.services.foundation_store import FoundationStore
from packages.contracts.access import UNRESTRICTED_SCOPE
from packages.contracts.assistant import GeneratedAnswer, ResponseKind
from packages.contracts.canonical import RetrievalChunk
from packages.contracts.policy import PolicyStatus, SOPPolicy, SOPVersion, VersionStatus
from packages.contracts.retrieval import RetrievalCandidate
from services.assistant.answer_generator import FixtureLLMProvider
from services.assistant.answerability import FixtureAnswerabilityGate
from services.assistant.citations import CitationValidator
from services.assistant.conversation import classify, retrieval_query
from services.assistant.grounding import GroundingVerifier
from services.evaluation.corpus import Corpus
from services.evaluation.matrix import MatrixSpec, RetrievalConfig
from services.evaluation.metrics import facts_present, percentile
from services.evaluation.models import EvaluationCase, EvaluationScope
from services.evaluation.providers import (
    MeteredEmbeddingProvider,
    ProviderUnavailableError,
    build_chunker,
    build_embedding,
    build_reranker,
)
from services.evaluation.results import (
    AssistantCaseResult,
    AssistantMetrics,
    BenchmarkResult,
    CaseResult,
    ConfigResult,
    ConfigStatus,
    CostReport,
    TagMetrics,
)
from services.evaluation.retrieval import CaseRetrievalScore, aggregate_scores, score_case
from services.retrieval.authorization_filter import AuthorizationFilter
from services.retrieval.fusion import ReciprocalRankFusion
from services.retrieval.lexical_search import FixtureLexicalRetriever, LexicalCandidateRetriever
from services.retrieval.retriever import RetrievalService
from services.retrieval.semantic_search import FixtureSemanticRetriever, SemanticCandidateRetriever

ASSISTANT_EVIDENCE_LIMIT = 8  # AssistantService retrieves 8 items in production.


class _LexicalChannel(LexicalCandidateRetriever):
    """Applies a per-channel candidate cap or switches the channel off."""

    def __init__(
        self, inner: LexicalCandidateRetriever, *, enabled: bool, pool: int | None
    ) -> None:
        self._inner = inner
        self._enabled = enabled
        self._pool = pool

    async def search(
        self,
        query: str,
        eligible_chunks: Sequence[RetrievalChunk],
        limit: int,
    ) -> list[RetrievalCandidate]:
        if not self._enabled:
            return []
        return await self._inner.search(
            query, eligible_chunks, min(limit, self._pool) if self._pool else limit
        )


class _SemanticChannel(SemanticCandidateRetriever):
    def __init__(
        self, inner: SemanticCandidateRetriever, *, enabled: bool, pool: int | None
    ) -> None:
        self._inner = inner
        self._enabled = enabled
        self._pool = pool

    async def search(
        self,
        query: str,
        eligible_chunks: Sequence[RetrievalChunk],
        limit: int,
    ) -> list[RetrievalCandidate]:
        if not self._enabled:
            return []
        return await self._inner.search(
            query, eligible_chunks, min(limit, self._pool) if self._pool else limit
        )


def build_profile(corpus: Corpus, scope: EvaluationScope) -> EmployeeProfile:
    identifier = f"eval-{scope.department}-{scope.location}-{scope.role}"
    return EmployeeProfile(
        id=identifier,
        organization_id=corpus.organization_id,
        identity_subject=f"fixture|{identifier}",
        display_name=f"Evaluation {scope.role}",
        email=f"{identifier}@example.test",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
        departments=frozenset({scope.department}),
        locations=frozenset({scope.location}),
        organizational_roles=frozenset({scope.role}),
    )


def build_store(corpus: Corpus, chunks: Mapping[str, list[RetrievalChunk]]) -> FoundationStore:
    store = FoundationStore()
    for document in corpus.documents:
        store.policies[document.policy_id] = SOPPolicy(
            id=document.policy_id,
            organization_id=corpus.organization_id,
            title=document.title,
            category="evaluation",
            status=PolicyStatus.ACTIVE,
            active_version_id=document.version_id,
        )
        store.versions[document.version_id] = SOPVersion(
            id=document.version_id,
            organization_id=corpus.organization_id,
            policy_id=document.policy_id,
            version_label="evaluation",
            status=VersionStatus.PUBLISHED,
            access=UNRESTRICTED_SCOPE,
        )
        store.chunks[document.version_id] = list(chunks[document.version_id])
    return store


def build_retrieval_service(
    config: RetrievalConfig, store: FoundationStore, embeddings: MeteredEmbeddingProvider
) -> RetrievalService:
    return RetrievalService(
        store,
        AuthorizationFilter(store),
        _LexicalChannel(
            FixtureLexicalRetriever(), enabled=config.lexical, pool=config.candidate_pool
        ),
        _SemanticChannel(
            FixtureSemanticRetriever(embeddings),
            enabled=config.semantic,
            pool=config.candidate_pool,
        ),
        ReciprocalRankFusion(
            lexical_weight=config.lexical_weight,
            semantic_weight=config.semantic_weight,
            rank_constant=config.rank_constant,
        ),
        build_reranker(config.reranker),
    )


def _describe(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"[:300]


async def run_config(
    config: RetrievalConfig,
    corpus: Corpus,
    cases: Sequence[EvaluationCase],
    ks: Sequence[int],
    primary_k: int,
    *,
    environment: Mapping[str, str] | None = None,
    include_cases: bool = True,
) -> ConfigResult:
    settings: dict[str, object] = config.model_dump()
    try:
        chunker = build_chunker(config.chunker)
        embedding = build_embedding(config.embedding, environment)
        build_reranker(config.reranker)
    except ProviderUnavailableError as unavailable:
        return ConfigResult(
            name=config.name,
            status=ConfigStatus.SKIPPED,
            reason=str(unavailable),
            settings=settings,
        )
    metered = MeteredEmbeddingProvider(embedding)
    try:
        chunks = {
            document.version_id: chunker.chunk(document, "published")
            for document in corpus.documents
        }
        unknown = {
            chunk.section_id
            for items in chunks.values()
            for chunk in items
            if chunk.section_id not in corpus.key_by_section_id
        }
        if unknown:
            raise ValueError(f"Chunker produced chunks for unknown sections: {sorted(unknown)[:3]}")
        store = build_store(corpus, chunks)
        all_chunks = [chunk for items in chunks.values() for chunk in items]
        text_by_chunk = {chunk.id: chunk.text for chunk in all_chunks}
        index_started = time.perf_counter()
        if config.semantic:
            await metered.embed_documents([chunk.text for chunk in all_chunks])
        index_seconds = time.perf_counter() - index_started
        service = build_retrieval_service(config, store, metered)
    except Exception as error:  # noqa: BLE001 - any construction failure is a failed config
        return ConfigResult(
            name=config.name, status=ConfigStatus.FAILED, reason=_describe(error), settings=settings
        )

    depth = max(ks)
    profiles: dict[tuple[str, str, str], EmployeeProfile] = {}
    restricted: dict[tuple[str, str, str], set[str]] = {}

    def profile_for(scope: EvaluationScope) -> EmployeeProfile:
        key = (scope.department, scope.location, scope.role)
        if key not in profiles:
            profiles[key] = build_profile(corpus, scope)
            restricted[key] = corpus.restricted_for(scope)
        return profiles[key]

    case_results: list[CaseResult] = []
    rankings: list[tuple[EvaluationCase, list[str], list[str], set[str]]] = []
    latencies: list[float] = []
    errors = 0
    for case in cases:
        profile = profile_for(case.employee_scope)
        scope_key = (
            case.employee_scope.department,
            case.employee_scope.location,
            case.employee_scope.role,
        )
        denied = restricted[scope_key]
        sections: list[str] = []
        chunk_ids: list[str] = []
        case_error: str | None = None
        routed = classify(case.question, case.history) is not None
        started = time.perf_counter()
        if not routed:
            try:
                evidence = await service.retrieve(
                    profile, retrieval_query(case.question, case.history), depth
                )
                chunk_ids = [item.chunk_id for item in evidence]
                sections = [corpus.key_by_section_id[item.section_id] for item in evidence]
            except Exception as failure:  # noqa: BLE001 - recorded as a technical failure
                case_error = _describe(failure)
                errors += 1
        elapsed = (time.perf_counter() - started) * 1000
        if not routed:
            latencies.append(elapsed)
        texts = [text_by_chunk.get(chunk_id, "") for chunk_id in chunk_ids]
        rankings.append((case, sections, texts, denied))
        case_results.append(
            CaseResult(
                case_id=case.id,
                language=case.language.value,
                tags=sorted(case.tags),
                routed_without_retrieval=routed,
                returned_sections=sections,
                returned_chunk_ids=chunk_ids,
                error=case_error,
                latency_ms=round(elapsed, 3),
            )
        )

    by_k: dict[str, list[CaseRetrievalScore]] = {}
    for k in ks:
        by_k[str(k)] = [
            score_case(case, sections, k, ranked_texts=texts, restricted_sections=denied)
            for case, sections, texts, denied in rankings
        ]
    primary_scores = by_k[str(primary_k)]
    for result, score, case in zip(case_results, primary_scores, cases, strict=True):
        result.recall = score.recall
        result.reciprocal_rank = score.reciprocal_rank
        result.fact_recall = score.fact_recall
        result.unauthorized_sections = score.unauthorized_sections
        found = set(result.returned_sections[:primary_k])
        result.missing_sections = sorted(
            (case.expected_sections - found)
            if score.recall is not None and score.recall < 1
            else []
        )

    tag_metrics: dict[str, TagMetrics] = {}
    tags = sorted({tag for case in cases for tag in case.tags})
    for tag in tags:
        tagged = [
            score
            for (case, *_), score in zip(rankings, primary_scores, strict=True)
            if tag in case.tags
        ]
        aggregate = aggregate_scores(tagged, primary_k)
        if aggregate.cases_scored:
            tag_metrics[tag] = TagMetrics(
                cases=aggregate.cases_scored,
                recall_at_k=aggregate.recall_at_k,
                mean_reciprocal_rank=aggregate.mean_reciprocal_rank,
                ndcg_at_k=aggregate.ndcg_at_k,
                fact_recall_at_k=aggregate.fact_recall_at_k,
            )

    assistant_metrics = None
    if config.assistant:
        assistant_metrics = await _run_assistant(
            service, corpus, cases, case_results, profile_for, restricted
        )

    return ConfigResult(
        name=config.name,
        status=ConfigStatus.OK,
        settings=settings,
        retrieval_by_k={key: aggregate_scores(scores, int(key)) for key, scores in by_k.items()},
        by_tag=tag_metrics,
        retrieval_technical_failure_rate=errors / len(cases) if cases else 0.0,
        retrieval_latency_ms_p50=round(percentile(latencies, 0.5), 3),
        retrieval_latency_ms_p95=round(percentile(latencies, 0.95), 3),
        assistant=assistant_metrics,
        cost=CostReport(
            embedding_model=metered.model_id,
            index_build_seconds=round(index_seconds, 3),
            query_calls=metered.cost.query_calls,
            provider_texts=metered.cost.provider_texts,
            provider_chars=metered.cost.provider_chars,
            provider_seconds=round(metered.cost.provider_seconds, 3),
            chunks=len(all_chunks),
            chunk_chars=sum(len(chunk.text) for chunk in all_chunks),
        ),
        cases=case_results if include_cases else [],
    )


def _acceptable(case: EvaluationCase, kind: str) -> bool:
    target = case.target_kind
    if target is ResponseKind.NO_ANSWER:
        return kind in {ResponseKind.NO_ANSWER.value, ResponseKind.OUT_OF_SCOPE.value}
    return kind == target.value


async def _run_assistant(
    retrieval: RetrievalService,
    corpus: Corpus,
    cases: Sequence[EvaluationCase],
    case_results: Sequence[CaseResult],
    profile_for: Callable[[EvaluationScope], EmployeeProfile],
    restricted: Mapping[tuple[str, str, str], set[str]],
) -> AssistantMetrics:
    assistant = AssistantService(
        retrieval,
        FixtureAnswerabilityGate(),
        FixtureLLMProvider(),
        CitationValidator(),
        GroundingVerifier(),
    )
    citations = CitationValidator()
    grounding = GroundingVerifier()
    outcomes: list[AssistantCaseResult] = []
    for case, case_result in zip(cases, case_results, strict=True):
        profile = profile_for(case.employee_scope)
        scope_key = (
            case.employee_scope.department,
            case.employee_scope.location,
            case.employee_scope.role,
        )
        denied = restricted[scope_key] | case.forbidden_sections
        started = time.perf_counter()
        kind = "error"
        error: str | None = None
        answer_text = ""
        cited: list[str] = []
        context_sections: list[str] = []
        valid_citations = False
        grounded_ok = False
        try:
            verified, context = await assistant.answer_with_context(
                profile, case.question, case.language, case.history
            )
            kind = verified.kind.value
            answer_text = verified.answer if verified.kind is ResponseKind.POLICY_ANSWER else ""
            cited = [corpus.key_by_section_id[item.section_id] for item in verified.citations]
            context_sections = [corpus.key_by_section_id[item.section_id] for item in context]
            if verified.kind is ResponseKind.POLICY_ANSWER:
                valid_citations = citations.validate(verified.citations, context)
                grounded_ok = grounding.verify(
                    GeneratedAnswer(
                        answerable=True, answer=verified.answer, citations=verified.citations
                    ),
                    context,
                )
        except Exception as failure:  # noqa: BLE001 - recorded as a technical failure
            error = _describe(failure)
        elapsed = (time.perf_counter() - started) * 1000
        answered = kind == ResponseKind.POLICY_ANSWER.value
        relevant = case.expected_sections | case.alternate_sections
        unauthorized_context = [key for key in context_sections if key in denied]
        unauthorized_cited = [key for key in cited if key in denied]
        leak = (
            any(facts_present(case.forbidden_facts, answer_text))
            if answered and case.forbidden_facts
            else (False if answered else None)
        )
        coverage = (
            sum(facts_present(case.expected_facts, answer_text)) / len(case.expected_facts)
            if answered and case.expected_facts
            else None
        )
        outcome = AssistantCaseResult(
            observed_kind=kind,
            error=error,
            answer_chars=len(answer_text),
            cited_sections=cited,
            context_sections=context_sections,
            unauthorized_context_sections=unauthorized_context,
            answerability_correct=(kind != "error") and (answered == case.answerable),
            clarification_correct=(kind != "error")
            and ((kind == ResponseKind.CLARIFICATION.value) == case.requires_clarification),
            kind_correct=(kind != "error") and _acceptable(case, kind),
            citation_correct=(
                valid_citations and not unauthorized_cited and bool(set(cited) & relevant)
                if answered
                else None
            ),
            grounded=(grounded_ok and not leak and not unauthorized_cited) if answered else None,
            fact_coverage=coverage,
            forbidden_fact_leak=leak,
            latency_ms=round(elapsed, 3),
        )
        outcomes.append(outcome)
        case_result.assistant = outcome

    def rate(values: Sequence[bool]) -> float:
        return sum(values) / len(values) if values else 0.0

    def optional_rate(values: Sequence[bool | None]) -> float | None:
        present = [value for value in values if value is not None]
        return sum(present) / len(present) if present else None

    required = [case.requires_clarification for case in cases]
    coverages = [item.fact_coverage for item in outcomes if item.fact_coverage is not None]
    latencies = [item.latency_ms for item in outcomes]
    return AssistantMetrics(
        cases=len(outcomes),
        answerability_accuracy=rate([item.answerability_correct for item in outcomes]),
        clarification_accuracy=rate([item.clarification_correct for item in outcomes]),
        clarification_recall=optional_rate(
            [
                item.observed_kind == ResponseKind.CLARIFICATION.value
                for item, needs in zip(outcomes, required, strict=True)
                if needs
            ]
        ),
        false_clarification_rate=rate(
            [
                item.observed_kind == ResponseKind.CLARIFICATION.value
                for item, needs in zip(outcomes, required, strict=True)
                if not needs
            ]
        ),
        kind_accuracy=rate([item.kind_correct for item in outcomes]),
        citation_correctness=optional_rate([item.citation_correct for item in outcomes]),
        grounding_correctness=optional_rate([item.grounded for item in outcomes]),
        fact_coverage=sum(coverages) / len(coverages) if coverages else None,
        forbidden_fact_leak_rate=optional_rate([item.forbidden_fact_leak for item in outcomes]),
        answered_cases=sum(
            item.observed_kind == ResponseKind.POLICY_ANSWER.value for item in outcomes
        ),
        technical_failure_rate=rate([item.error is not None for item in outcomes]),
        unauthorized_context_count=sum(
            len(item.unauthorized_context_sections) for item in outcomes
        ),
        latency_ms_p50=round(percentile(latencies, 0.5), 3),
        latency_ms_p95=round(percentile(latencies, 0.95), 3),
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit(root: Path) -> str | None:
    try:
        completed = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() or None


async def run_benchmark(
    corpus: Corpus,
    cases: Sequence[EvaluationCase],
    matrix: MatrixSpec,
    *,
    dataset_path: Path,
    environment: Mapping[str, str] | None = None,
    only: Sequence[str] | None = None,
    include_cases: bool = True,
    progress: Callable[[str], None] | None = None,
) -> BenchmarkResult:
    selected = [config for config in matrix.configs if not only or config.name in only]
    if only:
        missing = sorted(set(only) - {config.name for config in selected})
        if missing:
            raise ValueError(f"Unknown configuration names: {missing}")
    results: list[ConfigResult] = []
    for config in selected:
        if progress:
            progress(f"running {config.name}")
        results.append(
            await run_config(
                config,
                corpus,
                cases,
                matrix.ks,
                matrix.primary_k,
                environment=environment,
                include_cases=include_cases,
            )
        )
    return BenchmarkResult(
        run_id=uuid.uuid4().hex[:12],
        created_at=datetime.now(UTC),
        git_commit=_git_commit(Path.cwd()),
        dataset=str(dataset_path),
        dataset_sha256=_sha256(dataset_path),
        corpus_fingerprint=corpus.fingerprint,
        case_count=len(cases),
        ks=list(matrix.ks),
        primary_k=matrix.primary_k,
        configs=results,
    )
