from datetime import datetime
from uuid import uuid4

from pydantic import JsonValue

from apps.api.app.repositories.database import CanonicalDatabase
from packages.contracts.policy import AuditEvent


class AdminAuditService:
    """Durable, tenant-scoped audit writer for control-plane mutations."""

    def __init__(self, database: CanonicalDatabase) -> None:
        self._database = database

    async def record(
        self,
        organization_id: str,
        actor_id: str,
        action: str,
        entity_type: str,
        entity_id: str,
        metadata: dict[str, JsonValue] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            id=f"audit-{uuid4().hex[:12]}",
            organization_id=organization_id,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=metadata or {},
        )
        await self._database.insert_one(
            "audit_events",
            organization_id,
            event.model_dump(mode="json", exclude={"organization_id"}),
        )
        return event

    async def list_events(
        self,
        organization_id: str,
        *,
        actor_id: str | None = None,
        action: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[AuditEvent], int]:
        query: dict[str, object] = {}
        if actor_id:
            query["actor_id"] = actor_id
        if action:
            query["action"] = action
        if entity_type:
            query["entity_type"] = entity_type
        if entity_id:
            query["entity_id"] = entity_id
        records = await self._database.find_many(
            "audit_events",
            organization_id,
            query,
            sort=(("occurred_at", -1),),
            skip=0,
            limit=10_000,
        )
        events = [AuditEvent.model_validate(record) for record in records]
        if occurred_from:
            events = [event for event in events if event.occurred_at >= occurred_from]
        if occurred_to:
            events = [event for event in events if event.occurred_at <= occurred_to]
        return events[skip : skip + limit], len(events)
