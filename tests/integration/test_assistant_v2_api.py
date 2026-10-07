import json

from fastapi.testclient import TestClient

from apps.api.app.main import app
from packages.contracts.assistant import GeneratedAnswer
from services.assistant.answer_generator import FixtureLLMProvider
from services.assistant.grounding import FixtureSemanticVerifier

HEADERS = {"Authorization": "Fixture employee"}


def events(text: str) -> list[tuple[str, dict]]:
    output = []
    for block in text.strip().split("\n\n"):
        lines = block.splitlines()
        if len(lines) >= 2:
            output.append(
                (lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: ")))
            )
    return output


def test_stream_releases_only_verified_answer_and_truthful_stages():
    with TestClient(app) as client:
        client.app.state.assistant_service.provider = FixtureLLMProvider()
        client.app.state.assistant_service.grounding.semantic_verifier = FixtureSemanticVerifier()
        assert (
            client.post(
                "/api/v1/assistant/answer/events",
                json={
                    "question": "Hi",
                    "language": "english",
                },
            ).status_code
            == 401
        )
        response = client.post(
            "/api/v1/assistant/answer/events",
            headers=HEADERS,
            json={
                "question": "How is damaged stock handled?",
                "language": "english",
            },
        )
        assert response.status_code == 200
        stream = events(response.text)
        names = [name for name, _ in stream]
        assert names[:4] == ["status", "status", "status", "status"]
        assert [data["stage"] for name, data in stream if name == "status"] == [
            "retrieving",
            "reading",
            "generating",
            "verifying",
        ]
        assert (
            names.index("answer_start")
            < names.index("answer_delta")
            < names.index("sources")
            < names.index("done")
        )
        assert next(data for name, data in stream if name == "answer_start")["verified"]
        assert next(data for name, data in stream if name == "sources")["citations"]


def test_invalid_generation_is_never_streamed_and_only_retried_once():
    class InvalidProvider(FixtureLLMProvider):
        calls = 0

        async def generate(
            self, question, evidence, language, repair_feedback=None, answer_mode=None
        ):
            self.calls += 1
            return GeneratedAnswer(answerable=True, answer="Invented 999 days", citations=[])

        async def plan_query(self, question, history):
            from services.assistant.conversation import build_query_plan

            return build_query_plan(question, history)

    with TestClient(app) as client:
        provider = InvalidProvider()
        client.app.state.assistant_service.provider = provider
        client.app.state.assistant_service.grounding.semantic_verifier = FixtureSemanticVerifier()
        response = client.post(
            "/api/v1/assistant/answer/events",
            headers=HEADERS,
            json={
                "question": "How is damaged stock handled?",
                "language": "english",
            },
        )
        stream = events(response.text)
        assert provider.calls == 2
        assert stream[-1][0] == "error"
        assert not any(
            name in {"answer_start", "answer_delta", "sources", "done"} for name, _ in stream
        )
        assert "999" not in response.text


def test_twenty_turns_create_no_chat_records_or_mutations():
    with TestClient(app) as client:
        client.app.state.assistant_service.provider = FixtureLLMProvider()
        client.app.state.assistant_service.grounding.semantic_verifier = FixtureSemanticVerifier()
        store = client.app.state.foundation_store
        before_sessions = len(client.app.state.database.collections.get("chat_sessions", []))
        before_messages = len(client.app.state.database.collections.get("chat_messages", []))
        history: list[dict[str, str]] = []
        for index in range(20):
            question = (
                "How is damaged stock handled?" if index == 0 else "What about the damaged item?"
            )
            response = client.post(
                "/api/v1/assistant/answer",
                headers=HEADERS,
                json={
                    "question": question,
                    "language": "english",
                    "history": history[-16:],
                },
            )
            assert response.status_code == 200, response.text
            answer = response.json()
            assert answer["verified"]
            history.extend(
                [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": answer["answer"][:3000]},
                ]
            )
        assert len(store.chat_sessions) == len(store.chat_messages) == 0
        assert (
            len(client.app.state.database.collections.get("chat_sessions", [])) == before_sessions
        )
        assert (
            len(client.app.state.database.collections.get("chat_messages", [])) == before_messages
        )
        assert not {"chat_sessions", "chat_messages"} & set(store.get_mutations())


def test_no_answer_is_neutral_verified_response():
    class AbstainProvider(FixtureLLMProvider):
        async def generate(
            self, question, evidence, language, repair_feedback=None, answer_mode=None
        ):
            return GeneratedAnswer(answerable=False, answer="", citations=[])

        async def plan_query(self, question, history):
            from services.assistant.conversation import build_query_plan

            return build_query_plan(question, history)

    with TestClient(app) as client:
        client.app.state.assistant_service.provider = AbstainProvider()
        client.app.state.assistant_service.grounding.semantic_verifier = FixtureSemanticVerifier()
        response = client.post(
            "/api/v1/assistant/answer/events",
            headers=HEADERS,
            json={
                "question": "How is damaged stock handled?",
                "language": "roman_urdu",
            },
        )
        stream = events(response.text)
        assert next(data for name, data in stream if name == "answer_start")["kind"] == "no_answer"
        assert next(data for name, data in stream if name == "sources")["citations"] == []
        assert stream[-1][0] == "done"
