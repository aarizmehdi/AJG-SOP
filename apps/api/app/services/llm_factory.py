"""Composition root for the existing LLM interface and a caller-owned HTTP pool."""

import httpx

from apps.api.app.config import Settings
from apps.api.app.services.metrics import MetricsRegistry
from services.assistant.answer_generator import (
    DeepSeekLLMProvider,
    FixtureLLMProvider,
    LLMProvider,
    UnavailableLLMProvider,
)
from services.assistant.answerability import (
    AnswerabilityGate,
    DeepSeekAnswerabilityGate,
    FixtureAnswerabilityGate,
    UnavailableAnswerabilityGate,
)
from services.assistant.chat_transport import ChatCompletionTransport
from services.assistant.grounding import (
    DeepSeekSemanticVerifier,
    FixtureSemanticVerifier,
    SemanticVerifier,
    UnavailableSemanticVerifier,
)
from services.assistant.openrouter import OpenRouterLLMProvider


def build_chat_transport(
    settings: Settings, client: httpx.AsyncClient, metrics: MetricsRegistry
) -> ChatCompletionTransport | None:
    if settings.llm_provider == "fixture":
        if settings.app_mode == "live":
            raise ValueError("Fixture LLM is prohibited in live mode")
        return None
    secret = (
        settings.openrouter_api_key
        if settings.llm_provider == "openrouter"
        else settings.deepseek_api_key
    )
    if not secret or not secret.get_secret_value().strip():
        if settings.app_mode == "live":
            raise ValueError(f"Missing {settings.llm_provider.upper()}_API_KEY")
        return None
    options: dict[str, object]
    if settings.llm_provider == "openrouter":
        routing: dict[str, object] = {
            "require_parameters": True,
            "data_collection": "deny",
            "zdr": True,
            # Disable upstream failover: it may retry moderation/refusal errors.
            # Our transport owns the explicit availability-only model fallback.
            "allow_fallbacks": False,
        }
        if settings.openrouter_allowed_providers:
            routing["only"] = list(settings.openrouter_allowed_providers)
        options = {"provider": routing, "reasoning": {"enabled": False, "exclude": True}}
        base_url = settings.openrouter_base_url
    else:
        options = {"thinking": {"type": "disabled"}}
        base_url = settings.deepseek_base_url
    return ChatCompletionTransport(
        client,
        provider_id=settings.llm_provider,
        api_key=secret.get_secret_value(),
        base_url=base_url,
        metrics=metrics,
        request_timeout_seconds=settings.llm_request_timeout_seconds,
        structured_schema=settings.llm_provider == "openrouter",
        options=options,
    )


def build_llm_provider(
    settings: Settings, client: httpx.AsyncClient, metrics: MetricsRegistry
) -> LLMProvider:
    if settings.llm_provider == "fixture":
        if settings.app_mode == "live":
            raise ValueError("Fixture LLM is prohibited in live mode")
        return FixtureLLMProvider()
    transport = build_chat_transport(settings, client, metrics)
    if transport is None:
        return UnavailableLLMProvider()
    if settings.llm_provider == "openrouter":
        return OpenRouterLLMProvider(
            transport,
            settings.openrouter_model,
            settings.openrouter_fallback_model,
            settings.openrouter_temperature,
        )
    return DeepSeekLLMProvider(transport, settings.deepseek_model, settings.deepseek_temperature)


def build_answerability_gate(
    settings: Settings, transport: ChatCompletionTransport | None = None
) -> AnswerabilityGate:
    if settings.app_mode != "live":
        return FixtureAnswerabilityGate()
    model = (
        settings.openrouter_model
        if settings.llm_provider == "openrouter"
        else settings.deepseek_model
    )
    fallback = settings.openrouter_fallback_model if settings.llm_provider == "openrouter" else None
    if transport is not None:
        return DeepSeekAnswerabilityGate(
            transport, base_url_or_model=model, fallback_model=fallback
        )

    # Never construct an independent client or lose the composition root's privacy options.
    return UnavailableAnswerabilityGate()


def build_semantic_verifier(
    settings: Settings, transport: ChatCompletionTransport | None = None
) -> SemanticVerifier:
    if settings.app_mode != "live":
        return FixtureSemanticVerifier()
    model = (
        settings.openrouter_model
        if settings.llm_provider == "openrouter"
        else settings.deepseek_model
    )
    fallback = settings.openrouter_fallback_model if settings.llm_provider == "openrouter" else None
    if transport is not None:
        return DeepSeekSemanticVerifier(transport, base_url_or_model=model, fallback_model=fallback)

    return UnavailableSemanticVerifier()
