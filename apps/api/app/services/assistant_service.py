"""Ephemeral assistant orchestration with authorized, verified answer release."""

from collections.abc import Callable, Sequence
from time import perf_counter
from typing import Protocol

from apps.api.app.models.organization import EmployeeProfile, MembershipStatus
from apps.api.app.repositories.database import CanonicalDatabase
from apps.api.app.services.metrics import MetricsRegistry
from packages.contracts.assistant import (
    ConversationTurn,
    GeneratedAnswer,
    InternalAnswerMode,
    ResponseKind,
    VerifiedAnswer,
)
from packages.contracts.common import Language
from packages.contracts.retrieval import AssistantEvidence, SearchEvidence
from services.assistant.answer_generator import LLMProvider, LLMResponseError
from services.assistant.answerability import AnswerabilityGate
from services.assistant.citations import CitationValidator
from services.assistant.conversation import build_query_plan, canned
from services.assistant.grounding import GroundingVerifier


class EvidenceRetriever(Protocol):
    async def retrieve(
        self, profile: EmployeeProfile, query: str, limit: int
    ) -> list[SearchEvidence]: ...

    async def assistant_context(
        self, profile: EmployeeProfile, evidence: Sequence[SearchEvidence]
    ) -> list[AssistantEvidence]: ...

    async def revalidate_evidence(
        self, profile: EmployeeProfile, evidence: Sequence[SearchEvidence]
    ) -> bool: ...


class VerificationError(RuntimeError):
    pass


class AssistantService:
    def __init__(
        self,
        retrieval: EvidenceRetriever,
        answerability: AnswerabilityGate,
        provider: LLMProvider,
        citations: CitationValidator,
        grounding: GroundingVerifier,
        metrics: MetricsRegistry | None = None,
        database: CanonicalDatabase | None = None,
    ) -> None:
        self.retrieval = retrieval
        self.answerability = answerability
        self.provider = provider
        self.citations = citations
        self.grounding = grounding
        self.metrics = metrics
        self.database = database

    async def answer(
        self,
        profile: EmployeeProfile,
        question: str,
        language: Language,
        history: Sequence[ConversationTurn] = (),
        progress: Callable[[str], None] | None = None,
    ) -> VerifiedAnswer:
        result, _ = await self.answer_with_context(profile, question, language, history, progress)
        return result

    async def answer_with_context(
        self,
        profile: EmployeeProfile,
        question: str,
        language: Language,
        history: Sequence[ConversationTurn] = (),
        progress: Callable[[str], None] | None = None,
    ) -> tuple[VerifiedAnswer, list[AssistantEvidence]]:
        started = perf_counter()
        
        try:
            plan = await self.provider.plan_query(question, history)
        except Exception:
            plan = build_query_plan(question, history)
        
        if plan.answer_mode in {InternalAnswerMode.NO_ANSWER, InternalAnswerMode.ASK_CLARIFICATION}:
            kind_map = {
                "smalltalk": ResponseKind.SMALLTALK,
                "out_of_scope": ResponseKind.OUT_OF_SCOPE,
                "clarification": ResponseKind.CLARIFICATION,
            }
            kind = kind_map.get(plan.intent, ResponseKind.NO_ANSWER)
            result = self._canned(profile, language, kind, question)
            self._observe(kind, started)
            return result, []

        if progress:
            progress("retrieving")
        evidence = await self.retrieval.retrieve(profile, plan.resolved_query, 8)
        if not self.answerability.is_answerable(question, evidence):
            result = self._canned(profile, language, ResponseKind.NO_ANSWER)
            self._observe(result.kind, started)
            return result, []
        if progress:
            progress("reading")
        context = await self.retrieval.assistant_context(profile, evidence)
        if not context or not await self.retrieval.revalidate_evidence(profile, context):
            result = self._canned(profile, language, ResponseKind.NO_ANSWER)
            self._observe(result.kind, started)
            return result, []

        feedback: str | None = None
        for attempt in range(2):
            if attempt and self.metrics:
                self.metrics.observe("assistant_repair", 0)
            if progress:
                progress("generating" if attempt == 0 else "repairing")
            llm_started = perf_counter()
            try:
                generated = await self.provider.generate(
                    question, context, language, repair_feedback=feedback, answer_mode=plan.answer_mode
                )
            except LLMResponseError:
                self._metric("llm", llm_started, failed=True)
                feedback = (
                    "The previous response was malformed. Return valid JSON matching the schema."
                )
                if attempt == 0:
                    continue
                raise VerificationError("Provider response remained malformed") from None
            except Exception:
                self._metric("llm", llm_started, failed=True)
                raise
            self._metric("llm", llm_started)
            if progress:
                progress("verifying")
            verification_started = perf_counter()
            if not generated.answerable:
                self._metric("grounding_verification", verification_started)
                result = self._canned(profile, language, ResponseKind.NO_ANSWER)
                self._observe(result.kind, started)
                return result, []
            if await self._valid(generated, context):
                await self.assert_release_authorized(profile, context)
                self._metric("grounding_verification", verification_started)
                citations = list({item.chunk_id: item for item in generated.citations}.values())
                result = VerifiedAnswer(
                    organization_id=profile.organization_id,
                    kind=ResponseKind.POLICY_ANSWER,
                    answerable=True,
                    answer=generated.answer,
                    language=language,
                    citations=citations,
                    verified=True,
                )
                self._observe(result.kind, started)
                return result, context
            self._metric("grounding_verification", verification_started, failed=True)
            feedback = (
                "The previous answer failed citation or grounding validation. "
                "Use only supported facts and exact supplied citation metadata."
            )
            if attempt == 0:
                continue
        raise VerificationError("Generated answer failed citation or grounding verification")

    async def _valid(self, generated: GeneratedAnswer, context: Sequence[AssistantEvidence]) -> bool:
        return (
            bool(generated.answer.strip())
            and bool(generated.citations)
            and self.citations.validate(generated.citations, context)
            and await self.grounding.verify(generated, context)
        )

    async def assert_release_authorized(
        self, profile: EmployeeProfile, evidence: Sequence[SearchEvidence]
    ) -> None:
        current = profile
        if self.database is not None:
            stored = await self.database.get_one(
                "employee_profiles", profile.organization_id, {"id": profile.id}
            )
            if not stored:
                raise VerificationError("Membership is no longer available")
            current = EmployeeProfile.model_validate(stored)
            if (
                current.identity_subject != profile.identity_subject
                or not current.active
                or current.status is not MembershipStatus.ACTIVE
            ):
                raise VerificationError("Membership is no longer active")
        if evidence and not await self.retrieval.revalidate_evidence(current, evidence):
            raise VerificationError("Policy evidence is no longer available")

    @staticmethod
    def _canned(
        profile: EmployeeProfile,
        language: Language,
        kind: ResponseKind,
        question: str = "",
    ) -> VerifiedAnswer:
        return VerifiedAnswer(
            organization_id=profile.organization_id,
            kind=kind,
            answerable=False,
            answer=canned(kind, language, question),
            language=language,
            citations=[],
            verified=True,
        )

    def _metric(self, name: str, started: float, failed: bool = False) -> None:
        if self.metrics:
            self.metrics.observe(name, (perf_counter() - started) * 1000, failed=failed)

    def _observe(self, kind: ResponseKind, started: float) -> None:
        self._metric(f"assistant_{kind.value}", started)
        self._metric("assistant_total", started)
