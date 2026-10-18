import json
from collections.abc import Sequence

import pytest
from fastapi.testclient import TestClient

from apps.api.app.main import app
from apps.api.app.models.organization import ApplicationRole, EmployeeProfile
from apps.api.app.services.assistant_service import AssistantService, VerificationError
from packages.contracts.assistant import (
    AssistantCitation,
    ConversationTurn,
    GeneratedAnswer,
    InternalAnswerMode,
    ResponseKind,
)
from packages.contracts.canonical import SourceLocator
from packages.contracts.common import Language
from packages.contracts.retrieval import AssistantEvidence, SearchEvidence
from services.assistant.answer_generator import LLMProvider
from services.assistant.answerability import FixtureAnswerabilityGate
from services.assistant.citations import CitationValidator
from services.assistant.conversation import QueryPlan
from services.assistant.grounding import GroundingVerifier


def make_profile() -> EmployeeProfile:
    return EmployeeProfile(
        id="user-1",
        organization_id="ajt",
        identity_subject="fixture|sop-admin",
        display_name="Hamza Shah",
        email="hamza@example.test",
        application_roles=frozenset({ApplicationRole.EMPLOYEE, ApplicationRole.SOP_ADMIN}),
        departments=frozenset({"operations", "store"}),
        locations=frozenset({"head-office", "peshawar-main"}),
        organizational_roles=frozenset({"sop_owner"}),
    )


def make_chunk(
    chunk_id: str,
    policy_id: str,
    policy_title: str,
    section_id: str,
    heading: str,
    text: str,
) -> SearchEvidence:
    return SearchEvidence(
        organization_id="ajt",
        chunk_id=chunk_id,
        policy_id=policy_id,
        version_id="ver-1",
        section_id=section_id,
        policy_title=policy_title,
        heading_path=(policy_title, heading),
        excerpt=text,
        source=SourceLocator(source_document_id=f"doc-{policy_id}"),
        fused_score=1.0,
    )


class UngroundedProvider(LLMProvider):
    provider_id = "mock-ungrounded"
    model_id = "test"

    def __init__(self, fabricated_text: str = "Fabricated ungrounded claims.") -> None:
        self.fabricated_text = fabricated_text
        self.call_count = 0
        self.last_repair_feedback: str | None = None

    async def plan_query(self, question: str, history: Sequence[ConversationTurn]) -> QueryPlan:
        return QueryPlan(
            resolved_query=question,
            is_follow_up=False,
            answer_mode=InternalAnswerMode.ANSWER,
            intent="policy_query",
            original_question=question,
        )

    async def generate(
        self,
        question: str,
        context: Sequence[SearchEvidence],
        language: Language,
        repair_feedback: str | None = None,
        answer_mode: InternalAnswerMode | None = None,
    ) -> GeneratedAnswer:
        self.call_count += 1
        self.last_repair_feedback = repair_feedback
        return GeneratedAnswer(
            answerable=True,
            answer=f"{self.fabricated_text} attempt={self.call_count}",
            citations=[
                AssistantCitation(
                    chunk_id=context[0].chunk_id,
                    policy_id=context[0].policy_id,
                    policy_title=context[0].policy_title,
                    section_id=context[0].section_id,
                    heading_path=context[0].heading_path,
                    document_id=context[0].source.source_document_id,
                    source=context[0].source,
                )
            ],
        )


class StubRetrieval:
    def __init__(self, chunks: list[SearchEvidence]) -> None:
        self.chunks = chunks

    async def retrieve(
        self, profile: EmployeeProfile, query: str, limit: int = 8
    ) -> list[SearchEvidence]:
        return self.chunks

    async def assistant_context(
        self, profile: EmployeeProfile, evidence: Sequence[SearchEvidence]
    ) -> list[AssistantEvidence]:
        return [AssistantEvidence(**item.model_dump(), full_text=item.excerpt) for item in evidence]

    async def revalidate_evidence(
        self, profile: EmployeeProfile, context: Sequence[SearchEvidence]
    ) -> bool:
        return True


# ---------------------------------------------------------------------------
# Test 1: Legitimate answer with "may", thousands separators, contract number passes
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_1_legitimate_answer_with_may_thousands_separators_passes():
    ev_text = (
        "A.J. Textile Mills Limited. SOP #49 — SOP for Yarn Conversion. "
        "Contract # 108451: Paper Cone: 600 * 24 = 14,400 Cones. Dated: 13-02-2018."
    )
    ev = make_chunk("chunk-1", "pol-49", "SOP #49", "sec-1", "Contract", ev_text)
    ans_text = (
        "The Chief Accountant may maintain records for Contract # 108451. "
        "Calculated as 600 x 24 = 14,400 cones."
    )
    answer = GeneratedAnswer(
        answerable=True,
        answer=ans_text,
        citations=[
            AssistantCitation(
                chunk_id="chunk-1",
                policy_id="pol-49",
                policy_title="SOP #49",
                section_id="sec-1",
                heading_path=("SOP #49", "Contract"),
                document_id="doc-pol-49",
                source=SourceLocator(source_document_id="doc-pol-49"),
            )
        ],
    )
    verifier = GroundingVerifier()
    assert await verifier.verify(answer, [ev]) is True


# ---------------------------------------------------------------------------
# Test 2: Fabricated date/phone/number/SOP number still rejected
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_2_fabricated_values_still_rejected():
    ev = make_chunk(
        "chunk-1",
        "pol-49",
        "SOP #49",
        "sec-1",
        "Contract",
        "Storage capacity is 12 tonnes. Dated: 13-02-2018.",
    )
    verifier = GroundingVerifier()

    # Fabricated May date
    ans_date = GeneratedAnswer(
        answerable=True,
        answer="The effective date is 15 May 2026.",
        citations=[
            AssistantCitation(
                chunk_id="chunk-1",
                policy_id="pol-49",
                policy_title="SOP #49",
                section_id="sec-1",
                heading_path=("SOP #49", "Contract"),
                document_id="doc-pol-49",
                source=SourceLocator(source_document_id="doc-pol-49"),
            )
        ],
    )
    assert await verifier.verify(ans_date, [ev]) is False

    # Fabricated phone
    ans_phone = GeneratedAnswer(
        answerable=True,
        answer="Contact the manager at +92 300 1234567.",
        citations=ans_date.citations,
    )
    assert await verifier.verify(ans_phone, [ev]) is False

    # Fabricated number
    ans_num = GeneratedAnswer(
        answerable=True,
        answer="Storage capacity is 950 tonnes.",
        citations=ans_date.citations,
    )
    assert await verifier.verify(ans_num, [ev]) is False

    # Fabricated SOP number
    ans_sop = GeneratedAnswer(
        answerable=True,
        answer="Please follow SOP-999 for details.",
        citations=ans_date.citations,
    )
    assert await verifier.verify(ans_sop, [ev]) is False


# ---------------------------------------------------------------------------
# Test 3: Multi-section policy overview with zero LLM text
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_3_multisection_policy_returns_overview_zero_llm_text():
    chunks = [
        make_chunk(
            "c1", "pol-49", "SOP #49 — Yarn Conversion", "sec-contract", "Contract", "Contract text"
        ),
        make_chunk(
            "c2",
            "pol-49",
            "SOP #49 — Yarn Conversion",
            "sec-accounts",
            "Accounts Working and Consumption",
            "Accounts text",
        ),
        make_chunk(
            "c3", "pol-49", "SOP #49 — Yarn Conversion", "sec-arrival", "Arrival", "Arrival text"
        ),
    ]
    provider = UngroundedProvider(fabricated_text="I invented details about this policy.")
    service = AssistantService(
        retrieval=StubRetrieval(chunks),
        answerability=FixtureAnswerabilityGate(),
        provider=provider,
        citations=CitationValidator(),
        grounding=GroundingVerifier(),
    )

    profile = make_profile()
    result = await service.answer(profile, "what is SOP #49", Language.ENGLISH)

    # 1. Verification failed twice on provider
    assert provider.call_count == 2
    # 2. Repair feedback passed failing check name
    assert (
        "number" in (provider.last_repair_feedback or "")
        or "citation" in (provider.last_repair_feedback or "")
        or "grounding" in (provider.last_repair_feedback or "")
    )
    # 3. Contract semantics
    assert result.kind == ResponseKind.CLARIFICATION
    assert result.answerable is False
    assert result.verified is True
    # 4. Zero LLM text present
    assert "invented" not in result.answer
    assert "fabricated" not in result.answer
    # 5. Correct sections and headings present
    assert "Contract" in result.answer
    assert "Accounts Working and Consumption" in result.answer
    assert "Arrival" in result.answer
    assert "Which section would you like details on?" in result.answer
    # 6. Citations present for sections
    assert len(result.citations) == 3
    assert {c.chunk_id for c in result.citations} == {"c1", "c2", "c3"}


# ---------------------------------------------------------------------------
# Test 4: Different large policy proves generic behavior
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_4_different_large_policy_overview_proves_generic():
    chunks = [
        make_chunk(
            "hr-1",
            "pol-hr",
            "SOP #76 — HR Onboarding",
            "sec-probation",
            "Probation Guidelines",
            "Probation text",
        ),
        make_chunk(
            "hr-2",
            "pol-hr",
            "SOP #76 — HR Onboarding",
            "sec-leave",
            "Leave Entitlements",
            "Leave text",
        ),
        make_chunk(
            "hr-3",
            "pol-hr",
            "SOP #76 — HR Onboarding",
            "sec-conduct",
            "Code of Conduct",
            "Conduct text",
        ),
    ]
    provider = UngroundedProvider(fabricated_text="Hallucinated HR rules.")
    service = AssistantService(
        retrieval=StubRetrieval(chunks),
        answerability=FixtureAnswerabilityGate(),
        provider=provider,
        citations=CitationValidator(),
        grounding=GroundingVerifier(),
    )

    profile = make_profile()
    result = await service.answer(profile, "what is HR Onboarding SOP", Language.ENGLISH)

    assert result.kind == ResponseKind.CLARIFICATION
    assert "SOP #76 — HR Onboarding" in result.answer
    assert "Probation Guidelines" in result.answer
    assert "Leave Entitlements" in result.answer
    assert "Code of Conduct" in result.answer
    assert "Hallucinated" not in result.answer
    assert len(result.citations) == 3


# ---------------------------------------------------------------------------
# Test 5: Restricted/unauthorized chunks never appear in overview
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_5_restricted_unauthorized_chunks_never_in_overview():
    auth_chunk = make_chunk("c1", "pol-1", "Safety SOP", "sec-1", "General Safety", "Safety text")
    unauth_chunk = make_chunk(
        "c2",
        "pol-1",
        "Safety SOP",
        "sec-confidential",
        "Executive Emergency Protocol",
        "Confidential text",
    )

    class FilteredRetrieval(StubRetrieval):
        async def assistant_context(self, profile, evidence):
            # Simulated authorization filter: strips unauth_chunk
            return [
                AssistantEvidence(**item.model_dump(), full_text=item.excerpt)
                for item in evidence
                if item.chunk_id != "c2"
            ]

    provider = UngroundedProvider()
    service = AssistantService(
        retrieval=FilteredRetrieval([auth_chunk, unauth_chunk]),
        answerability=FixtureAnswerabilityGate(),
        provider=provider,
        citations=CitationValidator(),
        grounding=GroundingVerifier(),
    )

    profile = make_profile()
    # With only 1 authorized chunk remaining, single-section triggers safe VerificationError
    with pytest.raises(VerificationError):
        await service.answer(profile, "tell me about Safety SOP", Language.ENGLISH)


# ---------------------------------------------------------------------------
# Test 6: Single-section or empty evidence returns existing safe error
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_6_single_section_or_empty_evidence_raises_error():
    # Single section only
    single_chunk = [
        make_chunk("c1", "pol-1", "Single Section Policy", "sec-1", "Only Section", "Only text")
    ]
    provider = UngroundedProvider()
    service = AssistantService(
        retrieval=StubRetrieval(single_chunk),
        answerability=FixtureAnswerabilityGate(),
        provider=provider,
        citations=CitationValidator(),
        grounding=GroundingVerifier(),
    )

    profile = make_profile()
    # Single-section must NOT produce overview; must raise VerificationError
    with pytest.raises(VerificationError):
        await service.answer(profile, "what is Single Section Policy", Language.ENGLISH)


# ---------------------------------------------------------------------------
# Test 7: SSE endpoint streams overview only after decision with no unverified text
# ---------------------------------------------------------------------------
def test_7_sse_endpoint_overview_streaming():
    chunks = [
        make_chunk("c1", "pol-49", "SOP #49", "sec-1", "Contract", "Contract text"),
        make_chunk("c2", "pol-49", "SOP #49", "sec-2", "Accounts", "Accounts text"),
    ]
    provider = UngroundedProvider(fabricated_text="UNVERIFIED_HALLUCINATION_SECRET")

    with TestClient(app) as client:
        # Patch the app assistant service with mock provider and retrieval
        service = AssistantService(
            retrieval=StubRetrieval(chunks),
            answerability=FixtureAnswerabilityGate(),
            provider=provider,
            citations=CitationValidator(),
            grounding=GroundingVerifier(),
        )
        app.state.assistant_service = service

        response = client.post(
            "/api/v1/assistant/answer/events",
            headers={"Authorization": "Fixture sop-admin"},
            json={
                "question": "what is SOP #49 SOP for Yarn Conversion Packing Material Handling",
                "language": "english",
                "history": [],
            },
        )
        assert response.status_code == 200

        events = []
        for line in response.text.split("\n\n"):
            if line.strip():
                parts = line.strip().split("\n")
                event_type = parts[0].replace("event: ", "")
                data_str = parts[1].replace("data: ", "")
                events.append((event_type, json.loads(data_str)))

        # Assert no error event was yielded
        event_names = [e[0] for e in events]
        assert "error" not in event_names
        assert "answer_start" in event_names
        assert "answer_delta" in event_names
        assert "sources" in event_names
        assert "done" in event_names

        # Concatenate streamed text
        deltas = [e[1]["text"] for e in events if e[0] == "answer_delta"]
        full_streamed_answer = "".join(deltas)

        # Assert unverified LLM text is NEVER emitted
        assert "UNVERIFIED_HALLUCINATION_SECRET" not in full_streamed_answer
        # Assert deterministic overview sections are present
        assert "Contract" in full_streamed_answer
        assert "Accounts" in full_streamed_answer
        assert "Which section would you like details on?" in full_streamed_answer
