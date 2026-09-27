from datetime import datetime
from typing import Annotated, cast

from fastapi import APIRouter, Query, Request

from apps.api.app.auth.dependencies import CurrentProfile
from apps.api.app.auth.permissions import require_system_admin
from apps.api.app.services.admin_audit_service import AdminAuditService

router = APIRouter(prefix="/admin/audit-events", tags=["system-admin-audit"])


@router.get("")
async def list_audit_events(
    request: Request,
    profile: CurrentProfile,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    actor_id: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
) -> dict[str, object]:
    require_system_admin(profile)
    service = cast(AdminAuditService, request.app.state.admin_audit_service)
    events, total = await service.list_events(
        profile.organization_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        skip=(page - 1) * limit,
        limit=limit,
    )
    return {
        "items": [event.model_dump(mode="json") for event in events],
        "total": total,
        "page": page,
        "limit": limit,
    }
