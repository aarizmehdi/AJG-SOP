from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from packages.contracts.canonical import SourceLocator
from packages.contracts.common import Language, OrganizationOwned, utc_now


class AssistantCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_id: str
    policy_id: str
    policy_title: str
    section_id: str
    heading_path: tuple[str, ...]
    document_id: str
    source: SourceLocator


class GeneratedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answerable: bool
    answer: str
    citations: list[AssistantCitation]


class VerifiedAnswer(OrganizationOwned):
    answerable: bool
    answer: str
    language: Language
    citations: list[AssistantCitation]
    verified: bool
    session_id: str


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=2, max_length=1000)
    language: Language
    session_id: str | None = None


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatSession(OrganizationOwned):
    id: str
    employee_id: str
    language: Language
    created_at: datetime = Field(default_factory=utc_now)


class ChatMessage(OrganizationOwned):
    id: str
    session_id: str
    role: MessageRole
    content: str
    verified: bool = False
    created_at: datetime = Field(default_factory=utc_now)
