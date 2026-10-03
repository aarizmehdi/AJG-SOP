import re
from collections.abc import Sequence

from packages.contracts.assistant import GeneratedAnswer
from packages.contracts.retrieval import SearchEvidence


class GroundingVerifier:
    """Deterministic safety checks; calibration awaits the real SOP evaluation set."""

    _unsupported_advice = (
        "contact hr",
        "ask hr",
        "call hr",
        "contact your manager",
        "ask your supervisor",
        "seek approval",
    )
    _email = re.compile(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", re.I)
    _url = re.compile(r"https?://[^\s)]+", re.I)
    _phone = re.compile(r"(?<!\w)(?:\+\d[\d\s()-]{7,}\d|0\d[\d\s()-]{8,}\d)(?!\w)")
    _percent = re.compile(r"\b\d+(?:\.\d+)?\s*%")
    _time = re.compile(r"\b\d{1,2}:\d{2}(?:\s*[ap]m)?\b", re.I)
    _month_date = re.compile(
        r"\b(?:\d{1,2}\s+)?(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
        r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|"
        r"nov(?:ember)?|dec(?:ember)?)(?:\s+\d{1,2})?(?:,?\s+\d{4})?\b",
        re.I,
    )
    _instruction_leak = re.compile(
        r"\b(ignore (all |previous )?instructions|system prompt|developer message|"
        r"you are (chatgpt|an ai assistant)|reveal (hidden|secret) instructions)\b",
        re.I,
    )

    def verify(self, answer: GeneratedAnswer, evidence: Sequence[SearchEvidence]) -> bool:
        cited_ids = {citation.chunk_id for citation in answer.citations}
        cited_text = " ".join(
            getattr(item, "full_text", item.excerpt).casefold()
            for item in evidence
            if item.chunk_id in cited_ids
        )
        answer_text = answer.answer.casefold().strip()
        if not answer_text or not cited_text:
            return False
        if self._instruction_leak.search(answer_text):
            return False
        prose = re.sub(r"(?m)^\s*\d+[.)]\s+", "", answer_text)
        unsupported_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", prose)) - set(
            re.findall(r"\b\d+(?:\.\d+)?\b", cited_text)
        )
        if unsupported_numbers:
            return False
        for pattern in (
            self._email,
            self._url,
            self._phone,
            self._percent,
            self._time,
            self._month_date,
        ):
            if set(pattern.findall(prose)) - set(pattern.findall(cited_text)):
                return False
        return not any(
            phrase in answer_text and phrase not in cited_text
            for phrase in self._unsupported_advice
        )
