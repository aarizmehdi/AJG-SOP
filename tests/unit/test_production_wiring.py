"""Production wiring honesty tests: live vs fixture, fail-closed mechanics, and gate evaluation."""

from unittest.mock import AsyncMock

import pytest

from apps.api.app.config import Settings
from apps.api.app.main import build_assistant_components
from apps.api.app.models.organization import ApplicationRole, EmployeeProfile, MembershipStatus
from apps.api.app.services.assistant_service import AssistantService, VerificationError
from packages.contracts.assistant import ResponseKind
from packages.contracts.canonical import SourceLocator
from packages.contracts.common import Language
from packages.contracts.retrieval import AssistantEvidence, SearchEvidence
from services.assistant.answer_generator import (
    DeepSeekLLMProvider,
    FixtureLLMProvider,
    LLMProvider,
    LLMResponseError,
    LLMUnavailableError,
    UnavailableLLMProvider,
)
from services.assistant.answerability import (
    AnswerabilityDecision,
    AnswerabilityResult,
    DeepSeekAnswerabilityGate,
    FixtureAnswerabilityGate,
    UnavailableAnswerabilityGate,
)
from services.assistant.citations import CitationValidator
from services.assistant.grounding import (
    DeepSeekSemanticVerifier,
    FixtureSemanticVerifier,
    GroundingVerifier,
    UnavailableSemanticVerifier,
)

FAKE_TEST_KEY = "FAKE-KEY-FOR-TEST-123"


def make_profile() -> EmployeeProfile:
    return EmployeeProfile(
        id="emp-1",
        organization_id="ajt",
        identity_subject="fixture|emp-1",
        display_name="Test User",
        email="test@example.com",
        departments=frozenset({"Sales"}),
        status=MembershipStatus.ACTIVE,
        active=True,
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
    )


def make_evidence(
    chunk_id: str = "chunk-1",
    text: str = "Damaged stock must be reported within 24 hours.",
) -> SearchEvidence:
    return SearchEvidence(
        organization_id="ajt",
        chunk_id=chunk_id,
        policy_id="pol-1",
        version_id="ver-1",
        section_id="sec-1",
        policy_title="Damaged Stock Procedure",
        heading_path=("Reporting", "Damaged Stock"),
        excerpt=text,
        source=SourceLocator(source_document_id="doc-1", page_start=1, page_end=1),
        fused_score=1.0,
    )


class StubRetrieval:
    def __init__(self, evidence_list: list[SearchEvidence] | None = None):
        self.evidence_list = evidence_list if evidence_list is not None else [make_evidence()]

    async def retrieve(self, prof, query, limit):
        return self.evidence_list

    async def assistant_context(self, prof, evidence):
        return [
            AssistantEvidence(**item.model_dump(), full_text=item.excerpt)
            for item in evidence
        ]

    async def revalidate_evidence(self, prof, context):
        return True


def make_live_settings(
    llm_provider: str = "deepseek",
    deepseek_api_key: str | None = FAKE_TEST_KEY,
) -> Settings:
    return Settings(
        app_mode="live",
        llm_provider=llm_provider,
        deepseek_api_key=deepseek_api_key,
        firebase_project_id="test-project",
        firebase_service_account_json='{"type": "service_account"}',  # type: ignore[arg-type]
        s3_access_key_id="fake-s3-key",  # type: ignore[arg-type]
        s3_secret_access_key="fake-s3-secret",  # type: ignore[arg-type]
        embedding_provider="pinecone_e5",
        web_origin="https://app.azizjan.com",
    )


def test_1_live_mode_with_key_wires_deepseek_classes():
    """Live mode with DeepSeek key wires strictly DeepSeek-backed classes."""
    settings = make_live_settings(llm_provider="deepseek", deepseek_api_key=FAKE_TEST_KEY)
    llm, verifier, gate = build_assistant_components(settings)

    assert isinstance(llm, DeepSeekLLMProvider)
    assert isinstance(verifier, DeepSeekSemanticVerifier)
    assert isinstance(gate, DeepSeekAnswerabilityGate)
    assert not isinstance(llm, FixtureLLMProvider)
    assert not isinstance(verifier, FixtureSemanticVerifier)
    assert not isinstance(gate, FixtureAnswerabilityGate)


def test_2_live_mode_without_key_wires_unavailable_fail_closed_classes():
    """Live mode without API key wires fail-closed unavailable classes (zero fixture fallback)."""
    settings = make_live_settings(llm_provider="deepseek", deepseek_api_key=None)
    llm, verifier, gate = build_assistant_components(settings)

    assert isinstance(llm, UnavailableLLMProvider)
    assert isinstance(verifier, UnavailableSemanticVerifier)
    assert isinstance(gate, UnavailableAnswerabilityGate)
    assert not isinstance(llm, FixtureLLMProvider)
    assert not isinstance(verifier, FixtureSemanticVerifier)
    assert not isinstance(gate, FixtureAnswerabilityGate)


@pytest.mark.asyncio
async def test_3_live_mode_without_key_fails_closed_end_to_end_no_answer_released():
    """End-to-end: live mode with missing key releases zero policy answers."""
    service = AssistantService(
        retrieval=StubRetrieval(),
        answerability=UnavailableAnswerabilityGate(),
        provider=UnavailableLLMProvider(),
        citations=CitationValidator(),
        grounding=GroundingVerifier(semantic_verifier=UnavailableSemanticVerifier()),
    )
    result = await service.answer(
        make_profile(), "How is damaged stock handled?", Language.ENGLISH
    )

    # Gate returns INSUFFICIENT_EVIDENCE -> canned NO_ANSWER
    assert result.answerable is False
    assert result.kind == ResponseKind.NO_ANSWER
    assert result.citations == []
    assert result.verified is True
    # Zero policy excerpts or generated facts
    assert "damaged stock" not in result.answer.lower()


@pytest.mark.asyncio
async def test_4_unavailable_provider_and_verifier_fail_closed():
    """UnavailableLLMProvider raises on generate/plan; UnavailableSemanticVerifier returns False."""
    llm = UnavailableLLMProvider()
    verifier = UnavailableSemanticVerifier()

    with pytest.raises(LLMUnavailableError):
        await llm.generate("How?", [make_evidence()], Language.ENGLISH)

    with pytest.raises(LLMUnavailableError):
        await llm.plan_query("How?", ())

    assert await verifier.verify_claims("Some answer", [make_evidence()]) is False


def test_5_fixture_mode_wires_fixture_classes():
    """Fixture mode with fixture provider wires fixture-backed classes."""
    settings = Settings(
        app_mode="fixture",
        llm_provider="fixture",
    )
    llm, verifier, gate = build_assistant_components(settings)

    assert isinstance(llm, FixtureLLMProvider)
    assert isinstance(verifier, FixtureSemanticVerifier)
    assert isinstance(gate, FixtureAnswerabilityGate)


def test_6_unsupported_provider_value_does_not_default():
    """Unsupported llm_provider string fails closed to Unavailable classes, NOT default."""
    settings = make_live_settings(
        llm_provider="unsupported_bogus_provider", deepseek_api_key=FAKE_TEST_KEY
    )
    llm, verifier, gate = build_assistant_components(settings)

    assert isinstance(llm, UnavailableLLMProvider)
    assert isinstance(verifier, UnavailableSemanticVerifier)
    assert isinstance(gate, UnavailableAnswerabilityGate)
    assert not isinstance(llm, DeepSeekLLMProvider)
    assert not isinstance(llm, FixtureLLMProvider)


def test_6b_unsupported_provider_in_fixture_mode_does_not_default():
    """Unsupported provider in fixture mode fails closed to Unavailable classes, NOT default."""
    settings = Settings(
        app_mode="fixture",
        llm_provider="unsupported_bogus_provider",
    )
    llm, verifier, gate = build_assistant_components(settings)

    assert isinstance(llm, UnavailableLLMProvider)
    assert isinstance(verifier, UnavailableSemanticVerifier)
    assert not isinstance(llm, FixtureLLMProvider)


@pytest.mark.asyncio
async def test_7_live_path_calls_async_evaluate_never_sync_is_answerable():
    """In live path, AssistantService calls only async evaluate(), never sync is_answerable."""
    gate = DeepSeekAnswerabilityGate(FAKE_TEST_KEY, "https://api.deepseek.com")

    # If sync is_answerable is called, it would raise AssertionError
    def sync_fail(*args, **kwargs):
        raise AssertionError("Sync is_answerable must NEVER be called in live path!")

    gate.is_answerable = sync_fail  # type: ignore[assignment]
    gate.evaluate = AsyncMock(  # type: ignore[method-assign]
        return_value=AnswerabilityResult(decision=AnswerabilityDecision.INSUFFICIENT_EVIDENCE)
    )

    service = AssistantService(
        retrieval=StubRetrieval(),
        answerability=gate,
        provider=UnavailableLLMProvider(),
        citations=CitationValidator(),
        grounding=GroundingVerifier(),
    )

    # Calling answer must use evaluate() without raising from sync_fail
    result = await service.answer(make_profile(), "How is stock handled?", Language.ENGLISH)
    assert result.kind == ResponseKind.NO_ANSWER
    assert gate.evaluate.await_count > 0


@pytest.mark.asyncio
async def test_8_no_except_path_returns_unverified_answer():
    """Verify that no failure or exception path returns an ungrounded or unverified answer."""
    class CrashingProvider(LLMProvider):
        provider_id = "crash"
        model_id = "crash"

        async def plan_query(self, question, history):
            raise RuntimeError("Planner crash")

        async def generate(
            self, question, evidence, language, repair_feedback=None, answer_mode=None
        ):
            raise LLMResponseError("Malformed LLM response")

    service = AssistantService(
        retrieval=StubRetrieval(),
        answerability=FixtureAnswerabilityGate(),
        provider=CrashingProvider(),
        citations=CitationValidator(),
        grounding=GroundingVerifier(),
    )

    # Both repair attempts fail with LLMResponseError -> raises VerificationError
    with pytest.raises(VerificationError) as exc_info:
        await service.answer(make_profile(), "How is stock handled?", Language.ENGLISH)

    assert "Provider response remained malformed" in str(exc_info.value)
