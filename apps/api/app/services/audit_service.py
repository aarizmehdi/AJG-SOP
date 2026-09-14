from uuid import uuid4

from apps.api.app.services.foundation_store import FoundationStore
from packages.contracts.policy import AuditEvent


class AuditService:
    def __init__(self, store: FoundationStore) -> None:
        self._store = store

    def record(
        self,
        organization_id: str,
        actor_id: str,
        action: str,
        entity_type: str,
        entity_id: str,
        metadata: dict[str, str] | None = None,
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
        self._store.audit_events.append(event)
        return event
