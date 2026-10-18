"""Exercise HTTP lifecycle and existing release gates with mocked OpenRouter only."""

import json
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import apps.api.app.main as application
from apps.api.app.config import Settings
from apps.api.app.services.llm_factory import build_llm_provider

PRIMARY = "deepseek/deepseek-v4.1-flash-1017"
FALLBACK = "deepseek/deepseek-v4-flash"


@pytest.mark.parametrize(
    "mode", ["valid", "citations", "grounding", "malformed", "refusal", "availability"]
)
def test_openrouter_preserves_authorized_verified_only_release(monkeypatch, mode):
    config = Settings(_env_file=None, app_mode="fixture", llm_provider="fixture")
    monkeypatch.setattr(application, "get_settings", lambda: config)
    models = []
    captured_options = {}

    def respond(request):
        payload = json.loads(request.content)
        models.append(payload["model"])
        if mode == "availability" and len(models) == 1:
            return httpx.Response(503, headers={"retry-after": "0"})
        if mode == "refusal":
            return httpx.Response(403, json={"error": {"code": 403}})
        data = json.loads(payload["messages"][1]["content"])
        evidence = data["authorized_evidence"][0]
        citation = {
            key: evidence[key]
            for key in (
                "chunk_id",
                "policy_id",
                "policy_title",
                "section_id",
                "heading_path",
                "document_id",
                "source",
            )
        }
        if mode == "citations":
            citation["chunk_id"] = "invented-citation"
        answer = evidence["text"] if mode != "grounding" else "Invented entitlement: 999 days."
        content = json.dumps({"answerable": True, "answer": answer, "citations": [citation]})
        if mode == "malformed":
            content = "private malformed model output"
        return httpx.Response(
            200, json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}
        )

    real_client = httpx.AsyncClient
    shared = real_client(transport=httpx.MockTransport(respond))

    def pooled_client(**kwargs):
        captured_options.update(kwargs)
        return shared

    monkeypatch.setattr(application.httpx, "AsyncClient", pooled_client)
    with TestClient(application.app) as client:
        assert client.app.state.llm_http_client is shared
        assert not shared.is_closed
        provider_settings = Settings(
            _env_file=None,
            app_mode="fixture",
            llm_provider="openrouter",
            openrouter_api_key="test-only",
        )
        client.app.state.assistant_service.provider = build_llm_provider(
            provider_settings, shared, client.app.state.metrics
        )
        response = client.post(
            "/api/v1/assistant/answer/events",
            headers={"Authorization": "Fixture employee"},
            json={"question": "How is damaged stock handled?", "language": "english"},
        )
        if mode in {"valid", "availability"}:
            assert "event: answer_start" in response.text
            assert "event: answer_delta" in response.text
            assert "event: done" in response.text
            assert response.text.index('"stage": "verifying"') < response.text.index(
                "event: answer_start"
            )
            assert models == ([PRIMARY, FALLBACK] if mode == "availability" else [PRIMARY])
        else:
            assert "event: error" in response.text
            assert "event: answer_start" not in response.text
            assert "event: answer_delta" not in response.text
            assert "private malformed" not in response.text and "999" not in response.text
            # Existing one-repair ceiling, on the same primary; no model fallback.
            assert models == [PRIMARY] * (1 if mode == "refusal" else 2)
        assert (
            client.get(
                "/api/v1/admin/operations/metrics", headers={"Authorization": "Fixture employee"}
            ).status_code
            == 403
        )
        # Search and canonical reading remain independently available after model failure.
        headers = {"Authorization": "Fixture employee"}
        available = client.get("/api/v1/policies", headers=headers)
        assert available.status_code == 200 and available.json()
        assert (
            client.get(
                "/api/v1/policies/" + available.json()[0]["policy_id"], headers=headers
            ).status_code
            == 200
        )
        search = client.post(
            "/api/v1/search",
            headers=headers,
            json={"query": "damaged stock", "language": "english"},
        )
        assert search.status_code == 200 and search.json()["results"]
    assert shared.is_closed
    assert captured_options["follow_redirects"] is False
    assert captured_options["trust_env"] is False
    assert captured_options["timeout"].connect == 5
    assert captured_options["limits"].max_connections == 20


def test_pool_closes_when_application_startup_fails(monkeypatch):
    config = Settings(_env_file=None, app_mode="fixture", llm_provider="fixture")
    monkeypatch.setattr(application, "get_settings", lambda: config)
    real_client = httpx.AsyncClient
    shared = real_client(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    monkeypatch.setattr(application.httpx, "AsyncClient", lambda **kwargs: shared)

    @asynccontextmanager
    async def failed_startup(app):
        raise RuntimeError("synthetic startup failure")
        yield  # pragma: no cover

    monkeypatch.setattr(application, "application_lifespan", failed_startup)
    with pytest.raises(RuntimeError, match="synthetic startup failure"):
        with TestClient(FastAPI(lifespan=application.lifespan)):
            pass
    assert shared.is_closed
