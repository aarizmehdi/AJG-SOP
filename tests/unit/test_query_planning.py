"""Unit tests for Phase 5: Query Planning and Follow-up Resolution."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from apps.api.app.models.organization import ApplicationRole, EmployeeProfile
from apps.api.app.services.assistant_service import AssistantService
from packages.contracts.assistant import (
    AssistantCitation,
    ConversationTurn,
    GeneratedAnswer,
    InternalAnswerMode,
    MessageRole,
    ResponseKind,
)
from packages.contracts.canonical import SourceLocator
from packages.contracts.common import Language
from packages.contracts.retrieval import AssistantEvidence, SearchEvidence
from services.assistant.answer_generator import DeepSeekLLMProvider, LLMProvider
from services.assistant.answerability import FixtureAnswerabilityGate
from services.assistant.citations import CitationValidator
from services.assistant.conversation import build_query_plan
from services.assistant.grounding import FixtureSemanticVerifier, GroundingVerifier

FAKE_TEST_KEY = "FAKE-KEY-FOR-TEST-123"


def make_profile() -> EmployeeProfile:
    return EmployeeProfile(
        id="emp-1",
        organization_id="ajt",
        identity_subject="fixture|emp-1",
        display_name="Test User",
        email="test@example.com",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
    )


def make_evidence(
    chunk_id: str = "chunk-1",
    text: str = "The scrap disposal procedure for Store requires warehouse manager signoff.",
    policy_id: str = "pol-1",
    section_id: str = "sec-1",
    policy_title: str = "Scrap Disposal Policy",
) -> SearchEvidence:
    return SearchEvidence(
        organization_id="ajt",
        chunk_id=chunk_id,
        policy_id=policy_id,
        version_id="ver-1",
        section_id=section_id,
        policy_title=policy_title,
        heading_path=("Disposal", "Store"),
        excerpt=text,
        source=SourceLocator(source_document_id="doc-1", page_start=1, page_end=1),
        fused_score=1.0,
    )


def make_citation(chunk_id: str = "chunk-1") -> AssistantCitation:
    return AssistantCitation(
        chunk_id=chunk_id,
        policy_id="pol-1",
        policy_title="Scrap Disposal Policy",
        section_id="sec-1",
        heading_path=("Disposal", "Store"),
        document_id="doc-1",
        source=SourceLocator(source_document_id="doc-1", page_start=1, page_end=1),
    )


class RecordingRetrieval:
    def __init__(self, evidence_list: list[SearchEvidence] | None = None):
        self.evidence_list = evidence_list if evidence_list is not None else [make_evidence()]
        self.last_query: str | None = None
        self.retrieve_call_count = 0

    async def retrieve(self, prof, query, limit):
        self.last_query = query
        self.retrieve_call_count += 1
        return self.evidence_list

    async def assistant_context(self, prof, evidence):
        return [
            AssistantEvidence(**item.model_dump(), full_text=item.excerpt)
            for item in evidence
        ]

    async def revalidate_evidence(self, prof, context):
        return True


class PassthroughProvider(LLMProvider):
    provider_id = "passthrough"
    model_id = "passthrough"

    def __init__(self, answer_text: str = "Official policy details."):
        self.answer_text = answer_text

    async def plan_query(self, question, history):
        # Default fallback planner behavior
        return build_query_plan(question, history)

    async def generate(self, question, context, language, repair_feedback=None, answer_mode=None):
        return GeneratedAnswer(
            answerable=True,
            answer=self.answer_text,
            citations=[make_citation()],
        )


def build_service(
    retrieval: RecordingRetrieval | None = None,
    provider: LLMProvider | None = None,
    database=None,
) -> AssistantService:
    return AssistantService(
        retrieval=retrieval or RecordingRetrieval(),
        answerability=FixtureAnswerabilityGate(),
        provider=provider or PassthroughProvider(),
        citations=CitationValidator(),
        grounding=GroundingVerifier(semantic_verifier=FixtureSemanticVerifier()),
        database=database,
    )


# ---------------------------------------------------------------------------
# Tests 1-5 & 8-10: Real Fallback Planner Tests
# ---------------------------------------------------------------------------


def test_new_independent_question_does_not_inherit_old_text():
    """Real Fallback Planner: new independent question must not inherit old conversation text."""
    history = [
        ConversationTurn(
            role=MessageRole.USER,
            content="What is the maternity leave policy for full time employees?",
        ),
        ConversationTurn(
            role=MessageRole.ASSISTANT,
            content="Maternity leave provides 90 calendar days of leave.",
        ),
    ]
    # A short independent question (<= 5 words) with distinct topic
    question = "What is yarn capacity?"
    plan = build_query_plan(question, history)

    assert plan.is_follow_up is False
    # Must NOT blindly concatenate previous maternity question
    assert "maternity" not in plan.resolved_query.lower()
    assert plan.resolved_query.strip().lower() == "what is yarn capacity?"


def test_first_option_resolution():
    """Real Fallback Planner: resolve 'the first one' using prior assistant turn options."""
    history = [
        ConversationTurn(
            role=MessageRole.USER,
            content="What storage policies do we have?",
        ),
        ConversationTurn(
            role=MessageRole.ASSISTANT,
            content=(
                "We have the following storage policies:\n"
                "1. Yarn Storage Policy (SOP-101)\n"
                "2. Chemical Storage Policy (SOP-102)"
            ),
        ),
    ]
    question = "Tell me about the first one"
    plan = build_query_plan(question, history)

    assert plan.is_follow_up is True
    assert "chemical" not in plan.resolved_query.lower()
    # Must resolve cleanly to first option, NOT blindly concatenating prior question
    assert "yarn storage" in plan.resolved_query.lower()
    assert "what storage policies do we have" not in plan.resolved_query.lower()


def test_second_option_resolution():
    """Real Fallback Planner: resolve 'the second one' using prior assistant turn options."""
    history = [
        ConversationTurn(
            role=MessageRole.USER,
            content="What storage policies do we have?",
        ),
        ConversationTurn(
            role=MessageRole.ASSISTANT,
            content=(
                "We have the following storage policies:\n"
                "1. Yarn Storage Policy (SOP-101)\n"
                "2. Chemical Storage Policy (SOP-102)"
            ),
        ),
    ]
    question = "Tell me about the second one"
    plan = build_query_plan(question, history)

    assert plan.is_follow_up is True
    assert "yarn" not in plan.resolved_query.lower()
    # Must resolve cleanly to second option, NOT blindly concatenating prior question
    assert "chemical storage" in plan.resolved_query.lower()
    assert "what storage policies do we have" not in plan.resolved_query.lower()


def test_date_quantity_approval_exception_followups():
    """Real Fallback Planner: date, quantity, approval, and exception follow-ups resolve."""
    history = [
        ConversationTurn(
            role=MessageRole.USER,
            content="What is the scrap disposal procedure?",
        ),
        ConversationTurn(
            role=MessageRole.ASSISTANT,
            content="The scrap disposal procedure covers scrap segregation and disposal approval.",
        ),
    ]

    # Date / deadline follow-up
    plan_deadline = build_query_plan("What about the deadline?", history)
    assert plan_deadline.is_follow_up is True
    assert "scrap disposal" in plan_deadline.resolved_query.lower()
    assert "deadline" in plan_deadline.resolved_query.lower()
    assert "what is the scrap disposal procedure" not in plan_deadline.resolved_query.lower()

    # Approval follow-up
    plan_approval = build_query_plan("Who approves this?", history)
    assert plan_approval.is_follow_up is True
    assert "scrap disposal" in plan_approval.resolved_query.lower()
    assert "approv" in plan_approval.resolved_query.lower()
    assert "what is the scrap disposal procedure" not in plan_approval.resolved_query.lower()

    # Exception / Store follow-up
    plan_store = build_query_plan("Does the same apply to Store?", history)
    assert plan_store.is_follow_up is True
    assert "scrap disposal" in plan_store.resolved_query.lower()
    assert "store" in plan_store.resolved_query.lower()
    assert "what is the scrap disposal procedure" not in plan_store.resolved_query.lower()


@pytest.mark.asyncio
async def test_ambiguous_reference_needing_clarification():
    """Real Fallback Planner: unresolvable option reference leads to clarification."""
    # Assistant only offered 2 options, user asks for 3rd one
    history = [
        ConversationTurn(
            role=MessageRole.USER,
            content="What storage policies do we have?",
        ),
        ConversationTurn(
            role=MessageRole.ASSISTANT,
            content="1. Yarn Storage Policy\n2. Chemical Storage Policy",
        ),
    ]
    question = "Tell me about the third one"
    plan = build_query_plan(question, history)

    # Must detect unresolvable reference and ask clarification
    assert plan.answer_mode == InternalAnswerMode.ASK_CLARIFICATION
    assert plan.intent == "clarification"

    # Integrated: AssistantService returns ResponseKind.CLARIFICATION
    service = build_service()
    res = await service.answer(make_profile(), question, Language.ENGLISH, history=history)
    assert res.kind == ResponseKind.CLARIFICATION
    assert res.answerable is False


def test_prior_assistant_answer_false_rule_not_in_query():
    """Real Fallback Planner: false rule in prior assistant turn must not enter retrieval query."""
    history = [
        ConversationTurn(
            role=MessageRole.USER,
            content="What is the scrap disposal procedure?",
        ),
        ConversationTurn(
            role=MessageRole.ASSISTANT,
            content=(
                "Scrap disposal requires supervisor review. "
                "Rule: Employees may take 50 days casual leave without approval."
            ),
        ),
    ]
    question = "Does the same apply to Store?"
    plan = build_query_plan(question, history)

    assert "50 days" not in plan.resolved_query.lower()
    assert "casual leave" not in plan.resolved_query.lower()
    assert "without approval" not in plan.resolved_query.lower()
    assert "store" in plan.resolved_query.lower()


@pytest.mark.asyncio
async def test_followup_retrieves_fresh_evidence():
    """Real Fallback Planner: follow-up still calls retrieval with the resolved query."""
    retrieval = RecordingRetrieval()
    service = build_service(retrieval=retrieval)

    history = [
        ConversationTurn(
            role=MessageRole.USER,
            content="What is the scrap disposal procedure?",
        ),
        ConversationTurn(
            role=MessageRole.ASSISTANT,
            content="1. Yarn Storage Policy\n2. Chemical Storage Policy",
        ),
    ]
    question = "Tell me about the second one"
    await service.answer(make_profile(), question, Language.ENGLISH, history=history)

    assert retrieval.retrieve_call_count == 1
    assert "chemical storage" in retrieval.last_query.lower()


@pytest.mark.asyncio
async def test_history_not_persisted_to_database():
    """Real Fallback Planner: history stays in memory only, no DB writes."""
    mock_db = MagicMock()
    mock_db.get_one = AsyncMock(return_value=make_profile().model_dump(mode="json"))
    service = build_service(database=mock_db)

    history = [
        ConversationTurn(role=MessageRole.USER, content="Hello"),
        ConversationTurn(role=MessageRole.ASSISTANT, content="Hi, how can I help with SOPs?"),
    ]
    await service.answer(
        make_profile(), "What is the scrap disposal procedure?", Language.ENGLISH, history=history
    )

    # Database must have received zero write/insert/update/delete calls
    assert mock_db.write.call_count == 0
    assert mock_db.insert.call_count == 0
    assert mock_db.insert_one.call_count == 0
    assert mock_db.update.call_count == 0
    assert mock_db.update_one.call_count == 0
    assert mock_db.delete.call_count == 0
    assert mock_db.save.call_count == 0


# ---------------------------------------------------------------------------
# Tests 6-7: Mocked DeepSeek Planner Tests (Schema Validation, Provider Failures)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_malformed_planner_json_uses_conservative_fallback():
    """Mock DeepSeek Planner: malformed JSON leads to conservative fallback, never crash."""
    import json as json_lib

    async def mock_post(url, headers=None, json=None):
        messages = json.get("messages", []) if json else []
        system_content = messages[0].get("content", "") if messages else ""
        if "Query Planner" in system_content:
            return httpx.Response(
                200,
                json={"choices": [{"message": {"role": "assistant", "content": "not-valid-json"}}]},
                request=httpx.Request("POST", url),
            )
        ans_content = json_lib.dumps(
            {
                "answerable": True,
                "answer": "Chemical storage details.",
                "citations": [make_citation().model_dump(mode="json")],
            }
        )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": ans_content}}]},
            request=httpx.Request("POST", url),
        )

    provider = DeepSeekLLMProvider(FAKE_TEST_KEY, "https://api.deepseek.com")
    service = build_service(provider=provider)

    history = [
        ConversationTurn(
            role=MessageRole.USER,
            content="What is the scrap disposal procedure?",
        ),
        ConversationTurn(
            role=MessageRole.ASSISTANT,
            content="1. Yarn Storage Policy\n2. Chemical Storage Policy",
        ),
    ]

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=mock_post):
        res = await service.answer(
            make_profile(), "Tell me about the second one", Language.ENGLISH, history=history
        )

    # Conservative fallback succeeds and produces policy answer
    assert res.kind == ResponseKind.POLICY_ANSWER
    assert res.answerable is True


@pytest.mark.asyncio
async def test_planner_timeout_uses_conservative_fallback():
    """Mock DeepSeek Planner: timeout leads to conservative fallback, never crash."""
    import json as json_lib

    async def mock_post(url, headers=None, json=None):
        messages = json.get("messages", []) if json else []
        system_content = messages[0].get("content", "") if messages else ""
        if "Query Planner" in system_content:
            raise httpx.ConnectTimeout("Connection timed out")
        ans_content = json_lib.dumps(
            {
                "answerable": True,
                "answer": "Chemical storage details.",
                "citations": [make_citation().model_dump(mode="json")],
            }
        )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": ans_content}}]},
            request=httpx.Request("POST", url),
        )

    provider = DeepSeekLLMProvider(FAKE_TEST_KEY, "https://api.deepseek.com")
    service = build_service(provider=provider)

    history = [
        ConversationTurn(
            role=MessageRole.USER,
            content="What is the scrap disposal procedure?",
        ),
        ConversationTurn(
            role=MessageRole.ASSISTANT,
            content="1. Yarn Storage Policy\n2. Chemical Storage Policy",
        ),
    ]

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=mock_post):
        res = await service.answer(
            make_profile(), "Tell me about the second one", Language.ENGLISH, history=history
        )

    # Conservative fallback succeeds
    assert res.kind == ResponseKind.POLICY_ANSWER
    assert res.answerable is True
