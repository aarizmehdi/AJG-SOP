from typing import cast

from fastapi import APIRouter, Request

from apps.api.app.auth.dependencies import CurrentProfile
from apps.api.app.services.policy_purge_service import PolicyPurgeService
from packages.contracts.purge import PurgeConfirmation, PurgePreview, PurgeResult

router = APIRouter(prefix="/admin/policies", tags=["policy-purge"])


@router.get("/{policy_id}/purge-preview", response_model=PurgePreview)
async def preview(policy_id: str, request: Request, profile: CurrentProfile) -> PurgePreview:
    service = cast(PolicyPurgeService, request.app.state.policy_purge_service)
    return await service.preview(profile, policy_id)


@router.post("/{policy_id}/purge", response_model=PurgeResult)
async def purge(
    policy_id: str, confirmation: PurgeConfirmation, request: Request, profile: CurrentProfile
) -> PurgeResult:
    service = cast(PolicyPurgeService, request.app.state.policy_purge_service)
    return await service.purge(profile, policy_id, confirmation)
