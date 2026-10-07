"""Request-scoped conversation routing. No server chat state or answer-based retrieval."""

import re
from collections.abc import Sequence

from pydantic import BaseModel

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
    intent: str
    original_question: str
    resolved_query: str
    is_follow_up: bool
    answer_mode: InternalAnswerMode


def build_query_plan(question: str, history: Sequence[ConversationTurn]) -> QueryPlan:
    kind = classify(question, history)

    if kind == ResponseKind.SMALLTALK:
        intent = "smalltalk"
        mode = InternalAnswerMode.NO_ANSWER
    elif kind == ResponseKind.OUT_OF_SCOPE:
        intent = "out_of_scope"
        mode = InternalAnswerMode.NO_ANSWER
    elif kind == ResponseKind.CLARIFICATION:
        intent = "clarification"
        mode = InternalAnswerMode.ASK_CLARIFICATION
    else:
        intent = "question"
        # Deterministic logic cannot reliably detect SYNTHESIZE_MULTIPLE_POLICIES
        mode = InternalAnswerMode.ANSWER

    is_follow_up = False
    resolved = question[:500]
    previous = prior_user_question(history)

    # Heuristics for follow-up and reference resolution
    normalized = question.strip().casefold()
    if previous and (_FOLLOWUP.match(question.strip()) or len(question.split()) <= 5):
        is_follow_up = True
        # NOTE: Deterministic concatenation fails to resolve references like "second one"
        # from the assistant's previous response, because it only prepends the user's prior question.  # noqa: E501
        resolved = f"{previous} {question}"[:500]
    elif "second one" in normalized or "former" in normalized or "latter" in normalized:
        is_follow_up = True
        resolved = f"{previous} {question}"[:500] if previous else question[:500]

    return QueryPlan(
        intent=intent,
        original_question=question,
        resolved_query=resolved,
        is_follow_up=is_follow_up,
        answer_mode=mode,
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
