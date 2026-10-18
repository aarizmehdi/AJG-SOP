import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import smoke_test
from packages.contracts.assistant import (
    AssistantCitation,
    Language,
    ResponseKind,
    VerifiedAnswer,
)
from packages.contracts.canonical import SourceLocator


def make_dummy_citation() -> AssistantCitation:
    return AssistantCitation(
        chunk_id="chunk-1",
        policy_id="policy-1",
        policy_title="Store Operations",
        section_id="sec-1",
        heading_path=("Store Operations", "Section 1"),
        document_id="doc-1",
        source=SourceLocator(source_document_id="doc-1", page_start=1, page_end=1),
    )


def make_valid_answer(text: str = "Capacity is 12 tonnes.") -> VerifiedAnswer:
    return VerifiedAnswer(
        organization_id="ajt",
        kind=ResponseKind.POLICY_ANSWER,
        answerable=True,
        answer=text,
        language=Language.ENGLISH,
        citations=[make_dummy_citation()],
        verified=True,
    )


def make_no_guidance_answer() -> VerifiedAnswer:
    return VerifiedAnswer(
        organization_id="ajt",
        kind=ResponseKind.NO_ANSWER,
        answerable=False,
        answer=(
            "I couldn't find enough guidance for that "
            "in the SOPs available to you."
        ),
        language=Language.ENGLISH,
        citations=[],
        verified=True,
    )


def make_unverified_answer() -> VerifiedAnswer:
    return VerifiedAnswer(
        organization_id="ajt",
        kind=ResponseKind.POLICY_ANSWER,
        answerable=True,
        answer="Unverified answer.",
        language=Language.ENGLISH,
        citations=[make_dummy_citation()],
        verified=False,
    )


def live_settings():
    return SimpleNamespace(
        app_mode="live",
        llm_provider="deepseek",
        deepseek_api_key=SimpleNamespace(
            get_secret_value=lambda: "FAKE-KEY-FOR-TEST-123"
        ),
    )


# ---------------------------------------------------------------------------
# Tests 1–6: coroutine-level (return value + stdout)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_1_first_request_succeeds(capsys):
    """Both requests succeed: returns 0 and prints success."""
    service = SimpleNamespace(
        answer_with_context=AsyncMock(
            side_effect=[
                (make_valid_answer("Standalone answer"), []),
                (make_valid_answer("Follow-up answer"), []),
            ]
        )
    )
    code = await smoke_test.smoke_test(
        service=service, settings=live_settings()
    )
    captured = capsys.readouterr().out
    assert code == 0
    assert "Smoke test completed successfully!" in captured


@pytest.mark.asyncio
async def test_2_first_request_fails(capsys):
    """First request fails: returns 1 and no success message."""
    service = SimpleNamespace(
        answer_with_context=AsyncMock(
            return_value=(make_no_guidance_answer(), [])
        )
    )
    code = await smoke_test.smoke_test(
        service=service, settings=live_settings()
    )
    captured = capsys.readouterr().out
    assert code == 1
    assert "Smoke test completed successfully!" not in captured


@pytest.mark.asyncio
async def test_3_followup_succeeds(capsys):
    """Follow-up succeeds: both requests pass, exit code 0."""
    service = SimpleNamespace(
        answer_with_context=AsyncMock(
            side_effect=[
                (make_valid_answer("First answer"), []),
                (make_valid_answer("Second answer"), []),
            ]
        )
    )
    code = await smoke_test.smoke_test(
        service=service, settings=live_settings()
    )
    captured = capsys.readouterr().out
    assert code == 0
    assert service.answer_with_context.await_count == 2
    assert "Smoke test completed successfully!" in captured


@pytest.mark.asyncio
async def test_4_followup_fails(capsys):
    """First passes but follow-up fails: returns 1, no success."""
    service = SimpleNamespace(
        answer_with_context=AsyncMock(
            side_effect=[
                (make_valid_answer("First answer"), []),
                (make_no_guidance_answer(), []),
            ]
        )
    )
    code = await smoke_test.smoke_test(
        service=service, settings=live_settings()
    )
    captured = capsys.readouterr().out
    assert code == 1
    assert "Smoke test completed successfully!" not in captured


@pytest.mark.asyncio
async def test_5_response_is_unverified(capsys):
    """Response verified=False: must fail with exit code 1."""
    service = SimpleNamespace(
        answer_with_context=AsyncMock(
            return_value=(make_unverified_answer(), [])
        )
    )
    code = await smoke_test.smoke_test(
        service=service, settings=live_settings()
    )
    captured = capsys.readouterr().out
    assert code == 1
    assert "Smoke test completed successfully!" not in captured


@pytest.mark.asyncio
async def test_6_service_raises_exception(capsys):
    """Service raises exception: must fail with exit code 1."""
    service = SimpleNamespace(
        answer_with_context=AsyncMock(
            side_effect=RuntimeError("Provider connection error")
        )
    )
    code = await smoke_test.smoke_test(
        service=service, settings=live_settings()
    )
    captured = capsys.readouterr().out
    assert code == 1
    assert "Smoke test completed successfully!" not in captured


# ---------------------------------------------------------------------------
# Test 7: REAL process exit code via sys.exit → SystemExit
# Tests main() which calls sys.exit(asyncio.run(smoke_test()))
# ---------------------------------------------------------------------------


def _run_main_expecting_exit(mock_service, settings, capsys):
    """Call smoke_test.main() with injected service/settings.

    We patch ``asyncio.run`` so that when ``main()`` calls
    ``asyncio.run(smoke_test())``, we intercept the coroutine,
    close it (to avoid "was never awaited" warnings), and run
    our own coroutine with the injected service and settings
    instead. ``main()`` then calls ``sys.exit()`` with the
    returned exit code, which we catch via ``SystemExit``.
    """
    import asyncio as _asyncio

    _real_run = _asyncio.run

    def fake_run(coro, **kw):
        # Close the original coroutine to prevent ResourceWarning
        coro.close()
        return _real_run(
            smoke_test.smoke_test(
                service=mock_service, settings=settings
            )
        )

    with patch("asyncio.run", side_effect=fake_run):
        with pytest.raises(SystemExit) as exc_info:
            smoke_test.main()
    captured = capsys.readouterr().out
    return exc_info.value.code, captured


def test_7a_process_exit_first_request_fails(capsys):
    """7a. First request fails → real sys.exit(1)."""
    svc = SimpleNamespace(
        answer_with_context=AsyncMock(
            return_value=(make_no_guidance_answer(), [])
        )
    )
    code, out = _run_main_expecting_exit(svc, live_settings(), capsys)
    assert code != 0
    assert "Smoke test completed successfully!" not in out


def test_7b_process_exit_followup_fails(capsys):
    """7b. Follow-up fails → real sys.exit(1)."""
    svc = SimpleNamespace(
        answer_with_context=AsyncMock(
            side_effect=[
                (make_valid_answer("OK"), []),
                (make_no_guidance_answer(), []),
            ]
        )
    )
    code, out = _run_main_expecting_exit(svc, live_settings(), capsys)
    assert code != 0
    assert "Smoke test completed successfully!" not in out


def test_7c_process_exit_unverified(capsys):
    """7c. Unverified response → real sys.exit(1)."""
    svc = SimpleNamespace(
        answer_with_context=AsyncMock(
            return_value=(make_unverified_answer(), [])
        )
    )
    code, out = _run_main_expecting_exit(svc, live_settings(), capsys)
    assert code != 0
    assert "Smoke test completed successfully!" not in out


def test_7d_process_exit_exception(capsys):
    """7d. Service exception → real sys.exit(1)."""
    svc = SimpleNamespace(
        answer_with_context=AsyncMock(
            side_effect=RuntimeError("Connection refused")
        )
    )
    code, out = _run_main_expecting_exit(svc, live_settings(), capsys)
    assert code != 0
    assert "Smoke test completed successfully!" not in out


def test_7e_process_exit_no_guidance(capsys):
    """7e. 'No guidance found' canned answer → real sys.exit(1)."""
    no_guidance = VerifiedAnswer(
        organization_id="ajt",
        kind=ResponseKind.POLICY_ANSWER,
        answerable=True,
        answer=(
            "I couldn't find enough guidance for that "
            "in the SOPs available to you."
        ),
        language=Language.ENGLISH,
        citations=[make_dummy_citation()],
        verified=True,
    )
    svc = SimpleNamespace(
        answer_with_context=AsyncMock(
            return_value=(no_guidance, [])
        )
    )
    code, out = _run_main_expecting_exit(svc, live_settings(), capsys)
    assert code != 0
    assert "Smoke test completed successfully!" not in out


def test_7f_process_exit_setup_crash(capsys):
    """7f. Setup crash (service construction / settings crash) → sys.exit(1)."""
    with patch(
        "smoke_test.TestClient",
        side_effect=RuntimeError("TestClient construction failed"),
    ):
        code, out = _run_main_expecting_exit(None, live_settings(), capsys)
    assert code != 0
    assert code == 1
    assert "FAILED [Setup]: Service raised RuntimeError" in out
    assert "Smoke test completed successfully!" not in out


def test_skipped_exit_code_2(capsys):
    """Skipped path (fixture mode / missing key) → sys.exit(2)."""
    bad_settings = SimpleNamespace(
        app_mode="fixture",
        llm_provider="deepseek",
        deepseek_api_key=None,
    )
    code, out = _run_main_expecting_exit(None, bad_settings, capsys)
    assert code != 0
    assert code == 2
    assert "SKIPPED (live smoke test not run)" in out
    assert "Smoke test completed successfully!" not in out


# ---------------------------------------------------------------------------
# Test 8: Success message control
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_8_success_printed_only_when_all_checks_pass(capsys):
    """Success message printed ONLY when all checks pass."""
    # Failure path
    service_fail = SimpleNamespace(
        answer_with_context=AsyncMock(
            return_value=(make_no_guidance_answer(), [])
        )
    )
    await smoke_test.smoke_test(
        service=service_fail, settings=live_settings()
    )
    out_fail = capsys.readouterr().out
    assert "Smoke test completed successfully!" not in out_fail

    # Success path
    service_pass = SimpleNamespace(
        answer_with_context=AsyncMock(
            side_effect=[
                (make_valid_answer("Answer 1"), []),
                (make_valid_answer("Answer 2"), []),
            ]
        )
    )
    await smoke_test.smoke_test(
        service=service_pass, settings=live_settings()
    )
    out_pass = capsys.readouterr().out
    assert "Smoke test completed successfully!" in out_pass


# ---------------------------------------------------------------------------
# Test: Skip mode (fixture / no key)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_smoke_test_skipped_when_not_live_or_no_key(capsys):
    """Non-live or missing key: returns exit code 2."""
    fixture_settings = SimpleNamespace(
        app_mode="fixture",
        llm_provider="deepseek",
        deepseek_api_key=None,
    )
    code = await smoke_test.smoke_test(
        service=None, settings=fixture_settings
    )
    captured = capsys.readouterr().out
    assert code == 2
    assert "SKIPPED (live smoke test not run)" in captured
    assert "Smoke test completed successfully!" not in captured


# ---------------------------------------------------------------------------
# Subprocess test: runs real python smoke_test.py in fixture mode
# ---------------------------------------------------------------------------


def test_subprocess_fixture_mode_skips():
    """Run `python smoke_test.py` for real in fixture mode; asserts returncode == 2."""
    env = os.environ.copy()
    env["APP_MODE"] = "fixture"
    proc = subprocess.run(
        [sys.executable, "smoke_test.py"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 2
    assert "Smoke test completed successfully!" not in proc.stdout
    assert "SKIPPED (live smoke test not run)" in proc.stdout


# ---------------------------------------------------------------------------
# Test: Secret leak prevention (standalone, follow-up, setup; stdout + stderr)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_secret_key_never_leaked_on_standalone_failure(capfd):
    """Fake API key in standalone exception must NOT appear in stdout or stderr."""
    fake_key = "FAKE-KEY-FOR-TEST-123"
    settings = SimpleNamespace(
        app_mode="live",
        llm_provider="deepseek",
        deepseek_api_key=SimpleNamespace(
            get_secret_value=lambda: fake_key
        ),
    )
    service = SimpleNamespace(
        answer_with_context=AsyncMock(
            side_effect=RuntimeError(
                f"Connection refused to endpoint with key {fake_key}"
            )
        )
    )
    code = await smoke_test.smoke_test(
        service=service, settings=settings
    )
    captured = capfd.readouterr()
    assert code == 1
    assert fake_key not in captured.out, "API key was leaked in stdout"
    assert fake_key not in captured.err, "API key was leaked in stderr"


@pytest.mark.asyncio
async def test_secret_key_never_leaked_on_followup_failure(capfd):
    """Fake API key in follow-up exception must NOT appear in stdout or stderr."""
    fake_key = "FAKE-KEY-FOR-TEST-123"
    settings = SimpleNamespace(
        app_mode="live",
        llm_provider="deepseek",
        deepseek_api_key=SimpleNamespace(
            get_secret_value=lambda: fake_key
        ),
    )
    service = SimpleNamespace(
        answer_with_context=AsyncMock(
            side_effect=[
                (make_valid_answer("First answer"), []),
                RuntimeError(f"Follow-up error containing key {fake_key}"),
            ]
        )
    )
    code = await smoke_test.smoke_test(
        service=service, settings=settings
    )
    captured = capfd.readouterr()
    assert code == 1
    assert fake_key not in captured.out, "API key was leaked in stdout"
    assert fake_key not in captured.err, "API key was leaked in stderr"


@pytest.mark.asyncio
async def test_secret_key_never_leaked_on_setup_failure(capfd):
    """Fake API key in setup exception must NOT appear in stdout or stderr."""
    fake_key = "FAKE-KEY-FOR-TEST-123"

    class CrashSettings:
        @property
        def app_mode(self):
            raise RuntimeError(f"Config crash with key {fake_key}")

    code = await smoke_test.smoke_test(service=None, settings=CrashSettings())
    captured = capfd.readouterr()
    assert code == 1
    assert fake_key not in captured.out, "API key was leaked in stdout"
    assert fake_key not in captured.err, "API key was leaked in stderr"
