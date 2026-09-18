from datetime import date
from typing import cast

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from apps.api.app.auth.dependencies import CurrentProfile
from apps.api.app.auth.permissions import (
    can_manage_scope,
    require_admin,
    require_management_scope,
    require_system_admin,
)
from apps.api.app.services.foundation_store import FoundationStore
from apps.api.app.services.policy_service import PolicyService, PublicationError
from packages.contracts.access import AccessScope
from packages.contracts.canonical import CanonicalSOP
from packages.contracts.policy import DuplicateSectionGroup, SectionChange, SOPPolicy, SOPVersion
from packages.contracts.source import SourceDocument

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


class ReviewConfirmationRequest(BaseModel):
    confirmed: bool


def _service(request: Request) -> PolicyService:
    return cast(PolicyService, request.app.state.policy_service)


def _store(request: Request) -> FoundationStore:
    return cast(FoundationStore, request.app.state.foundation_store)


def _authorize_version(request: Request, profile: CurrentProfile, version_id: str) -> SOPVersion:
    version = _store(request).versions.get(version_id)
    if not version or version.organization_id != profile.organization_id:
        raise HTTPException(status_code=404, detail="Policy version not found")
    require_management_scope(profile, version.access)
    return version


def _authorize_complete_version(
    request: Request, profile: CurrentProfile, version_id: str
) -> SOPVersion:
    version = _authorize_version(request, profile, version_id)
    store = _store(request)
    for source_id in version.source_document_ids:
        canonical = store.canonicals.get(source_id)
        if canonical and (
            canonical.organization_id != profile.organization_id
            or canonical.policy_id != version.policy_id
            or canonical.version_id != version.id
            or any(not can_manage_scope(profile, section.access) for section in canonical.sections)
        ):
            raise HTTPException(status_code=403, detail="Version exceeds your management scope")
    return version


def _visible_canonicals(
    store: FoundationStore, version: SOPVersion, profile: CurrentProfile
) -> list[CanonicalSOP]:
    return [
        canonical.model_copy(
            update={
                "sections": [
                    section
                    for section in canonical.sections
                    if can_manage_scope(profile, section.access)
                ]
            }
        )
        for source_id in version.source_document_ids
        if (canonical := store.canonicals.get(source_id))
        and canonical.organization_id == profile.organization_id
        and canonical.policy_id == version.policy_id
        and canonical.version_id == version.id
    ]


def _source_summary(source: SourceDocument) -> dict[str, object]:
    return {
        "id": source.id,
        "file_name": source.file_name,
        "media_type": source.media_type,
        "source_format": source.source_format.value,
        "status": source.status.value,
        "created_at": source.created_at.isoformat(),
    }


def _version_sources(
    store: FoundationStore, version: SOPVersion, profile: CurrentProfile
) -> list[SourceDocument]:
    return [
        source
        for source_id in version.source_document_ids
        if (source := store.sources.get(source_id))
        and source.organization_id == profile.organization_id
        and source.policy_id == version.policy_id
        and source.version_id == version.id
    ]


def _page_count(canonicals: list[CanonicalSOP]) -> int | None:
    pages: list[int] = []
    for canonical in canonicals:
        for section in canonical.sections:
            page = section.source.page_end or section.source.page_start
            if page is not None:
                pages.append(page)
    return max(pages) if pages else None


@router.get("/policies")
async def list_policies(request: Request, profile: CurrentProfile) -> list[dict[str, object]]:
    require_admin(profile)
    store = _store(request)
    result: list[dict[str, object]] = []
    for policy in store.policies.values():
        if policy.organization_id != profile.organization_id:
            continue
        versions = [
            version
            for version in store.versions.values()
            if version.policy_id == policy.id
            and version.organization_id == profile.organization_id
            and can_manage_scope(profile, version.access)
        ]
        if not versions:
            continue
        selected = next(
            (version for version in versions if version.id == policy.active_version_id), None
        )
        selected = selected or max(versions, key=lambda version: version.created_at)
        canonicals = _visible_canonicals(store, selected, profile)
        sources = _version_sources(store, selected, profile)
        result.append(
            {
                **policy.model_dump(mode="json"),
                "versions": [version.model_dump(mode="json") for version in versions],
                "display_version_id": selected.id,
                "sources": [_source_summary(source) for source in sources],
                "section_count": sum(len(canonical.sections) for canonical in canonicals),
                "page_count": _page_count(canonicals),
            }
        )
    return result


@router.get("/policies/{policy_id}/viewer")
async def policy_viewer(
    request: Request, policy_id: str, profile: CurrentProfile, version_id: str | None = None
) -> dict[str, object]:
    require_admin(profile)
    store = _store(request)
    policy = store.policies.get(policy_id)
    if not policy or policy.organization_id != profile.organization_id:
        raise HTTPException(status_code=404, detail="Policy not found")
    versions = [
        version
        for version in store.versions.values()
        if version.organization_id == profile.organization_id
        and version.policy_id == policy_id
        and can_manage_scope(profile, version.access)
    ]
    if not versions:
        raise HTTPException(status_code=404, detail="Policy not found")
    selected = (
        next((version for version in versions if version.id == version_id), None)
        if version_id
        else next((version for version in versions if version.id == policy.active_version_id), None)
    )
    if version_id and not selected:
        raise HTTPException(status_code=404, detail="Policy version not found")
    selected = selected or max(versions, key=lambda version: version.created_at)
    canonicals = _visible_canonicals(store, selected, profile)
    sources = _version_sources(store, selected, profile)
    original_allowed = {
        source.id: canonical is None
        or (
            canonical.organization_id == profile.organization_id
            and canonical.version_id == selected.id
            and all(can_manage_scope(profile, section.access) for section in canonical.sections)
        )
        for source in sources
        for canonical in [store.canonicals.get(source.id)]
    }
    return {
        "policy": policy.model_dump(mode="json"),
        "version": selected.model_dump(mode="json"),
        "versions": [
            {
                **version.model_dump(mode="json"),
                "source_names": [
                    source.file_name for source in _version_sources(store, version, profile)
                ],
            }
            for version in sorted(versions, key=lambda item: item.created_at, reverse=True)
        ],
        "sources": [
            {**_source_summary(source), "original_allowed": original_allowed.get(source.id, False)}
            for source in sources
        ],
        "canonicals": [canonical.model_dump(mode="json") for canonical in canonicals],
        "section_count": sum(len(canonical.sections) for canonical in canonicals),
        "page_count": _page_count(canonicals),
    }


@router.post("/policies", status_code=status.HTTP_201_CREATED)
async def create_policy(
    request: Request, payload: CreatePolicyRequest, profile: CurrentProfile
) -> dict[str, object]:
    require_system_admin(profile)
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
    require_system_admin(profile)
    require_management_scope(profile, payload.access)
    _authorize_complete_version(request, profile, version_id)
    return _service(request).set_access(
        profile.organization_id, profile.id, version_id, payload.access
    )


@router.post("/sources/{source_id}/approve")
async def approve_structure(
    request: Request,
    source_id: str,
    payload: ReviewConfirmationRequest,
    profile: CurrentProfile,
) -> SOPVersion:
    require_admin(profile)
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="Review confirmation is required")
    source = _store(request).sources.get(source_id)
    if not source or source.organization_id != profile.organization_id:
        raise HTTPException(status_code=404, detail="Source not found")
    _authorize_complete_version(request, profile, source.version_id)
    try:
        return _service(request).approve_structure(profile.organization_id, profile.id, source_id)
    except (KeyError, PublicationError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/versions/{version_id}/prepare-publication")
async def prepare_publication(
    request: Request, version_id: str, profile: CurrentProfile
) -> SOPVersion:
    require_system_admin(profile)
    _authorize_complete_version(request, profile, version_id)
    try:
        return await _service(request).prepare_for_publication(
            profile.organization_id, profile.id, version_id
        )
    except (KeyError, PublicationError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/versions/{version_id}/publish")
async def publish_version(request: Request, version_id: str, profile: CurrentProfile) -> SOPVersion:
    require_system_admin(profile)
    _authorize_complete_version(request, profile, version_id)
    try:
        return _service(request).publish(profile.organization_id, profile.id, version_id)
    except (KeyError, PublicationError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/policies/{policy_id}/rollback/{version_id}")
async def rollback_version(
    request: Request, policy_id: str, version_id: str, profile: CurrentProfile
) -> SOPVersion:
    require_system_admin(profile)
    _authorize_complete_version(request, profile, version_id)
    policy = _store(request).policies.get(policy_id)
    if not policy or policy.organization_id != profile.organization_id:
        raise HTTPException(status_code=404, detail="Policy not found")
    if policy.active_version_id:
        _authorize_complete_version(request, profile, policy.active_version_id)
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
    _authorize_complete_version(request, profile, version_id)
    _authorize_complete_version(request, profile, against)
    try:
        return _service(request).diff(profile.organization_id, against, version_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Version not found") from error


@router.get("/versions/{version_id}/duplicates")
async def duplicate_sections(
    request: Request, version_id: str, profile: CurrentProfile
) -> list[DuplicateSectionGroup]:
    require_admin(profile)
    _authorize_complete_version(request, profile, version_id)
    return _service(request).duplicate_sections(profile.organization_id, version_id)


@router.post("/policies/{policy_id}/deactivate")
async def deactivate_policy(request: Request, policy_id: str, profile: CurrentProfile) -> SOPPolicy:
    require_system_admin(profile)
    policy = _store(request).policies.get(policy_id)
    if not policy or policy.organization_id != profile.organization_id:
        raise HTTPException(status_code=404, detail="Policy not found")
    if policy.active_version_id:
        _authorize_complete_version(request, profile, policy.active_version_id)
    return _service(request).deactivate(profile.organization_id, profile.id, policy_id)
