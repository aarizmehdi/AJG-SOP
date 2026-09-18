from typing import cast

from fastapi import APIRouter, Request

from apps.api.app.auth.dependencies import CurrentProfile
from apps.api.app.auth.permissions import require_system_admin
from apps.api.app.services.metrics import MetricsRegistry
from services.retrieval.retriever import RetrievalService

router = APIRouter(prefix="/admin/operations", tags=["operations"])


@router.get("/metrics")
async def metrics(request: Request, profile: CurrentProfile) -> dict[str, object]:
    require_system_admin(profile)
    registry = cast(MetricsRegistry, request.app.state.metrics)
    return {"organization_id": profile.organization_id, "metrics": registry.snapshot()}


@router.get("/retrieval-telemetry")
async def retrieval_telemetry(
    request: Request, profile: CurrentProfile
) -> dict[str, object]:
    require_system_admin(profile)
    retrieval = cast(RetrievalService, request.app.state.retrieval_service)
    return {
        "organization_id": profile.organization_id,
        "traces": retrieval.telemetry(profile.organization_id),
    }
