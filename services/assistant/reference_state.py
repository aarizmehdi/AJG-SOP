"""Bounded, ephemeral, identity-bound references. Never a store of policy facts or chats."""

import re
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from time import monotonic
from uuid import UUID, uuid4

from apps.api.app.models.organization import EmployeeProfile
from packages.contracts.assistant import (
    AssistantSectionOption,
    ConversationTurn,
    InternalAnswerMode,
    MessageRole,
)
from services.assistant.conversation import QueryPlan, build_query_plan


@dataclass(frozen=True)
class ReferenceTurn:
    conversation_id: UUID
    revision: int
    references: tuple[AssistantSectionOption, ...]


@dataclass
class _Slot:
    owner: tuple[str, str, str]
    expires_at: float
    revision: int = 0
    references: tuple[AssistantSectionOption, ...] = ()


class ConversationReferences:
    """Single-process TTL/LRU state; restart/eviction means clarification, not invented history."""

    def __init__(
        self,
        *,
        max_sessions: int = 1000,
        ttl_seconds: float = 1800,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_sessions < 1 or ttl_seconds <= 0:
            raise ValueError("Conversation reference bounds must be positive")
        self.max_sessions = max_sessions
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._slots: OrderedDict[UUID, _Slot] = OrderedDict()

    @staticmethod
    def _owner(profile: EmployeeProfile) -> tuple[str, str, str]:
        return profile.organization_id, profile.id, profile.identity_subject

    def begin(self, profile: EmployeeProfile, conversation_id: UUID | None) -> ReferenceTurn:
        now = self.clock()
        for key in [key for key, slot in self._slots.items() if slot.expires_at <= now]:
            del self._slots[key]
        slot = self._slots.get(conversation_id) if conversation_id else None
        if slot is None or slot.owner != self._owner(profile):
            # Do not confirm another user's session exists, or adopt client-chosen IDs.
            conversation_id = uuid4()
            slot = _Slot(owner=self._owner(profile), expires_at=now + self.ttl_seconds)
            self._slots[conversation_id] = slot
        assert conversation_id is not None
        slot.revision += 1
        slot.expires_at = now + self.ttl_seconds
        self._slots.move_to_end(conversation_id)
        while len(self._slots) > self.max_sessions:
            self._slots.popitem(last=False)
        return ReferenceTurn(conversation_id, slot.revision, slot.references)

    def remember(
        self,
        profile: EmployeeProfile,
        turn: ReferenceTurn,
        references: Sequence[AssistantSectionOption],
    ) -> None:
        slot = self._slots.get(turn.conversation_id)
        if (
            slot is not None
            and slot.owner == self._owner(profile)
            and slot.revision == turn.revision
            and slot.expires_at > self.clock()
        ):
            # A slower overlapping request cannot overwrite a newer turn's context.
            slot.references = tuple(item.model_copy(deep=True) for item in references[:8])


_REFERENCE = re.compile(
    # Do not interpret relative clauses ("policy that covers leave") or dummy
    # pronouns ("is it mandatory to report damage?") as a topic reference.
    r"\b(?:it|that|this|those|them)\s*[?.!،؟]*$|"
    r"\b(?:this|that|same)\s+(?:rule|policy|procedure|section|requirement)\b|"
    r"\b(?:it|this|that)\s+(?:apply|applies|mean|means|require|requires|work|works)\b|"
    r"\b(former|latter)\b|"
    r"\b(?:first|second|third|fourth|fifth|sixth|seventh|eighth|[1-8](?:st|nd|rd|th))"
    r"\s+(?:one|option|section|policy)\b|\b(?:more|further)\s+(?:detail|details|explanation)\b|"
    r"\b(?:mazeed|wazahat|tafseel|iski|uski)\b|\b(?:اس|اسے|اسی|مزید|تفصیل)\b",
    re.I,
)
_ORDINALS = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth")
_EXPANSION = re.compile(
    r"\b(explain|elaborate|expand|detail|details|clarify|break\s+(?:it|that)\s+down|"
    r"simpler|simplify|step\s+by\s+step|tafseel|wazahat|mazeed)\b|(?:تفصیل|وضاحت|مزید)",
    re.I,
)
_CONTINUATION = re.compile(
    r"^(?:(?:please|(?:can|could|would) you)\s+)?"
    r"(?:continue|go on|what next|what happens next|explain|elaborate|expand|"
    r"more details?|(?:and|also|what about|how about)\s+(?:the\s+)?"
    r"(?:deadline|approval|exceptions?|quantity|capacity))\s*[?.!]*$",
    re.I,
)


def trusted_query_plan(
    question: str,
    references: Sequence[AssistantSectionOption],
) -> QueryPlan:
    """Resolve references from reauthorized canonical identities, never client answer text.

    This is reference resolution, not a second model or a source of policy facts.
    Independent topics stay independent; all factual turns still retrieve again.
    """
    plan = build_query_plan(question, ())
    if plan.intent in {"smalltalk", "out_of_scope"}:
        return plan
    reference = bool(_REFERENCE.search(question) or _CONTINUATION.fullmatch(question.strip()))
    ordinal = re.search(
        r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|[1-8](?:st|nd|rd|th))"
        r"\s+(?:one|option|section|policy)\b|\b(former|latter)\b",
        question,
        re.I,
    )
    selected = list(references)
    if ordinal:
        word = (ordinal[1] or ordinal[2]).casefold()
        index = (
            _ORDINALS.index(word)
            if word in _ORDINALS
            else 0
            if word == "former"
            else 1
            if word == "latter"
            else int(word[0]) - 1
        )
        selected = selected[index : index + 1]
    # Bare attribute questions can be resolved by the existing planner against a
    # synthetic heading-only context, constructed exclusively by the server.
    if references:
        subject = " / ".join(dict.fromkeys(" > ".join(r.heading_path) for r in selected))[:500]
        history = [ConversationTurn(role=MessageRole.USER, content=subject or "policy")]
        attribute_plan = build_query_plan(question, history)
        if (
            not reference
            and attribute_plan.is_follow_up
            and not re.match(r"^(and|also|what about|how about)\b", question.strip(), re.I)
        ):
            return attribute_plan
    if reference and selected:
        subject = " / ".join(dict.fromkeys(" > ".join(r.heading_path) for r in selected))[:350]
        return QueryPlan(
            intent="question",
            original_question=question,
            resolved_query=f"{question.strip()}\nReferenced SOP section: {subject}"[:500],
            is_follow_up=True,
            answer_mode=InternalAnswerMode.SYNTHESIZE_MULTIPLE_POLICIES
            if re.search(
                r"\b(compare|comparison|differences?|across|both policies)\b", question, re.I
            )
            else InternalAnswerMode.ANSWER,
        )
    if reference or (not references and _EXPANSION.search(question) and len(question.split()) < 5):
        # An explicit new subject ("explain annual leave") is not an ellipsis.
        if not reference and not re.search(r"\b(more|further|it|that)\b", question, re.I):
            return plan
        return plan.model_copy(
            update={
                "intent": "clarification",
                "is_follow_up": True,
                "answer_mode": InternalAnswerMode.ASK_CLARIFICATION,
            }
        )
    return plan
