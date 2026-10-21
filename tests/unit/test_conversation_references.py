from uuid import uuid4

import pytest

from apps.api.app.models.organization import ApplicationRole, EmployeeProfile
from packages.contracts.assistant import AssistantSectionOption, InternalAnswerMode
from packages.contracts.canonical import SourceLocator
from services.assistant.reference_state import ConversationReferences, trusted_query_plan


def profile(**changes) -> EmployeeProfile:
    return EmployeeProfile(
        **{
            "id": "employee-one",
            "organization_id": "ajg",
            "identity_subject": "firebase|one",
            "display_name": "Fixture Employee",
            "email": "one@example.test",
            "application_roles": frozenset({ApplicationRole.EMPLOYEE}),
            **changes,
        }
    )


def section(heading: str = "Dispatch") -> AssistantSectionOption:
    return AssistantSectionOption(
        policy_id="policy-one",
        policy_title="Synthetic store policy",
        version_id="version-one",
        section_id=heading,
        heading=heading,
        heading_path=("Synthetic store policy", heading),
        source=SourceLocator(source_document_id="source-one", page_start=2, page_end=2),
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "employee-two"},
        {"organization_id": "other-organization"},
        {"identity_subject": "firebase|two"},
    ],
)
def test_owner_boundaries_never_expose_or_adopt_another_session(changes):
    store = ConversationReferences()
    owner = profile()
    first = store.begin(owner, None)
    store.remember(owner, first, [section()])
    foreign = store.begin(profile(**changes), first.conversation_id)
    assert foreign.conversation_id != first.conversation_id
    assert foreign.references == ()
    assert store.begin(owner, first.conversation_id).references == (section(),)


def test_unknown_client_ids_expiry_and_lru_start_empty_server_sessions():
    clock = [0.0]
    store = ConversationReferences(max_sessions=2, ttl_seconds=10, clock=lambda: clock[0])
    owner = profile()
    chosen = uuid4()
    first = store.begin(owner, chosen)
    assert first.conversation_id != chosen
    store.remember(owner, first, [section()])
    second = store.begin(owner, None)
    store.begin(owner, first.conversation_id)  # first is most recently used
    store.begin(owner, None)
    assert store.begin(owner, second.conversation_id).references == ()
    clock[0] = 11
    expired = store.begin(owner, first.conversation_id)
    assert expired.conversation_id != first.conversation_id
    assert expired.references == ()


def test_reference_state_is_bounded_copied_and_older_requests_cannot_overwrite():
    store = ConversationReferences()
    owner = profile()
    first = store.begin(owner, None)
    latest = store.begin(owner, first.conversation_id)
    refs = [section(str(index)) for index in range(12)]
    store.remember(owner, latest, refs)
    refs[0].heading = "mutated caller object"
    store.remember(owner, first, [section("obsolete")])
    saved = store.begin(owner, first.conversation_id).references
    assert len(saved) == 8
    assert saved[0].heading == "0"
    assert not {"question", "answer", "full_text", "excerpt"} & set(type(saved[0]).model_fields)


@pytest.mark.parametrize("bounds", [{"max_sessions": 0}, {"ttl_seconds": 0}])
def test_invalid_bounds_fail_closed(bounds):
    with pytest.raises(ValueError):
        ConversationReferences(**bounds)


@pytest.mark.parametrize(
    "question",
    [
        "Explain it in more detail",
        "Explain that policy",
        "Who approves it?",
        "What is the deadline?",
        "Continue",
        "Could you elaborate?",
        "What about the deadline?",
        "And capacity?",
        "What next?",
        "اس کی مزید تفصیل بتائیں",
        "iski tafseel batayein",
    ],
)
def test_followups_use_only_server_section_headings(question):
    plan = trusted_query_plan(question, [section()])
    assert plan.is_follow_up
    assert plan.intent == "question"
    assert "Dispatch" in plan.resolved_query


@pytest.mark.parametrize(
    "question",
    [
        "Explain annual leave",
        "What about bike maintenance?",
        "Is it mandatory to report damage?",
        "Show the policy that covers leave",
        "First aid procedure",
        "Who approves purchase orders?",
    ],
)
def test_new_subjects_do_not_inherit_previous_policy(question):
    plan = trusted_query_plan(question, [section()])
    assert not plan.is_follow_up
    assert plan.resolved_query == question


def test_ordinals_resolve_exact_server_options_and_missing_references_clarify():
    plan = trusted_query_plan("Explain the second one", [section("Receiving"), section()])
    assert "Dispatch" in plan.resolved_query
    assert "Receiving" not in plan.resolved_query
    for question, refs in [
        ("Explain the third one", [section()]),
        ("Explain it", []),
        ("Continue", []),
    ]:
        plan = trusted_query_plan(question, refs)
        assert plan.answer_mode is InternalAnswerMode.ASK_CLARIFICATION


def test_comparison_keeps_synthesis_mode():
    plan = trusted_query_plan("Compare both policies with this policy", [section()])
    assert plan.answer_mode is InternalAnswerMode.SYNTHESIZE_MULTIPLE_POLICIES
