"""Request-scoped conversation routing. No server chat state or answer-based retrieval."""

import re
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

from packages.contracts.assistant import (
    ConversationTurn,
    InternalAnswerMode,
    MessageRole,
    ResponseKind,
)
from packages.contracts.common import Language

_SMALLTALK = {
    "hi",
    "hello",
    "hey",
    "salam",
    "salaam",
    "assalamualaikum",
    "assalam o alaikum",
    "thanks",
    "thank you",
    "shukriya",
    "shukria",
    "شکریہ",
    "سلام",
    "السلام علیکم",
    "bye",
    "goodbye",
    "خدا حافظ",
}
_VAGUE = {
    "and",
    "what about that",
    "what about it",
    "what happens after that",
    "aur",
    "اور",
    "what next",
}
_OUTSIDE = re.compile(
    r"\b(weather|cricket score|football score|world cup|movie review|recipe)\b", re.I
)
_FOLLOWUP = re.compile(
    r"^(and |also |what about |how about |does that |is that |can they |can i |"
    r"aur |phir |us |وہ |اور |پھر )",
    re.I,
)


def classify(question: str, history: Sequence[ConversationTurn]) -> ResponseKind | None:
    normalized = re.sub(r"[!?.،؟]+$", "", question.strip().casefold()).strip()
    if normalized in _SMALLTALK:
        return ResponseKind.SMALLTALK
    if _OUTSIDE.search(question):
        return ResponseKind.OUT_OF_SCOPE
    if (
        normalized in _VAGUE or normalized in {"when", "where", "why", "how"}
    ) and not prior_user_question(history):
        return ResponseKind.CLARIFICATION
    return None


def prior_user_question(history: Sequence[ConversationTurn]) -> str | None:
    for turn in reversed(history[-16:]):
        if turn.role is MessageRole.USER and turn.content.strip().casefold() not in _SMALLTALK:
            return turn.content[:500]
    return None


def retrieval_query(question: str, history: Sequence[ConversationTurn]) -> str:
    previous = prior_user_question(history)
    if previous and (_FOLLOWUP.match(question.strip()) or len(question.split()) <= 5):
        return f"{previous} {question}"[:500]
    return question[:500]


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Literal["question", "smalltalk", "out_of_scope", "clarification"]
    original_question: str
    resolved_query: str
    is_follow_up: bool
    answer_mode: InternalAnswerMode


_ORDINAL_MAP = [
    (re.compile(r"\b(first|1st|former)\b", re.I), 0),
    (re.compile(r"\b(second|2nd|latter)\b", re.I), 1),
    (re.compile(r"\b(third|3rd)\b", re.I), 2),
    (re.compile(r"\b(fourth|4th)\b", re.I), 3),
    (re.compile(r"\b(fifth|5th)\b", re.I), 4),
    (re.compile(r"\b(sixth|6th)\b", re.I), 5),
    (re.compile(r"\b(seventh|7th)\b", re.I), 6),
    (re.compile(r"\b(eighth|8th)\b", re.I), 7),
]

_THAT_RULE = re.compile(
    r"\b(that\s+rule|that\s+policy|this\s+rule|this\s+policy|that\s+procedure|this\s+procedure)\b",
    re.I,
)

_APPLY_TO = re.compile(
    r"(?:does\s+(?:the\s+same|this|that)\s+apply\s+to|what\s+about)\s+([A-Za-z0-9_\-\s]+)",
    re.I,
)

_DEADLINE = re.compile(
    r"\b(deadline|due\s+date|submission\s+deadline|submission\s+date|when\s+is\s+it\s+due)\b",
    re.I,
)
_QUANTITY = re.compile(
    r"\b(quantity|capacity|how\s+many\s+tonnes|how\s+many|how\s+much|limit|maximum)\b",
    re.I,
)
_APPROVAL = re.compile(
    r"\b(approv(?:e|es|al|ing)|who\s+signs|authority)\b",
    re.I,
)
_EXCEPTIONS = re.compile(
    r"\b(exceptions?|exemptions?)\b",
    re.I,
)


def bound_history(
    history: Sequence[ConversationTurn], max_turns: int = 6
) -> Sequence[ConversationTurn]:
    """Bound history to the most recent N turns to prevent context blowup."""
    return history[-max_turns:]


def prior_assistant_turn(history: Sequence[ConversationTurn]) -> str | None:
    """Find the most recent assistant turn in bounded history."""
    for turn in reversed(bound_history(history)):
        if turn.role is MessageRole.ASSISTANT and turn.content.strip():
            return turn.content
    return None


_INJECTION_PATTERN = re.compile(
    r"\b(ignore\s+(?:all\s+)?previous|system\s*prompt|system\s*:|developer\s+mode|"
    r"jailbreak|admin\s+override|disregard|you\s+are\s+now|output\s+the\s+secret|"
    r"show\s+prompt|reveal\s+instructions)\b|<[^>]+>|https?://",
    re.I,
)


def extract_assistant_options(text: str) -> list[str]:
    """Extract numbered or bulleted options/items from an assistant message safely."""
    if not text.strip():
        return []
    numbered = re.findall(r"(?:^|\n)\s*(?:\d+[\.\)]|\(\d+\))\s+([^\n]+)", text)
    if numbered:
        items = [_clean_option_item(item) for item in numbered]
        return [i for i in items if i is not None]

    bulleted = re.findall(r"(?:^|\n)\s*[-*•]\s+([^\n]+)", text)
    if bulleted:
        items = [_clean_option_item(item) for item in bulleted]
        return [i for i in items if i is not None]

    return []


def _clean_option_item(item: str) -> str | None:
    if _INJECTION_PATTERN.search(item):
        return None
    cleaned = item.replace("**", "").replace("*", "").strip()
    if " → " in cleaned:
        # Mixed-policy canonical outlines retain both the policy and the heading.
        cleaned = cleaned.replace(" → ", " ")
    elif not re.match(r"Document\s+\d+\s*:", cleaned, re.I):
        parts = re.split(r"(?:\s*[:\-–—]\s+)", cleaned)
        if parts and parts[0].strip():
            cleaned = parts[0].strip()
    cleaned = re.sub(r"[.!?,]+$", "", cleaned).strip()
    cleaned = re.sub(r"[^\w\s\-\(\)\/]", "", cleaned).strip()
    if not cleaned or len(cleaned) < 2 or _INJECTION_PATTERN.search(cleaned):
        return None
    return cleaned[:250]


def extract_topic_from_question(question: str) -> str:
    """Extract core subject/topic from a question, removing interrogative prefixes."""
    q = re.sub(r"[!?.،؟]+$", "", question.strip()).strip()
    patterns = [
        r"^(?:what\s+is\s+the|what\s+are\s+the|what\s+about\s+the|what\s+is|what\s+are)\s+",
        r"^(?:when\s+must|when\s+is\s+the|when\s+is|when\s+should)\s+",
        r"^(?:how\s+is\s+the|how\s+is|how\s+do\s+we|how\s+can\s+i|how\s+to)\s+",
        r"^(?:tell\s+me\s+about\s+the|tell\s+me\s+about|can\s+you\s+explain\s+the|explain\s+the|explain)\s+",
        r"^(?:where\s+is\s+the|who\s+approves\s+the|who\s+is\s+the)\s+",
    ]
    for pat in patterns:
        m = re.match(pat, q, re.I)
        if m:
            topic = q[m.end() :].strip()
            topic = re.sub(
                r"\s+be\s+(reported|handled|submitted|conducted|done)$", "", topic, flags=re.I
            ).strip()
            return topic
    return q


def _extract_attribute_name(question: str) -> str | None:
    if _DEADLINE.search(question):
        return "deadline"
    if _APPROVAL.search(question):
        return "approval authority"
    if _EXCEPTIONS.search(question):
        return "exceptions"
    if _QUANTITY.search(question):
        return "quantity"
    return None


def _is_bare_attribute_question(question: str, attr_regex: re.Pattern[str]) -> bool:
    """Check if the question is asking only about an attribute without its own topic."""
    topic = extract_topic_from_question(question).lower()
    topic = re.sub(
        r"\b(this|that|it|the|about|what|when|who|is|are|any|there|the\s+same|please)\b",
        "",
        topic,
    ).strip()
    remaining = attr_regex.sub("", topic).strip()
    return len(remaining) == 0


def build_query_plan(question: str, history: Sequence[ConversationTurn]) -> QueryPlan:
    kind = classify(question, history)

    if kind == ResponseKind.SMALLTALK:
        return QueryPlan(
            intent="smalltalk",
            original_question=question,
            resolved_query=question[:500],
            is_follow_up=False,
            answer_mode=InternalAnswerMode.NO_ANSWER,
        )
    if kind == ResponseKind.OUT_OF_SCOPE:
        return QueryPlan(
            intent="out_of_scope",
            original_question=question,
            resolved_query=question[:500],
            is_follow_up=False,
            answer_mode=InternalAnswerMode.NO_ANSWER,
        )
    if kind == ResponseKind.CLARIFICATION:
        return QueryPlan(
            intent="clarification",
            original_question=question,
            resolved_query=question[:500],
            is_follow_up=False,
            answer_mode=InternalAnswerMode.ASK_CLARIFICATION,
        )

    previous_user_q = prior_user_question(history)
    assistant_text = prior_assistant_turn(history)
    options = extract_assistant_options(assistant_text) if assistant_text else []

    # 1. Check for ordinal option references ("the first one", "the second one", etc.)
    target_ordinal_index: int | None = None
    for regex, idx in _ORDINAL_MAP:
        if regex.search(question) and (
            options
            or re.search(
                r"\b(?:first|second|third|fourth|fifth|sixth|seventh|eighth|[1-8](?:st|nd|rd|th))"
                r"\s+(?:one|option|section|policy)\b|\b(?:former|latter)\b",
                question,
                re.I,
            )
        ):
            target_ordinal_index = idx
            break

    if target_ordinal_index is not None:
        if target_ordinal_index < len(options):
            option_topic = options[target_ordinal_index]
            attr = _extract_attribute_name(question)
            resolved = f"{option_topic} {attr}" if attr else option_topic
            return QueryPlan(
                intent="question",
                original_question=question,
                resolved_query=resolved[:300],
                is_follow_up=True,
                answer_mode=InternalAnswerMode.ANSWER,
            )
        # Unresolvable reference: option index exceeds options available -> ask clarification
        return QueryPlan(
            intent="clarification",
            original_question=question,
            resolved_query=question[:300],
            is_follow_up=True,
            answer_mode=InternalAnswerMode.ASK_CLARIFICATION,
        )

    # 2. Check for "that rule" / "that policy"
    if _THAT_RULE.search(question):
        if previous_user_q:
            topic = extract_topic_from_question(previous_user_q)
            return QueryPlan(
                intent="question",
                original_question=question,
                resolved_query=f"{topic} rule"[:300],
                is_follow_up=True,
                answer_mode=InternalAnswerMode.ANSWER,
            )
        return QueryPlan(
            intent="clarification",
            original_question=question,
            resolved_query=question[:300],
            is_follow_up=True,
            answer_mode=InternalAnswerMode.ASK_CLARIFICATION,
        )

    # 3. Check for entity transfer: "does the same apply to Store"
    apply_match = _APPLY_TO.search(question)
    if apply_match and previous_user_q:
        target_entity = re.sub(r"[!?.،؟]+$", "", apply_match.group(1)).strip()
        topic = extract_topic_from_question(previous_user_q)
        return QueryPlan(
            intent="question",
            original_question=question,
            resolved_query=f"{topic} {target_entity}"[:300],
            is_follow_up=True,
            answer_mode=InternalAnswerMode.ANSWER,
        )

    # 4. Check for attribute-only follow-ups (deadline, quantity, approval, exceptions)
    for attr_regex, attr_name in [
        (_DEADLINE, "deadline"),
        (_APPROVAL, "approval authority"),
        (_EXCEPTIONS, "exceptions"),
        (_QUANTITY, "quantity"),
    ]:
        if attr_regex.search(question) and previous_user_q:
            if _is_bare_attribute_question(question, attr_regex):
                topic = extract_topic_from_question(previous_user_q)
                return QueryPlan(
                    intent="question",
                    original_question=question,
                    resolved_query=f"{topic} {attr_name}"[:300],
                    is_follow_up=True,
                    answer_mode=InternalAnswerMode.ANSWER,
                )

    # 5. Connective follow-ups starting with "and ", "also ", "what about "
    if previous_user_q and _FOLLOWUP.match(question.strip()):
        topic = extract_topic_from_question(previous_user_q)
        stripped_sub = _FOLLOWUP.sub("", question.strip()).strip()
        stripped_sub = re.sub(r"[!?.،؟]+$", "", stripped_sub).strip()
        resolved = f"{topic} {stripped_sub}"[:300] if stripped_sub else topic
        return QueryPlan(
            intent="question",
            original_question=question,
            resolved_query=resolved,
            is_follow_up=True,
            answer_mode=InternalAnswerMode.ANSWER,
        )

    # 6. Default: New independent question - do NOT inherit previous text
    return QueryPlan(
        intent="question",
        original_question=question,
        resolved_query=question[:500],
        is_follow_up=False,
        answer_mode=(
            InternalAnswerMode.SYNTHESIZE_MULTIPLE_POLICIES
            if re.search(
                r"\b(compare|comparison|differences?|across|both policies)\b", question, re.I
            )
            else InternalAnswerMode.ANSWER
        ),
    )


def canned(kind: ResponseKind, language: Language, question: str = "") -> str:
    if kind is ResponseKind.SMALLTALK:
        normalized = re.sub(r"[!?.،؟]+$", "", question.strip().casefold()).strip()
        if normalized in {"thanks", "thank you", "shukriya", "shukria", "شکریہ"}:
            return {
                Language.ENGLISH: "You're welcome. Ask whenever you need help with an AJG SOP.",
                Language.URDU: "خوشی ہوئی۔ AJG ایس او پی کے بارے میں جب چاہیں پوچھیں۔",
                Language.ROMAN_URDU: "Khushi hui. AJG SOP ke bare mein jab chahen poochhein.",
            }[language]
        if normalized in {"bye", "goodbye", "خدا حافظ"}:
            return {
                Language.ENGLISH: "Goodbye. I'm here when you need SOP guidance.",
                Language.URDU: "خدا حافظ۔ ایس او پی رہنمائی کے لیے میں یہاں موجود ہوں۔",
                Language.ROMAN_URDU: "Khuda hafiz. SOP rehnumai ke liye main yahan hoon.",
            }[language]
    messages = {
        ResponseKind.SMALLTALK: {
            Language.ENGLISH: (
                "Hello! I can help you find guidance in the AJG SOPs available to you. "
                "What would you like to know?"
            ),
            Language.URDU: (
                "السلام علیکم! میں آپ کو دستیاب AJG ایس او پیز میں رہنمائی تلاش کرنے میں "
                "مدد کر سکتا ہوں۔ آپ کیا جاننا چاہتے ہیں؟"
            ),
            Language.ROMAN_URDU: (
                "Assalam o alaikum! Main aap ko dastiyab AJG SOPs mein rehnumai "
                "dhoondne mein madad kar sakta hoon. Aap kya janna chahte hain?"
            ),
        },
        ResponseKind.CLARIFICATION: {
            Language.ENGLISH: (
                "Which SOP topic or procedure do you mean? Please add a little detail "
                "so I can search the right policy."
            ),
            Language.URDU: (
                "آپ کس ایس او پی موضوع یا طریقۂ کار کی بات کر رہے ہیں؟ براہِ کرم "
                "کچھ تفصیل بتائیں تاکہ میں درست پالیسی تلاش کر سکوں۔"
            ),
            Language.ROMAN_URDU: (
                "Aap kis SOP mauzoo ya tareeqa-e-kaar ki baat kar rahe hain? "
                "Thori tafseel batayein taa ke main durust policy dhoond sakoon."
            ),
        },
        ResponseKind.NO_ANSWER: {
            Language.ENGLISH: (
                "I couldn't find enough guidance for that in the SOPs available to you. "
                "Try a more specific question or search the policy library."
            ),
            Language.URDU: (
                "مجھے آپ کے لیے دستیاب ایس او پیز میں اس بارے میں کافی رہنمائی نہیں ملی۔ "
                "مزید واضح سوال پوچھیں یا پالیسی لائبریری میں تلاش کریں۔"
            ),
            Language.ROMAN_URDU: (
                "Mujhe aap ke liye dastiyab SOPs mein is bare mein kaafi rehnumai "
                "nahi mili. Sawal mazeed wazeh karein ya policy library mein talash karein."
            ),
        },
        ResponseKind.OUT_OF_SCOPE: {
            Language.ENGLISH: (
                "I can help with AJG SOP guidance. Ask me about a policy or procedure "
                "available to you."
            ),
            Language.URDU: (
                "میں AJG ایس او پی سے متعلق رہنمائی میں مدد کر سکتا ہوں۔ اپنے لیے دستیاب "
                "کسی پالیسی یا طریقۂ کار کے بارے میں پوچھیں۔"
            ),
            Language.ROMAN_URDU: (
                "Main AJG SOP se mutaliq rehnumai mein madad kar sakta hoon. "
                "Apne liye dastiyab kisi policy ya tareeqa-e-kaar ke bare mein poochhein."
            ),
        },
    }
    return messages[kind][language]
