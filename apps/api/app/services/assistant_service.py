from time import perf_counter
from typing import Protocol
from uuid import uuid4

from apps.api.app.models.organization import EmployeeProfile
from apps.api.app.services.foundation_store import FoundationStore
from apps.api.app.services.metrics import MetricsRegistry
from packages.contracts.assistant import (
    ChatMessage,
    ChatSession,
    MessageRole,
    VerifiedAnswer,
)
from packages.contracts.common import Language
from packages.contracts.retrieval import SearchEvidence
from services.assistant.answer_generator import LLMProvider
from services.assistant.answerability import AnswerabilityGate
from services.assistant.citations import CitationValidator
from services.assistant.grounding import GroundingVerifier


class EvidenceRetriever(Protocol):
    async def retrieve(
        self, profile: EmployeeProfile, query: str, limit: int
    ) -> list[SearchEvidence]: ...


class VerificationError(RuntimeError):
    pass


class AssistantService:
    def __init__(
        self,
        store: FoundationStore,
        retrieval: EvidenceRetriever,
        answerability: AnswerabilityGate,
        provider: LLMProvider,
        citations: CitationValidator,
        grounding: GroundingVerifier,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self.store = store
        self.retrieval = retrieval
        self.answerability = answerability
        self.provider = provider
        self.citations = citations
        self.grounding = grounding
        self.metrics = metrics

    async def answer(
        self,
        profile: EmployeeProfile,
        question: str,
        language: Language,
        session_id: str | None = None,
    ) -> VerifiedAnswer:
        session = self._session(profile, language, session_id)
        evidence = await self.retrieval.retrieve(profile, question, 8)
        self._message(profile, session.id, MessageRole.USER, question, verified=True)
        if not self.answerability.is_answerable(question, evidence):
            if self.metrics:
                self.metrics.observe("answerability", 0, failed=True)
            answer = self._no_answer(language, session.id, profile.organization_id)
            self._message(profile, session.id, MessageRole.ASSISTANT, answer.answer, verified=True)
            return answer
        llm_started = perf_counter()
        try:
            generated = await self.provider.generate(question, evidence, language)
        except Exception:
            if self.metrics:
                self.metrics.observe("llm", (perf_counter() - llm_started) * 1000, failed=True)
            raise
        if self.metrics:
            self.metrics.observe("llm", (perf_counter() - llm_started) * 1000)
        if (
            not generated.answerable
            or not self.citations.validate(generated.citations, evidence)
            or not self.grounding.verify(generated, evidence)
        ):
            if self.metrics:
                self.metrics.observe("grounding_verification", 0, failed=True)
            raise VerificationError("Generated answer failed citation or grounding verification")
        if self.metrics:
            self.metrics.observe("grounding_verification", 0)
        result = VerifiedAnswer(
            organization_id=profile.organization_id,
            answerable=True,
            answer=generated.answer,
            language=language,
            citations=generated.citations,
            verified=True,
            session_id=session.id,
        )
        self._message(profile, session.id, MessageRole.ASSISTANT, result.answer, verified=True)
        return result

    def _session(
        self, profile: EmployeeProfile, language: Language, session_id: str | None
    ) -> ChatSession:
        if session_id:
            existing = self.store.chat_sessions.get(session_id)
            if (
                not existing
                or existing.organization_id != profile.organization_id
                or existing.employee_id != profile.id
            ):
                raise PermissionError("Chat session is unavailable")
            if existing.language is not language:
                raise ValueError("Session language cannot change implicitly")
            return existing
        session = ChatSession(
            id=f"chat-{uuid4().hex[:12]}",
            organization_id=profile.organization_id,
            employee_id=profile.id,
            language=language,
        )
        self.store.chat_sessions[session.id] = session
        return session

    def _message(
        self,
        profile: EmployeeProfile,
        session_id: str,
        role: MessageRole,
        content: str,
        verified: bool,
    ) -> None:
        message = ChatMessage(
            id=f"message-{uuid4().hex[:12]}",
            organization_id=profile.organization_id,
            session_id=session_id,
            role=role,
            content=content,
            verified=verified,
        )
        self.store.chat_messages.append(message)

    @staticmethod
    def _no_answer(
        language: Language, session_id: str, organization_id: str
    ) -> VerifiedAnswer:
        text = {
            Language.ENGLISH: "I couldn't find guidance for that in the SOPs available to you.",
            Language.URDU: "مجھے آپ کے لیے دستیاب ایس او پیز میں اس بارے میں رہنمائی نہیں ملی۔",
            Language.ROMAN_URDU: (
                "Mujhe aap ke liye dastiyab SOPs mein is bare mein rehnumai nahi mili."
            ),
        }[language]
        return VerifiedAnswer(
            organization_id=organization_id,
            answerable=False,
            answer=text,
            language=language,
            citations=[],
            verified=True,
            session_id=session_id,
        )
