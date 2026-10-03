from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any
from uuid import uuid4

import anyio
from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from apps.api.app.repositories.purge_graph import discover, evict, store_rows
from apps.api.app.services.foundation_store import FoundationStore
from packages.contracts.common import utc_now
from packages.contracts.policy import AuditEvent
from packages.contracts.purge import PurgeGraph


class PurgeRepository:
    """Fixture implementation; Mongo adapter uses the same graph discovery rules."""

    def __init__(self, store: FoundationStore, database: Any = None) -> None:
        self.store = store
        self.database = database
        self._operations: dict[tuple[str, str], dict[str, Any]] = {}
        self._lock = anyio.Lock()
        self.cache_listener: Callable[[set[str]], None] | None = None

    async def rows(self, org: str) -> dict[str, list[dict[str, Any]]]:
        if self.database is None:
            return {
                name: [row for row in rows if row.get("organization_id") == org]
                for name, rows in store_rows(self.store).items()
            }
        return {
            name: await self.database[name]
            .find({"$or": [{"organization_id": org}, {"organization_id": None}]})
            .to_list(None)
            for name in await self.database.list_collection_names()
        }

    async def graph(self, org: str, policy: str) -> PurgeGraph:
        return discover(await self.rows(org), org, policy)

    async def operation(self, org: str, policy: str) -> dict[str, Any] | None:
        if self.database is None:
            pending = self._operations.get((org, policy))
            event = next(
                (
                    e.model_dump(mode="json")
                    for e in self.store.audit_events
                    if e.organization_id == org
                    and e.action == "policy.purged"
                    and e.entity_id == policy
                ),
                None,
            )
        else:
            pending = await self.database.policy_purges.find_one({"_id": f"{org}:{policy}"})
            event = await self.database.audit_events.find_one(
                {"organization_id": org, "action": "policy.purged", "entity_id": policy}
            )
        if pending:
            return dict(pending)
        if not event:
            return None
        return {
            "status": "complete",
            "actor_id": event["actor_id"],
            "result": {
                "policy_id": policy,
                "status": "complete",
                "counts": event["metadata"]["counts"],
                "stages": {
                    stage: "complete" for stage in ("pinecone", "r2", "mongo", "verification")
                },
                "remaining": {"mongo_references": 0, "r2_objects": 0, "pinecone_vectors": 0},
                "error": None,
            },
        }

    async def finish(self, org: str, policy: str) -> None:
        """The single minimal audit tombstone becomes the durable invalidation marker."""
        if self.database is None:
            self._operations.pop((org, policy), None)
        else:
            event = await self.database.audit_events.find_one(
                {"organization_id": org, "action": "policy.purged", "entity_id": policy}
            )
            if event is None:
                raise RuntimeError("Cannot remove retry manifest before the audit tombstone exists")
            await self.database.policy_purges.delete_one(
                {"_id": f"{org}:{policy}", "organization_id": org}
            )

    async def save(self, org: str, policy: str, operation: dict[str, Any]) -> None:
        data = {**operation, "organization_id": org, "policy_id": policy}
        if self.database is None:
            self._operations[(org, policy)] = data
        else:
            await self.database.policy_purges.replace_one(
                {"_id": f"{org}:{policy}"}, data, upsert=True
            )

    async def synchronize_cache(self) -> set[str]:
        rows = (
            list(self._operations.values())
            if self.database is None
            else await self.database.policy_purges.find({}).to_list(None)
        )
        removed_chunks: set[str] = set()
        completed = (
            [
                e.model_dump(mode="json")
                for e in self.store.audit_events
                if e.action == "policy.purged"
            ]
            if self.database is None
            else await self.database.audit_events.find({"action": "policy.purged"}).to_list(None)
        )
        rows.extend(
            {"organization_id": e["organization_id"], "policy_id": e["entity_id"]}
            for e in completed
        )
        for row in rows:
            removed_chunks.update(evict(self.store, row["organization_id"], row["policy_id"]))
        if self.cache_listener is not None:
            self.cache_listener(removed_chunks)
        return removed_chunks

    async def delete_graph(self, graph: PurgeGraph) -> dict[str, int]:
        counts: dict[str, int] = {}
        if self.database is None:
            counts = {name: len(rows) for name, rows in graph.records.items()}
            evict(self.store, graph.organization_id, graph.policy_id)
            return counts
        # Re-discover to include late exact audit references before final metadata removal.
        fresh = discover(
            await self.rows(graph.organization_id),
            graph.organization_id,
            graph.policy_id,
            set(graph.entity_ids),
        )
        for name, rows in fresh.records.items():
            ids = [ObjectId(str(row["key"])) if row["object_id"] else row["key"] for row in rows]
            result = await self.database[name].delete_many(
                {"organization_id": graph.organization_id, "_id": {"$in": ids}}
            )
            counts[name] = result.deleted_count
        return counts

    async def tombstone(self, org: str, policy: str, actor: str, counts: dict[str, Any]) -> None:
        event = AuditEvent(
            id=f"purged-{policy}",
            organization_id=org,
            actor_id=actor,
            action="policy.purged",
            entity_type="policy",
            entity_id=policy,
            metadata={"counts": counts},
        )
        if self.database is not None:
            await self.database.audit_events.replace_one(
                {"organization_id": org, "id": event.id},
                {**event.model_dump(mode="json"), "_foundation_key": event.id},
                upsert=True,
            )
        self.store.audit_events[:] = [e for e in self.store.audit_events if e.id != event.id]
        self.store.audit_events.append(event)

    @asynccontextmanager
    async def write_guard(self) -> AsyncIterator[None]:
        """Serialize policy writes and purge across workers, including cache flushes.

        A renewable lease avoids abandoned locks on process failure. All supported
        application writers and the maintenance CLI enter this guard.
        """
        async with self._lock:
            if self.database is None:
                yield
                return
            token = uuid4().hex
            acquired = False
            for _ in range(50):
                now = utc_now()
                try:
                    row = await self.database.purge_locks.find_one_and_update(
                        {"_id": "foundation-write", "expires_at": {"$lte": now}},
                        {"$set": {"owner": token, "expires_at": now + timedelta(seconds=90)}},
                        upsert=True,
                        return_document=ReturnDocument.AFTER,
                    )
                    acquired = row is not None and row.get("owner") == token
                except DuplicateKeyError:
                    acquired = False
                if acquired:
                    break
                await anyio.sleep(0.2)
            if not acquired:
                raise RuntimeError("Another policy write is running; retry shortly")

            async def renew() -> None:
                while True:
                    await anyio.sleep(15)
                    result = await self.database.purge_locks.update_one(
                        {"_id": "foundation-write", "owner": token},
                        {"$set": {"expires_at": utc_now() + timedelta(seconds=90)}},
                    )
                    if not result.matched_count:
                        raise RuntimeError("Policy write lease lost")

            try:
                async with anyio.create_task_group() as group:
                    group.start_soon(renew)
                    try:
                        yield
                    finally:
                        group.cancel_scope.cancel()
            finally:
                with anyio.CancelScope(shield=True):
                    await self.database.purge_locks.delete_one(
                        {"_id": "foundation-write", "owner": token}
                    )
