from collections import defaultdict
from collections.abc import Iterable
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel
from pymongo import AsyncMongoClient

from apps.api.app.services.foundation_store import FoundationStore
from packages.contracts.assistant import ChatMessage, ChatSession
from packages.contracts.canonical import CanonicalSOP, RetrievalChunk
from packages.contracts.policy import AuditEvent, IngestionJob, SOPPolicy, SOPVersion
from packages.contracts.source import SourceDocument
from services.ingestion.extractors.base import RawDocumentResult

Model = TypeVar("Model", bound=BaseModel)


class FoundationPersistence(Protocol):
    async def load(self, store: FoundationStore) -> None: ...

    async def flush(self, store: FoundationStore) -> None: ...

    async def close(self) -> None: ...


class FixtureFoundationPersistence:
    async def load(self, store: FoundationStore) -> None:
        return None

    async def flush(self, store: FoundationStore) -> None:
        return None

    async def close(self) -> None:
        return None


class MongoFoundationPersistence:
    """Mongo is canonical; FoundationStore is a process-local unit-of-work cache.

    flush() persists only the mutations recorded during the current request.
    It never deletes records that are absent from the process snapshot, preventing
    data loss from concurrent processes, stale restarts, or multi-worker deployments.
    """

    _models: dict[str, type[BaseModel]] = {
        "source_documents": SourceDocument,
        "canonical_sops": CanonicalSOP,
        "raw_parser_results": RawDocumentResult,
        "policies": SOPPolicy,
        "policy_versions": SOPVersion,
        "ingestion_jobs": IngestionJob,
        "retrieval_chunks": RetrievalChunk,
        "audit_events": AuditEvent,
        "chat_sessions": ChatSession,
        "chat_messages": ChatMessage,
    }

    # Collections where items are only inserted, never updated or deleted.
    _append_only: frozenset[str] = frozenset({"audit_events", "chat_messages"})

    def __init__(self, uri: str, database: str) -> None:
        self._client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(uri)
        self._database = self._client[database]

    async def load(self, store: FoundationStore) -> None:
        records: dict[str, list[BaseModel]] = {}
        for collection, model in self._models.items():
            items: list[BaseModel] = []
            async for document in self._database[collection].find({}):
                document.pop("_id", None)
                document.pop("_foundation_key", None)
                items.append(model.model_validate(document))
            records[collection] = items
        store.sources = {
            item.id: item for item in self._typed(records["source_documents"], SourceDocument)
        }
        store.canonicals = {
            item.source_document_ids[0]: item
            for item in self._typed(records["canonical_sops"], CanonicalSOP)
            if item.source_document_ids
        }
        store.raw_results = {
            item.source_document_id: item
            for item in self._typed(records["raw_parser_results"], RawDocumentResult)
        }
        store.policies = {item.id: item for item in self._typed(records["policies"], SOPPolicy)}
        store.versions = {
            item.id: item for item in self._typed(records["policy_versions"], SOPVersion)
        }
        store.jobs = {
            item.id: item for item in self._typed(records["ingestion_jobs"], IngestionJob)
        }
        chunks: defaultdict[str, list[RetrievalChunk]] = defaultdict(list)
        for item in self._typed(records["retrieval_chunks"], RetrievalChunk):
            chunks[item.version_id].append(item)
        store.chunks = dict(chunks)
        store.audit_events = self._typed(records["audit_events"], AuditEvent)
        store.chat_sessions = {
            item.id: item for item in self._typed(records["chat_sessions"], ChatSession)
        }
        store.chat_messages = self._typed(records["chat_messages"], ChatMessage)

    async def flush(self, store: FoundationStore) -> None:
        """Persist only the mutations recorded since the last flush."""
        mutations = store.get_mutations()
        if not mutations:
            return

        for collection, mutation_set in mutations.items():
            # Upserted (keyed) records: replace or insert, never delete
            for key, item in mutation_set.upserted.items():
                if not isinstance(item, BaseModel):
                    continue
                organization_id = self._organization_id(item)
                await self._database[collection].replace_one(
                    {"organization_id": organization_id, "_foundation_key": key},
                    {
                        **item.model_dump(mode="json"),
                        "_foundation_key": key,
                    },
                    upsert=True,
                )

            # Appended (insert-only) records: just insert, never upsert or delete
            for item in mutation_set.appended:
                if not isinstance(item, BaseModel):
                    continue
                organization_id = self._organization_id(item)
                key = self._key(item)
                await self._database[collection].update_one(
                    {"organization_id": organization_id, "_foundation_key": key},
                    {
                        "$setOnInsert": {
                            **item.model_dump(mode="json"),
                            "_foundation_key": key,
                        }
                    },
                    upsert=True,
                )

    async def close(self) -> None:
        await self._client.close()

    @staticmethod
    def _key(item: BaseModel) -> str:
        value = getattr(item, "id", None) or getattr(item, "source_document_id", None)
        if not value:
            raise ValueError("Persistent foundation records require a stable id")
        return str(value)

    @staticmethod
    def _organization_id(item: BaseModel) -> str:
        value = getattr(item, "organization_id", None)
        if not value:
            raise ValueError("Persistent foundation records require organization_id")
        return str(value)

    @staticmethod
    def _typed(items: Iterable[BaseModel], model: type[Model]) -> list[Model]:
        return [item for item in items if isinstance(item, model)]
