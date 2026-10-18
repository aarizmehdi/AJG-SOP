"""OpenRouter answer adapter; no retrieval, planning or semantic-verifier logic."""

from collections.abc import Sequence

from packages.contracts.assistant import GeneratedAnswer
from packages.contracts.common import Language
from packages.contracts.retrieval import SearchEvidence
from services.assistant.answer_generator import LLMProvider
from services.assistant.answer_prompts import answer_messages
from services.assistant.chat_transport import ChatCompletionTransport


class OpenRouterLLMProvider(LLMProvider):
    provider_id = "openrouter"

    def __init__(
        self,
        transport: ChatCompletionTransport,
        model: str = "deepseek/deepseek-v4.1-flash-1017",
        fallback_model: str = "deepseek/deepseek-v4-flash",
        temperature: float = 0.2,
    ) -> None:
        self.transport = transport
        self.model_id = model
        self.fallback_model = fallback_model
        self.temperature = temperature

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
            fallback_model=self.fallback_model,
            temperature=self.temperature,
        )
