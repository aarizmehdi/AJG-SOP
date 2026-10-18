import json
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import overload

import httpx
from pydantic import ValidationError

from packages.contracts.assistant import (
    AssistantCitation,
    ConversationTurn,
    GeneratedAnswer,
    InternalAnswerMode,
)
from packages.contracts.common import Language
from packages.contracts.retrieval import SearchEvidence
from services.assistant.answer_prompts import answer_messages, answer_system_prompt
from services.assistant.chat_transport import ChatCompletionTransport
from services.assistant.conversation import QueryPlan, build_query_plan
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
        answer_mode: InternalAnswerMode | None = None,
    ) -> GeneratedAnswer:
        raise NotImplementedError

    async def plan_query(
        self,
        question: str,
        history: Sequence[ConversationTurn],
    ) -> QueryPlan:
        return build_query_plan(question, history)


class FixtureLLMProvider(LLMProvider):
    provider_id = "fixture"
    model_id = "fixture-grounded-v1"

    async def generate(
        self,
        question: str,
        evidence: Sequence[SearchEvidence],
        language: Language,
        repair_feedback: str | None = None,
        answer_mode: InternalAnswerMode | None = None,
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

    async def plan_query(
        self,
        question: str,
        history: Sequence[ConversationTurn],
    ) -> QueryPlan:
        return build_query_plan(question, history)


class UnavailableLLMProvider(LLMProvider):
    provider_id = "unavailable"
    model_id = "unconfigured"

    async def generate(
        self,
        question: str,
        evidence: Sequence[SearchEvidence],
        language: Language,
        repair_feedback: str | None = None,
        answer_mode: InternalAnswerMode | None = None,
    ) -> GeneratedAnswer:
        raise LLMUnavailableError("The configured LLM provider is unavailable")

    async def plan_query(
        self,
        question: str,
        history: Sequence[ConversationTurn],
    ) -> QueryPlan:
        raise LLMUnavailableError("The configured LLM provider is unavailable")


class DeepSeekLLMProvider(LLMProvider):
    """Controlled rollback adapter using either the pooled transport or direct client."""

    provider_id = "deepseek"

    @overload
    def __init__(
        self,
        transport_or_api_key: ChatCompletionTransport,
        base_url_or_model: str = "deepseek-flash",
        model_or_temperature: float = 0.2,
    ) -> None: ...

    @overload
    def __init__(
        self,
        transport_or_api_key: str,
        base_url_or_model: str = "https://api.deepseek.com",
        model_or_temperature: str = "deepseek-flash",
        temperature: float = 0.2,
    ) -> None: ...

    def __init__(
        self,
        transport_or_api_key: ChatCompletionTransport | str,
        base_url_or_model: str = "https://api.deepseek.com",
        model_or_temperature: str | float = "deepseek-flash",
        temperature: float = 0.2,
    ) -> None:
        if isinstance(transport_or_api_key, ChatCompletionTransport):
            self.transport: ChatCompletionTransport | None = transport_or_api_key
            self.model_id = (
                base_url_or_model
                if base_url_or_model != "https://api.deepseek.com"
                else "deepseek-flash"
            )
            self._temperature = (
                float(model_or_temperature)
                if isinstance(model_or_temperature, (int, float))
                else temperature
            )
            self._api_key: str | None = None
            self._base_url: str | None = None
        else:
            self.transport = None
            self._api_key = transport_or_api_key
            self._base_url = base_url_or_model.rstrip("/")
            self.model_id = (
                str(model_or_temperature)
                if isinstance(model_or_temperature, str)
                else "deepseek-flash"
            )
            self._temperature = temperature

    async def generate(
        self,
        question: str,
        evidence: Sequence[SearchEvidence],
        language: Language,
        repair_feedback: str | None = None,
        answer_mode: InternalAnswerMode | None = None,
    ) -> GeneratedAnswer:
        if self.transport is not None:
            return await self.transport.complete(
                messages=answer_messages(
                    question, evidence, language, repair_feedback, answer_mode
                ),
                response_model=GeneratedAnswer,
                model=self.model_id,
                temperature=self._temperature,
            )
        msgs = answer_messages(question, evidence, language, repair_feedback, answer_mode)
        payload = {
            "model": self.model_id,
            "thinking": {"type": "disabled"},
            "messages": msgs,
            "response_format": {"type": "json_object"},
            "max_tokens": 1200,
            "temperature": self._temperature,
            "stream": False,
        }
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            return GeneratedAnswer.model_validate_json(content)
        except httpx.HTTPError as error:
            raise LLMUnavailableError("DeepSeek is unavailable") from error
        except (KeyError, IndexError, TypeError, ValueError, ValidationError) as error:
            raise LLMResponseError("DeepSeek response could not be validated") from error

    async def plan_query(
        self,
        question: str,
        history: Sequence[ConversationTurn],
    ) -> QueryPlan:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a Query Planner for the AJG SOP Assistant. "
                    "Determine the intent of the user's question, whether it is a follow-up, "
                    "and what exactly should be searched in the policy library. "
                    "Return only a JSON object matching this schema:\n"
                    "{\n"
                    '  "intent": "question" | "smalltalk" | "out_of_scope" | "clarification",\n'
                    '  "original_question": "<the user\'s current question>",\n'
                    '  "resolved_query": "<the full search string resolving any conversational references like \'second one\', or the question itself>",\n'  # noqa: E501
                    '  "is_follow_up": true | false,\n'
                    '  "answer_mode": "answer" | "synthesize_multiple_policies" | "ask_clarification" | "no_answer"\n'  # noqa: E501
                    "}\n"
                    "Use 'synthesize_multiple_policies' if the user explicitly asks to compare across multiple policies. "  # noqa: E501
                    "Use 'ask_clarification' if the question is completely ambiguous. "
                    "Use 'no_answer' if the intent is out_of_scope or smalltalk. "
                    "Use 'answer' for normal or follow-up factual questions. "
                    "Crucially, if the user says 'second one' or similar, look at the assistant's previous response to resolve what that is in 'resolved_query'."  # noqa: E501
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": question,
                        "history": [
                            {"role": t.role.value, "content": t.content} for t in history[-5:]
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        if self.transport is not None:
            return await self.transport.complete(
                messages=messages,
                response_model=QueryPlan,
                model=self.model_id,
                temperature=0.0,
            )
        payload = {
            "model": self.model_id,
            "thinking": {"type": "disabled"},
            "messages": messages,
            "response_format": {"type": "json_object"},
            "max_tokens": 500,
            "temperature": 0.0,
            "stream": False,
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            return QueryPlan.model_validate_json(content)
        except httpx.HTTPError as error:
            raise LLMUnavailableError("DeepSeek is unavailable for query planning") from error
        except (KeyError, IndexError, TypeError, ValueError, ValidationError) as error:
            raise LLMResponseError(
                "DeepSeek query planning response could not be validated"
            ) from error

    _system_prompt = staticmethod(answer_system_prompt)
