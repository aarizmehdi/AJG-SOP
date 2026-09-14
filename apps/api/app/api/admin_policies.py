from datetime import date
from typing import cast

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from apps.api.app.auth.dependencies import CurrentProfile
from apps.api.app.auth.permissions import can_manage_scope, require_admin, require_management_scope
from apps.api.app.services.foundation_store import FoundationStore
from apps.api.app.services.policy_service import PolicyService, PublicationError
from packages.contracts.access import AccessScope
from packages.contracts.policy import DuplicateSectionGroup, SectionChange, SOPPolicy, SOPVersion

router = APIRouter(prefix="/admin", tags=["admin-policies"])


class CreatePolicyRequest(BaseModel):
    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    policy_number: str | None = None
    version_label: str = Field(min_length=1)
    effective_date: date | None = None
    access: AccessScope


class AccessUpdateRequest(BaseModel):
    access: AccessScope


def _service(request: Request) -> PolicyService:
    return cast(PolicyService, request.app.state.policy_service)


def _store(request: Request) -> FoundationStore:
    return cast(FoundationStore, request.app.state.foundation_store)


def _authorize_version(
    request: Request, profile: CurrentProfile, version_id: str
) -> SOPVersion:
    version = _store(request).versions.get(version_id)
    if not version or version.organization_id != profile.organization_id:
        raise HTTPException(status_code=404, detail="Policy version not found")
    require_management_scope(profile, version.access)
    return version


@router.get("/policies")
async def list_policies(request: Request, profile: CurrentProfile) -> list[dict[str, object]]:
    require_admin(profile)
    store = _store(request)
    return [
        {
            **policy.model_dump(mode="json"),
            "versions": [
                version.model_dump(mode="json")
                for version in store.versions.values()
                if version.policy_id == policy.id
                and version.organization_id == profile.organization_id
                and can_manage_scope(profile, version.access)
            ],
        }
        for policy in store.policies.values()
        if policy.organization_id == profile.organization_id
        and any(
            version.policy_id == policy.id and can_manage_scope(profile, version.access)
            for version in store.versions.values()
        )
    ]


@router.post("/policies", status_code=status.HTTP_201_CREATED)
async def create_policy(
    request: Request, payload: CreatePolicyRequest, profile: CurrentProfile
) -> dict[str, object]:
    require_admin(profile)
    require_management_scope(profile, payload.access)
    service = _service(request)
    policy = service.create_policy(
        profile.organization_id,
        profile.id,
        payload.title,
        payload.category,
        payload.policy_number,
    )
    version = service.create_version(
        profile.organization_id,
        profile.id,
        policy.id,
        payload.version_label,
        payload.access,
        payload.effective_date,
    )
    return {"policy": policy.model_dump(mode="json"), "version": version.model_dump(mode="json")}


@router.put("/versions/{version_id}/access")
async def update_access(
    request: Request,
    version_id: str,
    payload: AccessUpdateRequest,
    profile: CurrentProfile,
) -> SOPVersion:
    require_admin(profile)
    require_management_scope(profile, payload.access)
    return _service(request).set_access(
        profile.organization_id, profile.id, version_id, payload.access
    )


@router.post("/sources/{source_id}/approve")
async def approve_structure(
    request: Request, source_id: str, profile: CurrentProfile
) -> SOPVersion:
    require_admin(profile)
    source = _store(request).sources.get(source_id)
    if not source or source.organization_id != profile.organization_id:
        raise HTTPException(status_code=404, detail="Source not found")
    _authorize_version(request, profile, source.version_id)
    try:
        return _service(request).approve_structure(profile.organization_id, profile.id, source_id)
    except (KeyError, PublicationError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/versions/{version_id}/prepare-publication")
async def prepare_publication(
    request: Request, version_id: str, profile: CurrentProfile
) -> SOPVersion:
    require_admin(profile)
    _authorize_version(request, profile, version_id)
    try:
        return await _service(request).prepare_for_publication(
            profile.organization_id, profile.id, version_id
        )
    except (KeyError, PublicationError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/versions/{version_id}/publish")
async def publish_version(
    request: Request, version_id: str, profile: CurrentProfile
) -> SOPVersion:
    require_admin(profile)
    _authorize_version(request, profile, version_id)
    try:
        return _service(request).publish(profile.organization_id, profile.id, version_id)
    except (KeyError, PublicationError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/policies/{policy_id}/rollback/{version_id}")
async def rollback_version(
    request: Request, policy_id: str, version_id: str, profile: CurrentProfile
) -> SOPVersion:
    require_admin(profile)
    _authorize_version(request, profile, version_id)
    try:
        return _service(request).rollback(
            profile.organization_id, profile.id, policy_id, version_id
        )
    except (KeyError, PublicationError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/versions/{version_id}/diff")
async def version_diff(
    request: Request,
    version_id: str,
    profile: CurrentProfile,
    against: str = Query(min_length=1),
) -> list[SectionChange]:
    require_admin(profile)
    _authorize_version(request, profile, version_id)
    _authorize_version(request, profile, against)
    try:
        return _service(request).diff(profile.organization_id, against, version_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Version not found") from error


@router.get("/versions/{version_id}/duplicates")
async def duplicate_sections(
    request: Request, version_id: str, profile: CurrentProfile
) -> list[DuplicateSectionGroup]:
    require_admin(profile)
    _authorize_version(request, profile, version_id)
    return _service(request).duplicate_sections(profile.organization_id, version_id)


@router.post("/policies/{policy_id}/deactivate")
async def deactivate_policy(
    request: Request, policy_id: str, profile: CurrentProfile
) -> SOPPolicy:
    require_admin(profile)
    policy = _store(request).policies.get(policy_id)
    if not policy or policy.organization_id != profile.organization_id:
        raise HTTPException(status_code=404, detail="Policy not found")
    if policy.active_version_id:
        _authorize_version(request, profile, policy.active_version_id)
    return _service(request).deactivate(profile.organization_id, profile.id, policy_id)
