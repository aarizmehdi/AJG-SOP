from dataclasses import dataclass, field

from packages.contracts.assistant import ChatMessage, ChatSession
from packages.contracts.canonical import CanonicalSOP, RetrievalChunk
from packages.contracts.policy import AuditEvent, IngestionJob, SOPPolicy, SOPVersion
from packages.contracts.source import SourceDocument


@dataclass
class FoundationStore:
    sources: dict[str, SourceDocument] = field(default_factory=dict)
    canonicals: dict[str, CanonicalSOP] = field(default_factory=dict)
    raw_results: dict[str, object] = field(default_factory=dict)
    policies: dict[str, SOPPolicy] = field(default_factory=dict)
    versions: dict[str, SOPVersion] = field(default_factory=dict)
    jobs: dict[str, IngestionJob] = field(default_factory=dict)
    chunks: dict[str, list[RetrievalChunk]] = field(default_factory=dict)
    audit_events: list[AuditEvent] = field(default_factory=list)
    chat_sessions: dict[str, ChatSession] = field(default_factory=dict)
    chat_messages: list[ChatMessage] = field(default_factory=list)
