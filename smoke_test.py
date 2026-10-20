import asyncio
import sys

from fastapi.testclient import TestClient

from apps.api.app.config import get_settings
from apps.api.app.main import app
from apps.api.app.models.organization import ApplicationRole, EmployeeProfile
from packages.contracts.assistant import (
    Language,
    MessageRole,
    ResponseKind,
    VerifiedAnswer,
)
from services.assistant.conversation import ConversationTurn

DEFAULT_SMOKE_PROFILE = EmployeeProfile(
    id="smoke-user",
    organization_id="ajt",
    identity_subject="fixture|smoke-test-user",
    display_name="Smoke Test User",
    email="smoke@example.test",
    application_roles=frozenset({ApplicationRole.EMPLOYEE, ApplicationRole.SOP_ADMIN}),
    departments=frozenset({"store", "operations"}),
)

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_SKIPPED = 2


async def smoke_test(service=None, settings=None, profile=None) -> int:
    try:
        if settings is None:
            settings = get_settings()

        app_mode = getattr(settings, "app_mode", None)
        llm_provider = getattr(settings, "llm_provider", None)

        if llm_provider == "openrouter":
            has_key = bool(
                getattr(settings, "openrouter_api_key", None)
                and (
                    settings.openrouter_api_key.get_secret_value()
                    if hasattr(settings.openrouter_api_key, "get_secret_value")
                    else settings.openrouter_api_key
                )
            )
            key_name = "OPENROUTER_API_KEY"
        else:
            has_key = bool(
                getattr(settings, "deepseek_api_key", None)
                and (
                    settings.deepseek_api_key.get_secret_value()
                    if hasattr(settings.deepseek_api_key, "get_secret_value")
                    else settings.deepseek_api_key
                )
            )
            key_name = "DEEPSEEK_API_KEY"

        print(f"Active app_mode: {app_mode}")
        print(f"Active llm_provider: {llm_provider}")

        # Check for live prerequisites
        if app_mode != "live" or not has_key:
            print("\n[SMOKE TEST] SKIPPED (live smoke test not run)")
            print(f"Reason: Requires app_mode='live' and a configured {key_name}.")
            return EXIT_SKIPPED

        if profile is None:
            profile = DEFAULT_SMOKE_PROFILE

        def validate_answer(resp: object, step_name: str) -> bool:
            if not isinstance(resp, VerifiedAnswer):
                print(f"FAILED [{step_name}]: Expected VerifiedAnswer, got {type(resp).__name__}")
                return False
            if not resp.verified:
                print(f"FAILED [{step_name}]: Response verified flag is False")
                return False
            if not resp.answerable:
                print(f"FAILED [{step_name}]: Response answerable flag is False")
                return False
            if resp.kind is not ResponseKind.POLICY_ANSWER:
                print(f"FAILED [{step_name}]: Response kind is {resp.kind}, expected POLICY_ANSWER")
                return False
            if not resp.answer or not resp.answer.strip():
                print(f"FAILED [{step_name}]: Answer text is empty")
                return False
            # A 'no guidance found' answer must NOT count as a passing live check
            lower_ans = resp.answer.casefold()
            if (
                "couldn't find enough guidance" in lower_ans
                or "could not find enough guidance" in lower_ans
            ):
                print(f"FAILED [{step_name}]: Answer returned 'no guidance found' canned response")
                return False
            if not resp.citations:
                print(f"FAILED [{step_name}]: Expected at least one citation, got empty citations")
                return False
            return True

        async def execute_steps(srv) -> int:
            print("Running end-to-end API smoke test against real OpenRouter DeepSeek...")

            # 1. Standalone Question
            standalone_q = "What is the capacity of the yarn godown?"
            try:
                resp1, _ = await srv.answer_with_context(
                    profile, standalone_q, Language.ENGLISH, [], None
                )
                print("\n[Standalone Question]")
                print(f"Verified: {resp1.verified}")
                print(f"Answerable: {resp1.answerable}")
                print(f"Kind: {resp1.kind.value if hasattr(resp1.kind, 'value') else resp1.kind}")
                print(
                    f"Citations count: {len(resp1.citations) if hasattr(resp1, 'citations') else 0}"
                )
                if not validate_answer(resp1, "Standalone Question"):
                    return EXIT_FAILURE
            except Exception as e:
                print(
                    f"\nFAILED [Standalone Question]: Service raised {type(e).__name__}"
                )
                return EXIT_FAILURE

            # 2. Follow-up Question
            history = [
                ConversationTurn(role=MessageRole.USER, content=standalone_q),
                ConversationTurn(role=MessageRole.ASSISTANT, content=resp1.answer),
            ]
            followup_q = "Who approves it?"
            try:
                resp2, _ = await srv.answer_with_context(
                    profile, followup_q, Language.ENGLISH, history, None
                )
                print("\n[Follow-up Question]")
                print(f"Verified: {resp2.verified}")
                print(f"Answerable: {resp2.answerable}")
                print(f"Kind: {resp2.kind.value if hasattr(resp2.kind, 'value') else resp2.kind}")
                print(
                    f"Citations count: {len(resp2.citations) if hasattr(resp2, 'citations') else 0}"
                )
                if not validate_answer(resp2, "Follow-up Question"):
                    return EXIT_FAILURE
            except Exception as e:
                print(
                    f"\nFAILED [Follow-up Question]: Service raised {type(e).__name__}"
                )
                return EXIT_FAILURE

            print("\nSmoke test completed successfully!")
            return EXIT_SUCCESS

        if service is not None:
            return await execute_steps(service)

        with TestClient(app):
            service = app.state.assistant_service
            return await execute_steps(service)
    except Exception as e:
        print(f"\nFAILED [Setup]: Service raised {type(e).__name__}")
        return EXIT_FAILURE


def main() -> None:
    try:
        sys.exit(asyncio.run(smoke_test()))
    except SystemExit:
        raise
    except Exception as e:
        print(f"\nFAILED [Setup]: Service raised {type(e).__name__}")
        sys.exit(EXIT_FAILURE)


if __name__ == "__main__":
    main()
