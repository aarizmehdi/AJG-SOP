"""Ephemeral assistant orchestration with authorized, verified answer release."""

import inspect
import re
from collections.abc import Callable, Sequence
from time import perf_counter
from typing import Protocol

from apps.api.app.models.organization import EmployeeProfile, MembershipStatus
from apps.api.app.repositories.database import CanonicalDatabase
from apps.api.app.services.metrics import MetricsRegistry
from packages.contracts.assistant import (
    AssistantCitation,
    AssistantSectionOption,
    ConversationTurn,
    GeneratedAnswer,
    InternalAnswerMode,
    ResponseKind,
    VerifiedAnswer,
)
from packages.contracts.common import Language
from packages.contracts.retrieval import AssistantEvidence, PolicyReaderDocument, SearchEvidence
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


class AuthorizedPolicyReader(Protocol):
    def read_policy(
        self, profile: EmployeeProfile, policy_id: str
    ) -> PolicyReaderDocument | None: ...


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
        policy_reader: AuthorizedPolicyReader | None = None,
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

        # Planning resolves references only. No model or client history supplies policy facts.
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
        if (
            not plan.is_follow_up
            and plan.answer_mode == InternalAnswerMode.ANSWER
            and self._is_broad_policy_question(question, context)
        ):
            overview = self._build_sections_overview(profile, language, context)
            if overview is not None:
                if progress:
                    progress("verifying")
                await self.assert_release_authorized(profile, context, overview.section_options)
                self._observe(overview.kind, started)
                return overview, context

        # QA-04: Evaluate answerability gate using the full authorized context
        gate_decision = await self._evaluate_answerability(plan.resolved_query, context)
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
                    plan.resolved_query,
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
                getattr(self.grounding, "last_rejection_reason", None) or "grounding verification"
            )
            feedback = (
                f"The previous answer failed {reason}. "
                "Use only supported facts and exact supplied citation metadata."
            )
            if attempt == 0:
                continue

        if (
            not plan.is_follow_up
            and plan.answer_mode == InternalAnswerMode.ANSWER
            and self._is_broad_policy_question(question, context)
        ):
            overview = self._build_sections_overview(profile, language, context)
            if overview is not None:
                await self.assert_release_authorized(profile, context, overview.section_options)
                self._observe(overview.kind, started)
                return overview, context

        raise VerificationError("Generated answer failed citation or grounding verification")

    def _is_broad_policy_question(
        self, question: str, context: Sequence[AssistantEvidence]
    ) -> bool:
        q = question.strip().casefold()

        narrow_prefixes = (
            "how ",
            "how's ",
            "when ",
            "who ",
            "where ",
            "why ",
            "is ",
            "are ",
            "can ",
            "could ",
            "should ",
            "do ",
            "does ",
            "will ",
            "would ",
            "kaise ",
            "kese ",
            "kab ",
            "kaun ",
            "kon ",
            "kahan ",
            "kyun ",
            "kiun ",
            "کیسے ",
            "کب ",
            "کون ",
            "کہاں ",
            "کیوں ",
        )
        if any(q.startswith(prefix) for prefix in narrow_prefixes):
            return False

        narrow_attributes = (
            "deadline",
            "due date",
            "capacity",
            "quantity",
            "limit",
            "maximum",
            "minimum",
            "fee",
            "penalty",
            "approval authority",
            "who approves",
        )
        if any(attr in q for attr in narrow_attributes):
            return False

        for item in context:
            sec = item.heading_path[-1] if item.heading_path else ""
            if sec and len(sec) > 3 and sec.casefold() in q:
                if sec.casefold() != item.policy_title.casefold():
                    return False

        broad_indicators = (
            "sop",
            "policy",
            "policies",
            "procedure",
            "procedures",
            "overview",
            "summary",
            "guideline",
            "guidelines",
            "پالیسی",
            "ایس او پی",
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

        # Canonical navigation is independent of retrieval chunk citations.
        groups: list[list[AssistantSectionOption]] = []
        for policy_id in dict.fromkeys(item.policy_id for item in context):
            items = [item for item in context if item.policy_id == policy_id]
            versions = {item.version_id for item in items}
            options: list[AssistantSectionOption] = []
            if self.policy_reader is not None:
                doc = self.policy_reader.read_policy(profile, policy_id)
                if not doc or doc.policy_id != policy_id:
                    continue
                for section in doc.sections:
                    if (
                        section.organization_id != profile.organization_id
                        or section.policy_id != policy_id
                        or section.version_id not in versions
                    ):
                        continue
                    options.append(
                        AssistantSectionOption(
                            policy_id=policy_id,
                            policy_title=doc.title,
                            version_id=section.version_id,
                            section_id=section.section_id,
                            heading=section.heading,
                            heading_path=section.heading_path,
                            source=section.source,
                        )
                    )
            else:
                # Fixture/service callers may only have already-authorized chunks.
                for item in items:
                    options.append(
                        AssistantSectionOption(
                            policy_id=item.policy_id,
                            policy_title=item.policy_title,
                            version_id=item.version_id,
                            section_id=item.section_id,
                            heading=item.heading_path[-1]
                            if item.heading_path
                            else item.policy_title,
                            heading_path=item.heading_path,
                            source=item.source,
                        )
                    )
            unique = {option.section_id: option for option in options}
            if unique:
                groups.append(list(unique.values()))

        # Interleave policies so a mixed result cannot hide the second SOP.
        total = sum(len(group) for group in groups)
        selected = [
            group[index]
            for index in range(min(8, max((len(group) for group in groups), default=0)))
            for group in groups
            if index < len(group)
        ][:8]
        if len(selected) < 2:
            return None

        citations: dict[str, AssistantCitation] = {}
        for option in selected:
            for item in context:
                if (
                    item.organization_id == profile.organization_id
                    and item.policy_id == option.policy_id
                    and item.version_id == option.version_id
                    and item.section_id == option.section_id
                    and item.policy_title == option.policy_title
                    and item.heading_path == option.heading_path
                    and item.source == option.source
                ):
                    citations.setdefault(
                        item.chunk_id,
                        AssistantCitation(
                            chunk_id=item.chunk_id,
                            policy_id=item.policy_id,
                            policy_title=item.policy_title,
                            section_id=item.section_id,
                            heading_path=item.heading_path,
                            document_id=item.source.source_document_id,
                            source=item.source,
                        ),
                    )
                    break

        if language == Language.URDU:
            header = "آپ کی مجاز، شائع شدہ پالیسیوں کے سیکشنز:\n\n"
            prompt = "\n\nتفصیل کے لیے کوئی سیکشن منتخب کریں یا اس کا نام پوچھیں۔"
            more = (
                f"\n\nکل {total} دستیاب سیکشنز میں سے {len(selected)} دکھائے گئے ہیں۔ "
                "مکمل پالیسی کھولیں۔"
            )
        elif language == Language.ROMAN_URDU:
            header = "Aap ki authorized, published policies ke sections:\n\n"
            prompt = "\n\nTafseel ke liye section chunein ya us ka naam poochhein."
            more = (
                f"\n\n{total} dastiyab sections mein se {len(selected)} dikhaye gaye hain. "
                "Poori policy kholein."
            )
        else:
            header = "Sections in your authorized, published policies:\n\n"
            prompt = (
                "\n\nWhich section would you like details on? "
                "Select a heading or ask about a section by name or number."
            )
            more = (
                f"\n\nShowing {len(selected)} of {total} available sections. "
                "Open the policy reader for the full contents."
            )

        def plain(text: str) -> str:
            # Source headings are data, not Markdown/HTML instructions.
            return re.sub(r"([\\`*_{}\[\]<>|])", r"\\\1", " ".join(text.split()))

        multiple = len({item.policy_id for item in selected}) > 1
        if not multiple:
            header = plain(selected[0].policy_title) + "\n\n" + header
        body = "\n".join(
            f"{index}. {plain(item.policy_title) + ' → ' if multiple else ''}{plain(item.heading)}"
            for index, item in enumerate(selected, 1)
        )
        return VerifiedAnswer(
            organization_id=profile.organization_id,
            kind=ResponseKind.CLARIFICATION,
            answerable=False,
            answer=header + body + (more if total > len(selected) else "") + prompt,
            language=language,
            citations=list(citations.values()),
            section_options=selected,
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
        self,
        profile: EmployeeProfile,
        evidence: Sequence[SearchEvidence],
        section_options: Sequence[AssistantSectionOption] = (),
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
        if section_options and self.policy_reader is not None:
            documents = {
                policy_id: self.policy_reader.read_policy(current, policy_id)
                for policy_id in dict.fromkeys(item.policy_id for item in section_options)
            }
            for item in section_options:
                doc = documents.get(item.policy_id)
                if (
                    not doc
                    or doc.title != item.policy_title
                    or not any(
                        section.organization_id == current.organization_id
                        and section.policy_id == item.policy_id
                        and section.version_id == item.version_id
                        and section.section_id == item.section_id
                        and section.heading == item.heading
                        and section.heading_path == item.heading_path
                        and section.source == item.source
                        for section in doc.sections
                    )
                ):
                    raise VerificationError("Policy navigation is no longer authorized")

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
