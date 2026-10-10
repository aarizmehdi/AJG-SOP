from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class ResponseKind(StrEnum):
    SMALLTALK = "smalltalk"
    POLICY_ANSWER = "policy_answer"
    CLARIFICATION = "clarification"
    NO_ANSWER = "no_answer"
    OUT_OF_SCOPE = "out_of_scope"


class VerifiedAnswer(OrganizationOwned):
    kind: ResponseKind = ResponseKind.POLICY_ANSWER
    answerable: bool
    answer: str
    language: Language
    citations: list[AssistantCitation]
    verified: bool


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ConversationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: MessageRole
    content: str = Field(min_length=1, max_length=3000)


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=2, max_length=1000)
    language: Language
    history: list[ConversationTurn] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def bounded_history(self) -> "AssistantRequest":
        if sum(len(turn.content) for turn in self.history) > 12000:
            raise ValueError("Conversation context exceeds the request limit")
        if any(turn.role is MessageRole.USER and len(turn.content) > 1000 for turn in self.history):
            raise ValueError("A previous user message exceeds the request limit")
        return self


class ChatSession(OrganizationOwned):
    """Legacy record shape retained only for historical purge compatibility."""
    id: str
    employee_id: str
    language: Language
    created_at: datetime = Field(default_factory=utc_now)


class ChatMessage(OrganizationOwned):
    """Legacy record shape retained only for historical purge compatibility."""
    id: str
    session_id: str
    role: MessageRole
    content: str
    verified: bool = False
    created_at: datetime = Field(default_factory=utc_now)
