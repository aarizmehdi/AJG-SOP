import json
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence

import httpx
from pydantic import BaseModel

from packages.contracts.assistant import GeneratedAnswer
from packages.contracts.retrieval import SearchEvidence


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

class DeepSeekSemanticVerifier(SemanticVerifier):
    def __init__(self, api_key: str, base_url: str, model: str = "deepseek-flash"):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self.model_id = model

    async def verify_claims(self, answer: str, evidence: Sequence[SearchEvidence]) -> bool:
        payload = {
            "model": self.model_id,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a factual verification assistant. Verify if ALL claims in the "
                        "generated answer are fully supported by the provided authorized evidence. "
                        "Do NOT use outside knowledge. Return a JSON object with 'is_grounded' (bool) "
                        "and 'unsupported_claims' (list of strings)."
                    )
                },
                {
                    "role": "user",
                    "content": json.dumps({
                        "generated_answer": answer,
                        "authorized_evidence": [getattr(item, "full_text", item.excerpt) for item in evidence]
                    })
                }
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload
                )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            result = SemanticVerificationResult.model_validate_json(content)
            return result.is_grounded
        except Exception:
            return False


class GroundingVerifier:
    """Deterministic safety checks combined with semantic claim verification."""

    def __init__(self, semantic_verifier: SemanticVerifier | None = None) -> None:
        self.semantic_verifier = semantic_verifier or FixtureSemanticVerifier()

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

    async def verify(self, answer: GeneratedAnswer, evidence: Sequence[SearchEvidence]) -> bool:
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
        deterministic = not any(
            phrase in answer_text and phrase not in cited_text
            for phrase in self._unsupported_advice
        )
        if not deterministic:
            return False
            
        # Layer 2: Semantic verification
        try:
            return await self.semantic_verifier.verify_claims(answer.answer, evidence)
        except Exception:
            return False
