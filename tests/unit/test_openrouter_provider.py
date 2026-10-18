"""No live credentials: exercise actual adapters and pooled transport with MockTransport."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from apps.api.app.config import Settings
from apps.api.app.services.llm_factory import build_llm_provider
from apps.api.app.services.metrics import MetricsRegistry
from packages.contracts.assistant import GeneratedAnswer
from packages.contracts.common import Language
from services.assistant.answer_generator import (
    DeepSeekLLMProvider,
    FixtureLLMProvider,
    UnavailableLLMProvider,
)
from services.assistant.chat_transport import ChatCompletionTransport
from services.assistant.llm_errors import (
    LLMAvailabilityError,
    LLMRejectedError,
    LLMResponseError,
)
from services.assistant.openrouter import OpenRouterLLMProvider

PRIMARY = "deepseek/deepseek-v4.1-flash-1017"
FALLBACK = "deepseek/deepseek-v4-flash"
ABSTAIN = {"answerable": False, "answer": "", "citations": []}


def completion(content=ABSTAIN, **overrides):
    message = {"content": json.dumps(content) if not isinstance(content, str) else content}
    return {"choices": [{"message": message, "finish_reason": "stop", **overrides}]}


def settings(**overrides):
    return Settings(
        _env_file=None,
        **{
            "app_mode": "fixture",
            "llm_provider": "openrouter",
            "openrouter_api_key": "test-only-not-a-real-key",
            **overrides,
        },
    )


@pytest.fixture(autouse=True)
def no_real_backoff(monkeypatch):
    waits = []

    async def sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr("services.assistant.chat_transport.asyncio.sleep", sleep)
    return waits


async def test_structured_schema_privacy_stable_prefix_and_safe_usage():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                **completion(),
                "usage": {
                    "prompt_tokens": 300,
                    "completion_tokens": 20,
                    "prompt_tokens_details": {"cached_tokens": 100, "cache_write_tokens": 0},
                    "cost": 0.000123,
                },
            },
        )

    metrics = MetricsRegistry()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = build_llm_provider(settings(), client, metrics)
        assert isinstance(provider, OpenRouterLLMProvider)
        assert provider.transport.client is client
        for question in ("secret employee question", "second employee question"):
            result = await provider.generate(question, [], Language.ENGLISH)
            assert result == GeneratedAnswer(**ABSTAIN)
        assert not client.is_closed
    assert client.is_closed
    first, second = [json.loads(request.content) for request in requests]
    assert str(requests[0].url) == "https://openrouter.ai/api/v1/chat/completions"
    assert requests[0].headers["authorization"] == "Bearer test-only-not-a-real-key"
    assert first["model"] == PRIMARY
    assert first["stream"] is False
    assert "thinking" not in first and "models" not in first and "route" not in first
    assert first["reasoning"] == {"enabled": False, "exclude": True}
    assert first["provider"] == {
        "data_collection": "deny",
        "zdr": True,
        "require_parameters": True,
        "allow_fallbacks": False,
    }
    assert first["messages"][0] == second["messages"][0]
    schema = first["response_format"]["json_schema"]
    assert schema["strict"] is True
    assert set(schema["schema"]["required"]) == {"answerable", "answer", "citations"}
    locator = schema["schema"]["$defs"]["SourceLocator"]
    assert set(locator["required"]) == set(locator["properties"])
    assert locator["additionalProperties"] is False
    snapshot = metrics.snapshot()
    prefix = "llm_openrouter.deepseek_deepseek-v4.1-flash-1017"
    assert snapshot[prefix + ".request"]["count"] == 2
    assert snapshot[prefix + ".request"]["failures"] == 0
    assert snapshot[prefix + ".input_tokens"]["total"] == 600
    assert snapshot[prefix + ".output_tokens"]["total"] == 40
    assert snapshot[prefix + ".cached_tokens"]["total"] == 200
    assert snapshot[prefix + ".reported_cost_usd"]["total"] == pytest.approx(0.000246)
    assert "secret employee" not in str(snapshot)
    assert "test-only-not-a-real-key" not in str(snapshot)


@pytest.mark.parametrize(
    "bad",
    [
        "not JSON",
        "{}",
        {"answerable": "false", "answer": "", "citations": []},
        {**ABSTAIN, "extra": "forbidden"},
        {**ABSTAIN, "answer": 42},
        {**ABSTAIN, "citations": [{"chunk_id": "invented"}]},
    ],
)
async def test_schema_failure_does_not_retry_or_fallback(bad):
    calls = []

    def handle(request):
        calls.append(json.loads(request.content)["model"])
        return httpx.Response(200, json=completion(bad))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = build_llm_provider(settings(), client, MetricsRegistry())
        with pytest.raises(LLMResponseError):
            await provider.generate("question", [], Language.ENGLISH)
    assert calls == [PRIMARY]


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
async def test_availability_failure_selects_only_the_approved_fallback(status):
    models = []

    def handle(request):
        models.append(json.loads(request.content)["model"])
        if len(models) == 1:
            return httpx.Response(
                status,
                json={"error": {"code": status, "message": "private upstream error"}},
                headers={"retry-after": "0"},
            )
        return httpx.Response(200, json=completion())

    metrics = MetricsRegistry()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = build_llm_provider(settings(), client, metrics)
        await provider.generate("question", [], Language.ENGLISH)
    assert models == [PRIMARY, FALLBACK]
    assert metrics.snapshot()["llm_openrouter.fallbacks"]["total"] == 1


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectError,
        httpx.ReadError,
        httpx.RemoteProtocolError,
        httpx.ReadTimeout,
        httpx.ConnectTimeout,
        httpx.PoolTimeout,
    ],
)
async def test_network_errors_and_timeouts_have_a_two_attempt_limit(failure):
    models = []

    def handle(request):
        models.append(json.loads(request.content)["model"])
        raise failure("private network detail", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = build_llm_provider(settings(), client, MetricsRegistry())
        with pytest.raises(LLMAvailabilityError) as caught:
            await provider.generate("question", [], Language.ENGLISH)
    assert models == [PRIMARY, FALLBACK]
    assert "private" not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 408, 422])
async def test_nonavailability_http_errors_never_fallback(status):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(
            status, json={"error": {"code": status, "message": "private body key=secret"}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = build_llm_provider(settings(), client, MetricsRegistry())
        with pytest.raises(LLMRejectedError) as caught:
            await provider.generate("question", [], Language.ENGLISH)
    assert len(calls) == 1
    assert "private" not in str(caught.value)


@pytest.mark.parametrize(
    "body",
    [
        {"error": {"code": 403, "message": "moderation"}},
        {
            "choices": [
                {"message": {"content": "", "refusal": "moderation"}, "finish_reason": "stop"}
            ]
        },
        {"choices": [{"message": {"content": "refusal"}, "finish_reason": "content_filter"}]},
    ],
)
async def test_moderation_refusal_never_falls_back(body):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = build_llm_provider(settings(), client, MetricsRegistry())
        with pytest.raises(LLMRejectedError):
            await provider.generate("question", [], Language.ENGLISH)
    assert len(calls) == 1


async def test_long_retry_after_is_not_clamped_to_retry_early(no_real_backoff):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"code": 429}}, headers={"retry-after": "60"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(LLMAvailabilityError):
            await build_llm_provider(settings(), client, MetricsRegistry()).generate(
                "question", [], Language.ENGLISH
            )
    assert len(calls) == 1 and not no_real_backoff


def test_retry_after_http_date_and_invalid_values():
    date = format_datetime(datetime.now(UTC) + timedelta(seconds=60))
    assert (
        ChatCompletionTransport._retry_after(httpx.Response(429, headers={"retry-after": date}))
        > 55
    )
    for value in ("bad", "inf", "nan"):
        assert (
            ChatCompletionTransport._retry_after(
                httpx.Response(429, headers={"retry-after": value})
            )
            is None
        )


async def test_total_deadline_bounds_the_entire_operation(monkeypatch):
    entered = []

    async def handle(request):
        entered.append(request)
        await asyncio.Event().wait()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = build_llm_provider(
            settings(llm_request_timeout_seconds=0.01), client, MetricsRegistry()
        )
        with pytest.raises(LLMAvailabilityError, match="deadline_exceeded"):
            await provider.generate("question", [], Language.ENGLISH)
    assert len(entered) == 1


async def test_future_structured_component_reuses_transport_and_pool():
    class FutureResult(BaseModel):
        model_config = ConfigDict(extra="forbid")
        supported: bool

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=completion({"supported": True}))
        )
    ) as client:
        provider = build_llm_provider(
            settings(openrouter_allowed_providers=("approved",)), client, MetricsRegistry()
        )
        result = await provider.transport.complete(
            messages=[{"role": "user", "content": "synthetic"}],
            response_model=FutureResult,
            model=PRIMARY,
        )
        assert result.supported
        assert provider.transport.options["provider"]["only"] == ["approved"]


def test_live_configuration_requires_selected_key_and_prohibits_fixture(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    common = dict(
        app_mode="live",
        web_origin="https://example.test",
        firebase_project_id="test",
        firebase_service_account_json="{}",
        s3_access_key_id="test",
        s3_secret_access_key="test",
        embedding_provider="pinecone_e5",
    )
    for provider in ("openrouter", "deepseek"):
        with pytest.raises(ValidationError, match=provider.upper() + "_API_KEY"):
            Settings(
                _env_file=None,
                **common,
                llm_provider=provider,
                openrouter_api_key=None,
                deepseek_api_key=None,
            )
    with pytest.raises(ValidationError, match="Fixture LLM"):
        Settings(_env_file=None, **common, llm_provider="fixture")
    assert (
        Settings(
            _env_file=None, **common, llm_provider="openrouter", openrouter_api_key="test"
        ).llm_provider
        == "openrouter"
    )
    assert (
        Settings(
            _env_file=None, **common, llm_provider="deepseek", deepseek_api_key="test"
        ).llm_provider
        == "deepseek"
    )


async def test_missing_key_is_unavailable_in_fixture_mode_and_never_silently_fixture():
    async with httpx.AsyncClient() as client:
        assert isinstance(
            build_llm_provider(settings(openrouter_api_key=""), client, MetricsRegistry()),
            UnavailableLLMProvider,
        )
        assert isinstance(
            build_llm_provider(settings(llm_provider="fixture"), client, MetricsRegistry()),
            FixtureLLMProvider,
        )
        with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
            ChatCompletionTransport(
                client,
                provider_id="openrouter",
                api_key=" ",
                base_url="https://openrouter.ai/api/v1",
                metrics=MetricsRegistry(),
            )


@pytest.mark.parametrize(
    "url",
    [
        "http://example.test",
        "https://user:pass@example.test",
        "https://example.test?key=secret",
        "https://example.test#frag",
    ],
)
async def test_invalid_base_urls_fail_before_sending_credentials(url):
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError, match="HTTPS"):
            build_llm_provider(settings(openrouter_base_url=url), client, MetricsRegistry())


async def test_direct_deepseek_rollback_uses_same_model_retry_only():
    models = []

    def handle(request):
        payload = json.loads(request.content)
        models.append(payload["model"])
        assert "provider" not in payload and "reasoning" not in payload
        assert payload["thinking"] == {"type": "disabled"}
        return httpx.Response(503) if len(models) == 1 else httpx.Response(200, json=completion())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = build_llm_provider(
            settings(llm_provider="deepseek", deepseek_api_key="test"), client, MetricsRegistry()
        )
        assert isinstance(provider, DeepSeekLLMProvider)
        await provider.generate("question", [], Language.ENGLISH)
    assert models == ["deepseek-flash", "deepseek-flash"]


@pytest.mark.parametrize(
    "status,body",
    [
        (503, {"error": {"code": 403, "message": "moderation"}}),
        (503, {"choices": [{"message": {"refusal": "moderation"}}]}),
        (403, {"error": {"code": 503}}),
    ],
)
async def test_refusals_take_precedence_over_ambiguous_availability_status(status, body):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(status, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(LLMRejectedError):
            await build_llm_provider(settings(), client, MetricsRegistry()).generate(
                "question", [], Language.ENGLISH
            )
    assert len(calls) == 1


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {},
        {"prompt_tokens": "300", "completion_tokens": True, "cost": "0.1"},
        {"cost": float("inf")},
    ],
)
async def test_missing_or_invalid_usage_never_invents_tokens_or_cost(usage):
    metrics = MetricsRegistry()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={**completion(), "usage": usage})
        )
    ) as client:
        # Infinity is invalid JSON: use no cost rather than serializing it in the mock response.
        if isinstance(usage, dict) and usage.get("cost") == float("inf"):
            provider = build_llm_provider(settings(), client, metrics)
            provider.transport._usage("test", usage)
        else:
            await build_llm_provider(settings(), client, metrics).generate(
                "question", [], Language.ENGLISH
            )
    assert not any("tokens" in name or "cost" in name for name in metrics.snapshot())
