import json
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence

import httpx
from pydantic import BaseModel

from packages.contracts.assistant import GeneratedAnswer
from packages.contracts.retrieval import SearchEvidence
from services.assistant.chat_transport import ChatCompletionTransport
from services.assistant.llm_errors import LLMUnavailableError


class SemanticVerificationResult(BaseModel):
    is_grounded: bool
    unsupported_claims: list[str]


class SemanticVerifier(ABC):
    @abstractmethod
    async def verify_claims(self, answer: str, evidence: Sequence[SearchEvidence]) -> bool:
        pass


class FixtureSemanticVerifier(SemanticVerifier):
    async def verify_claims(self, answer: str, evidence: Sequence[SearchEvidence]) -> bool:
        return True


class UnavailableSemanticVerifier(SemanticVerifier):
    """Fail-closed semantic verifier when no verifier provider is available."""

    async def verify_claims(self, answer: str, evidence: Sequence[SearchEvidence]) -> bool:
        return False


class DeepSeekSemanticVerifier(SemanticVerifier):
    def __init__(
        self,
        transport_or_api_key: ChatCompletionTransport | str | None = None,
        base_url_or_model: str = "deepseek/deepseek-v4.1-flash-1017",
        model: str = "deepseek-flash",
        timeout: float = 15.0,
        fallback_model: str | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        transport: ChatCompletionTransport | None = None,
    ) -> None:
        eff_transport = transport if transport is not None else (
            transport_or_api_key
            if isinstance(transport_or_api_key, ChatCompletionTransport)
            else None
        )
        eff_key = api_key if api_key is not None else (
            transport_or_api_key if isinstance(transport_or_api_key, str) else None
        )
        eff_url = base_url if base_url is not None else (
            base_url_or_model if eff_transport is None else "https://api.deepseek.com"
        )
        eff_model = model if eff_transport is None else base_url_or_model

        if eff_transport is not None:
            self.transport: ChatCompletionTransport | None = eff_transport
            self.model_id = eff_model
            self.fallback_model = fallback_model
            self._api_key: str | None = None
            self._base_url: str | None = None
            self._timeout = timeout
        else:
            self.transport = None
            self._api_key = eff_key
            self._base_url = eff_url.rstrip("/")
            self.model_id = eff_model
            self.fallback_model = fallback_model
            self._timeout = timeout

    async def verify_claims(self, answer: str, evidence: Sequence[SearchEvidence]) -> bool:
        if not evidence or not answer.strip():
            return False
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a factual verification assistant. Verify if ALL claims in the "
                    "generated answer are fully supported by the provided authorized evidence. "
                    "Do NOT use outside knowledge. Return a JSON object with "
                    "'is_grounded' (bool) and 'unsupported_claims' (list of strings)."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "generated_answer": answer,
                        "authorized_evidence": [
                            getattr(item, "full_text", item.excerpt) for item in evidence
                        ],
                    }
                ),
            },
        ]

        if self.transport is not None:
            try:
                res = await self.transport.complete(
                    messages=messages,
                    response_model=SemanticVerificationResult,
                    model=self.model_id,
                    fallback_model=self.fallback_model,
                    temperature=0.0,
                )
                if res.is_grounded is not True:
                    return False
                if len(res.unsupported_claims) != 0:
                    return False
                return True
            except LLMUnavailableError:
                raise
            except Exception:
                return False

        payload = {
            "model": self.model_id,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                return False
            choices = data.get("choices")
            if not isinstance(choices, list) or not choices:
                return False
            message = choices[0].get("message")
            if not isinstance(message, dict):
                return False
            content = message.get("content")
            if not isinstance(content, str):
                return False
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                return False
            # Reject extra unexpected keys or missing keys
            if set(parsed.keys()) != {"is_grounded", "unsupported_claims"}:
                return False
            # 1. Reject if is_grounded is not strictly boolean True
            is_grounded = parsed.get("is_grounded")
            if is_grounded is not True:
                return False
            # 2. Reject if unsupported_claims is anything other than an empty list
            unsupported_claims = parsed.get("unsupported_claims")
            if not isinstance(unsupported_claims, list) or len(unsupported_claims) != 0:
                return False
            return True
        except LLMUnavailableError:
            raise
        except Exception:
            return False


class GroundingVerifier:
    """Deterministic safety checks combined with claim-to-source semantic verification."""

    def __init__(self, semantic_verifier: SemanticVerifier | None = None) -> None:
        self.semantic_verifier = semantic_verifier or FixtureSemanticVerifier()
        self.last_rejection_reason: str | None = None

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
    _month_names_ex_may = (
        r"(?:jan(?:uary)?|feb(?:ruary)?|march?|apr(?:il)?|"
        r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|"
        r"nov(?:ember)?|dec(?:ember)?)"
    )
    _month_date = re.compile(
        rf"\b(?:"
        rf"(?:\d{{1,2}}(?:st|nd|rd|th)?\s+)?{_month_names_ex_may}(?:\s+\d{{1,2}}(?:st|nd|rd|th)?)?(?:,?\s+\d{{4}})?"
        rf"|(?:\d{{1,2}}(?:st|nd|rd|th)?\s+may|may\s+\d{{1,2}}(?:st|nd|rd|th)?|may,?\s+\d{{4}})"
        rf")\b",
        re.I,
    )
    _iso_date = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
    _sop_number = re.compile(
        r"\bsop(?:-(?:[a-z0-9]+-?)+|\s*#\s*[a-z0-9]+|\s+\d+[a-z0-9.-]*)\b",
        re.I,
    )
    _deadline = re.compile(r"\b(?:deadline|due\s+date|submission\s+date)\b", re.I)
    _instruction_leak = re.compile(
        r"\b(ignore (?:all\s+|previous\s+)*instructions|system prompt|developer message|"
        r"you are (chatgpt|an ai assistant)|reveal (hidden|secret) instructions)\b",
        re.I,
    )

    @staticmethod
    def _extract_numbers(text: str) -> set[str]:
        prose = re.sub(r"(?m)^\s*(?:\(\d+\)|\d+(?:\.\d+)?[.)])\s+", "", text)
        nums: set[str] = set()
        for match in re.findall(
            r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|\b\d+(?:\.\d+)?\b", prose
        ):
            nums.add(match.replace(",", ""))
        return nums

    async def verify(self, answer: GeneratedAnswer, evidence: Sequence[SearchEvidence]) -> bool:
        self.last_rejection_reason = None
        # Deterministic checks first: every citation ID must exist in evidence
        retrieved_chunk_ids = {item.chunk_id for item in evidence}
        cited_ids = {citation.chunk_id for citation in answer.citations}
        if not cited_ids or not cited_ids.issubset(retrieved_chunk_ids):
            self.last_rejection_reason = "citation validation"
            return False

        # Build text exclusively from cited evidence chunks
        cited_chunks = [item for item in evidence if item.chunk_id in cited_ids]
        cited_text = " ".join(
            getattr(item, "full_text", item.excerpt).casefold()
            for item in cited_chunks
        )
        answer_text = answer.answer.casefold().strip()
        if not answer_text or not cited_text:
            self.last_rejection_reason = "citation validation"
            return False

        if self._instruction_leak.search(answer_text):
            self.last_rejection_reason = "instruction leak"
            return False

        # Numbers check (with thousands separator support)
        unsupported_numbers = self._extract_numbers(answer_text) - self._extract_numbers(cited_text)
        if unsupported_numbers:
            self.last_rejection_reason = "number"
            return False

        prose = re.sub(r"(?m)^\s*(?:\(\d+\)|\d+(?:\.\d+)?[.)])\s+", "", answer_text)

        # SOP number check: all SOP references in answer must appear in cited evidence
        unsupported_sops = set(self._sop_number.findall(answer_text)) - set(
            self._sop_number.findall(cited_text)
        )
        if unsupported_sops:
            self.last_rejection_reason = "SOP number"
            return False

        # Deadline check: deadline references in answer must appear in cited evidence
        if self._deadline.search(answer_text) and not self._deadline.search(cited_text):
            self.last_rejection_reason = "deadline"
            return False

        # Contact and date pattern checks
        patterns = [
            (self._email, "email"),
            (self._url, "URL"),
            (self._phone, "phone"),
            (self._percent, "percent"),
            (self._time, "time"),
            (self._month_date, "date"),
            (self._iso_date, "date"),
        ]
        for pattern, name in patterns:
            if set(pattern.findall(prose)) - set(pattern.findall(cited_text)):
                self.last_rejection_reason = name
                return False

        deterministic = not any(
            phrase in answer_text and phrase not in cited_text
            for phrase in self._unsupported_advice
        )
        if not deterministic:
            self.last_rejection_reason = "unsupported advice"
            return False

        # Layer 2: Claim-to-source semantic verification (send ONLY cited chunks)
        try:
            passed = await self.semantic_verifier.verify_claims(answer.answer, cited_chunks)
            if not passed:
                self.last_rejection_reason = "semantic verifier reason"
            return passed
        except LLMUnavailableError:
            raise
        except Exception:
            self.last_rejection_reason = "semantic verifier reason"
            return False
