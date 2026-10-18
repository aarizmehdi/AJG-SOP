from abc import ABC, abstractmethod
from collections.abc import Sequence

from packages.contracts.assistant import AssistantCitation, GeneratedAnswer
from packages.contracts.common import Language
from packages.contracts.retrieval import SearchEvidence
from services.assistant.answer_prompts import answer_messages, answer_system_prompt
from services.assistant.chat_transport import ChatCompletionTransport
from services.assistant.llm_errors import (
    LLMResponseError as LLMResponseError,
)
from services.assistant.llm_errors import (
    LLMUnavailableError as LLMUnavailableError,
)


class LLMProvider(ABC):
    provider_id: str
    model_id: str

    @abstractmethod
    async def generate(
        self,
        question: str,
        evidence: Sequence[SearchEvidence],
        language: Language,
        repair_feedback: str | None = None,
    ) -> GeneratedAnswer:
        raise NotImplementedError


class FixtureLLMProvider(LLMProvider):
    provider_id = "fixture"
    model_id = "fixture-grounded-v1"

    async def generate(
        self,
        question: str,
        evidence: Sequence[SearchEvidence],
        language: Language,
        repair_feedback: str | None = None,
    ) -> GeneratedAnswer:
        if not evidence:
            return GeneratedAnswer(answerable=False, answer="", citations=[])
        item = evidence[0]
        content = getattr(item, "full_text", item.excerpt)
        answer = {
            Language.ENGLISH: f"According to the available SOP section: {content}",
            Language.URDU: f"دستیاب ایس او پی حصے کے مطابق: {content}",
            Language.ROMAN_URDU: f"Dastiyab SOP section ke mutabiq: {content}",
        }[language]
        return GeneratedAnswer(
            answerable=True,
            answer=answer,
            citations=[
                AssistantCitation(
                    chunk_id=item.chunk_id,
                    policy_id=item.policy_id,
                    policy_title=item.policy_title,
                    section_id=item.section_id,
                    heading_path=item.heading_path,
                    document_id=item.source.source_document_id,
                    source=item.source,
                )
            ],
        )


class UnavailableLLMProvider(LLMProvider):
    provider_id = "unavailable"
    model_id = "unconfigured"

    async def generate(
        self,
        question: str,
        evidence: Sequence[SearchEvidence],
        language: Language,
        repair_feedback: str | None = None,
    ) -> GeneratedAnswer:
        raise LLMUnavailableError("The configured LLM provider is unavailable")


class DeepSeekLLMProvider(LLMProvider):
    """Controlled rollback adapter using the same lifespan-owned connection pool."""

    provider_id = "deepseek"

    def __init__(
        self,
        transport: ChatCompletionTransport,
        model: str = "deepseek-flash",
        temperature: float = 0.2,
    ) -> None:
        self.transport = transport
        self.model_id = model
        self._temperature = temperature

    async def generate(
        self,
        question: str,
        evidence: Sequence[SearchEvidence],
        language: Language,
        repair_feedback: str | None = None,
    ) -> GeneratedAnswer:
        return await self.transport.complete(
            messages=answer_messages(question, evidence, language, repair_feedback),
            response_model=GeneratedAnswer,
            model=self.model_id,
            temperature=self._temperature,
        )

    _system_prompt = staticmethod(answer_system_prompt)
