"""Ephemeral assistant orchestration with authorized, verified answer release."""

import inspect
from collections.abc import Callable, Sequence
from time import perf_counter
from typing import Any, Protocol

from apps.api.app.models.organization import EmployeeProfile, MembershipStatus
from apps.api.app.repositories.database import CanonicalDatabase
from apps.api.app.services.metrics import MetricsRegistry
from packages.contracts.assistant import (
    AssistantCitation,
    ConversationTurn,
    GeneratedAnswer,
    InternalAnswerMode,
    ResponseKind,
    VerifiedAnswer,
)
from packages.contracts.common import Language
from packages.contracts.retrieval import AssistantEvidence, SearchEvidence
from services.assistant.answer_generator import LLMProvider, LLMResponseError
from services.assistant.answerability import (
    AnswerabilityDecision,
    AnswerabilityGate,
    AnswerabilityResult,
)
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
        policy_reader: Any = None,
    ) -> None:
        self.retrieval = retrieval
        self.answerability = answerability
        self.provider = provider
        self.citations = citations
        self.grounding = grounding
        self.metrics = metrics
        self.database = database
        self.policy_reader = policy_reader

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
        if not evidence:
            gate_decision = await self._evaluate_answerability(question, [])
            if gate_decision == AnswerabilityDecision.GREETING:
                result = self._canned(profile, language, ResponseKind.SMALLTALK, question)
                self._observe(result.kind, started)
                return result, []
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

        # QA-05: Check broad policy question UPFRONT on identifiable large SOP
        if self._is_broad_policy_question(question, context):
            overview = self._build_sections_overview(profile, language, context)
            if overview is not None:
                await self.assert_release_authorized(profile, context)
                self._observe(overview.kind, started)
                return overview, context

        # QA-04: Evaluate answerability gate using the full authorized context
        gate_decision = await self._evaluate_answerability(question, context)
        if gate_decision == AnswerabilityDecision.GREETING:
            result = self._canned(profile, language, ResponseKind.SMALLTALK, question)
            self._observe(result.kind, started)
            return result, []
        if gate_decision == AnswerabilityDecision.CLARIFICATION:
            result = self._canned(profile, language, ResponseKind.CLARIFICATION)
            self._observe(result.kind, started)
            return result, []
        if gate_decision not in {
            AnswerabilityDecision.ANSWERABLE,
            AnswerabilityDecision.SYNTHESIS,
        }:
            result = self._canned(profile, language, ResponseKind.NO_ANSWER)
            self._observe(result.kind, started)
            return result, []
        if gate_decision == AnswerabilityDecision.SYNTHESIS:
            plan.answer_mode = InternalAnswerMode.SYNTHESIZE_MULTIPLE_POLICIES

        feedback: str | None = None
        for attempt in range(2):
            if attempt and self.metrics:
                self.metrics.observe("assistant_repair", 0)
            if progress:
                progress("generating" if attempt == 0 else "repairing")
            llm_started = perf_counter()
            try:
                generated = await self.provider.generate(
                    question,
                    context,
                    language,
                    repair_feedback=feedback,
                    answer_mode=plan.answer_mode,
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
            reason = (
                getattr(self.grounding, "last_rejection_reason", None)
                or "grounding verification"
            )
            feedback = (
                f"The previous answer failed {reason}. "
                "Use only supported facts and exact supplied citation metadata."
            )
            if attempt == 0:
                continue

        if self._is_broad_policy_question(question, context):
            overview = self._build_sections_overview(profile, language, context)
            if overview is not None:
                await self.assert_release_authorized(profile, context)
                self._observe(overview.kind, started)
                return overview, context

        raise VerificationError("Generated answer failed citation or grounding verification")

    def _is_broad_policy_question(
        self, question: str, context: Sequence[AssistantEvidence]
    ) -> bool:
        q = question.strip().casefold()

        narrow_prefixes = (
            "how ", "how's ", "when ", "who ", "where ", "why ",
            "is ", "are ", "can ", "could ", "should ", "do ", "does ", "will ", "would ",
            "kaise ", "kese ", "kab ", "kaun ", "kon ", "kahan ", "kyun ", "kiun ",
            "کیسے ", "کب ", "کون ", "کہاں ", "کیوں ",
        )
        if any(q.startswith(prefix) for prefix in narrow_prefixes):
            return False

        narrow_attributes = (
            "deadline", "due date", "capacity", "quantity", "limit", "maximum",
            "minimum", "fee", "penalty", "approval authority", "who approves",
        )
        if any(attr in q for attr in narrow_attributes):
            return False

        for item in context:
            sec = item.heading_path[-1] if item.heading_path else ""
            if sec and len(sec) > 3 and sec.casefold() in q:
                if sec.casefold() != item.policy_title.casefold():
                    return False

        broad_indicators = (
            "sop", "policy", "policies", "procedure", "procedures",
            "overview", "summary", "guideline", "guidelines",
            "پالیسی", "ایس او پی",
        )
        if any(ind in q for ind in broad_indicators):
            return True

        for item in context:
            if item.policy_title and item.policy_title.casefold() in q:
                return True

        return False

    def _build_sections_overview(
        self,
        profile: EmployeeProfile,
        language: Language,
        context: Sequence[AssistantEvidence],
    ) -> VerifiedAnswer | None:
        if not context:
            return None

        # Check if an identifiable SOP exists with canonical sections from policy reader
        policy_ids = list(dict.fromkeys(item.policy_id for item in context))
        canonical_sections: list[tuple[str, str, SearchEvidence]] = []

        if len(policy_ids) == 1 and getattr(self, "policy_reader", None) is not None:
            policy_id = policy_ids[0]
            try:
                reader_doc = self.policy_reader.read_policy(profile, policy_id)
                if reader_doc and len(reader_doc.sections) >= 2:
                    context_by_sec = {item.section_id: item for item in context}
                    fallback_chunk = context[0]
                    for sec in reader_doc.sections:
                        chunk_ref = context_by_sec.get(sec.section_id, fallback_chunk)
                        sec_name = (
                            sec.heading
                            if sec.heading
                            else sec.heading_path[-1]
                            if sec.heading_path
                            else reader_doc.title
                        )
                        canonical_sections.append((reader_doc.title, sec_name, chunk_ref))
            except Exception:
                canonical_sections = []

        if not canonical_sections:
            seen_section_keys: set[tuple[str, str]] = set()
            for item in context:
                sec_key = (item.policy_id, item.section_id)
                if sec_key not in seen_section_keys:
                    seen_section_keys.add(sec_key)
                    sec_name = item.heading_path[-1] if item.heading_path else item.policy_title
                    canonical_sections.append((item.policy_title, sec_name, item))
                    if len(canonical_sections) >= 8:
                        break

        if len(canonical_sections) < 2:
            return None

        unique_policy_titles = list(dict.fromkeys(pol for pol, _, _ in canonical_sections))
        if len(unique_policy_titles) == 1:
            policy_name = unique_policy_titles[0]
            if language == Language.URDU:
                header = f"{policy_name} میں آپ کی مجاز پالیسیوں سے یہ سیکشنز ملے ہیں:\n\n"
                prompt_line = "\n\nآپ کس سیکشن کے بارے میں تفصیلات جاننا چاہتے ہیں؟"
            elif language == Language.ROMAN_URDU:
                header = (
                    f"{policy_name} mein aap ki authorized policies se yeh sections miley hain:\n\n"
                )
                prompt_line = "\n\nKis section ke baare mein aap tafseelat jaanna chahte hain?"
            else:
                header = (
                    f"{policy_name} covers these sections found in your authorized policies:\n\n"
                )
                prompt_line = "\n\nWhich section would you like details on?"
            body = "\n".join(f"{i + 1}. {sec}" for i, (_, sec, _) in enumerate(canonical_sections))
        else:
            if language == Language.URDU:
                header = "آپ کی مجاز پالیسیوں میں یہ سیکشنز ملے ہیں:\n\n"
                prompt_line = "\n\nآپ کس سیکشن کے بارے میں تفصیلات جاننا چاہتے ہیں؟"
            elif language == Language.ROMAN_URDU:
                header = "Aap ki authorized policies mein yeh sections miley hain:\n\n"
                prompt_line = "\n\nKis section ke baare mein aap tafseelat jaanna chahte hain?"
            else:
                header = "The following sections were found in your authorized policies:\n\n"
                prompt_line = "\n\nWhich section would you like details on?"
            body = "\n".join(
                f"{i + 1}. {pol} → {sec}" for i, (pol, sec, _) in enumerate(canonical_sections)
            )

        overview_text = header + body + prompt_line

        citations = [
            AssistantCitation(
                chunk_id=item.chunk_id,
                policy_id=item.policy_id,
                policy_title=item.policy_title,
                section_id=item.section_id,
                heading_path=item.heading_path,
                document_id=item.source.source_document_id,
                source=item.source,
            )
            for _, _, item in canonical_sections
        ]

        return VerifiedAnswer(
            organization_id=profile.organization_id,
            kind=ResponseKind.CLARIFICATION,
            answerable=False,
            answer=overview_text,
            language=language,
            citations=citations,
            verified=True,
        )

    async def _valid(
        self, generated: GeneratedAnswer, context: Sequence[AssistantEvidence]
    ) -> bool:
        if not generated.answer.strip() or not generated.citations:
            if hasattr(self.grounding, "last_rejection_reason"):
                self.grounding.last_rejection_reason = "citation validation"
            return False
        if not self.citations.validate(generated.citations, context):
            if hasattr(self.grounding, "last_rejection_reason"):
                self.grounding.last_rejection_reason = "citation validation"
            return False
        return await self.grounding.verify(generated, context)

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

    async def _evaluate_answerability(
        self, question: str, evidence: Sequence[SearchEvidence]
    ) -> AnswerabilityDecision:
        if hasattr(self.answerability, "evaluate"):
            eval_fn = self.answerability.evaluate
            eval_call = eval_fn(question, evidence)
            eval_res = await eval_call if inspect.isawaitable(eval_call) else eval_call
            if isinstance(eval_res, AnswerabilityResult):
                return eval_res.decision
            if isinstance(eval_res, AnswerabilityDecision):
                return eval_res
        is_ans_fn = self.answerability.is_answerable
        ans_call = is_ans_fn(question, evidence)
        ans_bool = await ans_call if inspect.isawaitable(ans_call) else ans_call
        return (
            AnswerabilityDecision.ANSWERABLE
            if ans_bool
            else AnswerabilityDecision.INSUFFICIENT_EVIDENCE
        )
