from dataclasses import dataclass, field

from packages.contracts.assistant import ChatMessage, ChatSession
from packages.contracts.canonical import CanonicalSOP, RetrievalChunk
from packages.contracts.policy import AuditEvent, IngestionJob, SOPPolicy, SOPVersion
from packages.contracts.source import SourceDocument


@dataclass
class MutationSet:
    """Tracks records that were modified during a request."""

    upserted: dict[str, object] = field(default_factory=dict)
    appended: list[object] = field(default_factory=list)


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
    _mutations: dict[str, MutationSet] = field(default_factory=dict)

    def mark_modified(self, collection: str, key: str, item: object) -> None:
        """Record that a keyed record was created or updated."""
        mutation = self._mutations.setdefault(collection, MutationSet())
        mutation.upserted[key] = item

    def mark_appended(self, collection: str, item: object) -> None:
        """Record that an item was appended to an append-only collection."""
        mutation = self._mutations.setdefault(collection, MutationSet())
        mutation.appended.append(item)

    def get_mutations(self) -> dict[str, MutationSet]:
        return dict(self._mutations)

    def clear_mutations(self) -> None:
        self._mutations.clear()
