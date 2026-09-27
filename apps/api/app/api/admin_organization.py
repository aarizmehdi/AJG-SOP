from typing import Annotated, cast

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from apps.api.app.auth.dependencies import CurrentProfile
from apps.api.app.auth.permissions import require_system_admin
from apps.api.app.models.organization import CatalogKind, OrganizationCatalogItem
from apps.api.app.services.organization_service import (
    CatalogConflictError,
    CatalogReferenceError,
    OrganizationService,
)

router = APIRouter(prefix="/admin", tags=["system-admin-organization"])


class CreateCatalogItemRequest(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class UpdateCatalogItemRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    active: bool | None = None
    expected_version: int = Field(ge=1)


def _service(request: Request) -> OrganizationService:
    return cast(OrganizationService, request.app.state.organization_service)


def _kind(value: str) -> CatalogKind:
    try:
        return CatalogKind(value)
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Organization catalog not found") from error


@router.get("/organization")
async def organization_summary(request: Request, profile: CurrentProfile) -> dict[str, object]:
    require_system_admin(profile)
    database = request.app.state.database
    return {
        "organization_id": profile.organization_id,
        "name": "Aziz Jan Trust" if profile.organization_id == "ajt" else profile.organization_id,
        "catalog_counts": {
            kind.value: await database.count_documents(
                kind.value, profile.organization_id, {"active": True}
            )
            for kind in CatalogKind
        },
    }


@router.get("/{catalog_kind}")
async def list_catalog(
    request: Request,
    catalog_kind: str,
    profile: CurrentProfile,
    include_inactive: Annotated[bool, Query()] = True,
) -> list[dict[str, object]]:
    require_system_admin(profile)
    kind = _kind(catalog_kind)
    service = _service(request)
    items = await service.list_items(
        profile.organization_id, kind, include_inactive=include_inactive
    )
    result: list[dict[str, object]] = []
    for item in items:
        usage = await service.usage(profile.organization_id, kind, item.key)
        result.append(
            {
                **item.model_dump(mode="json"),
                "usage": {
                    "active_users": usage.active_users,
                    "policies": usage.policies,
                    "sop_administrators": usage.sop_administrators,
                    "total": usage.total,
                },
            }
        )
    return result


@router.post("/{catalog_kind}", status_code=status.HTTP_201_CREATED)
async def create_catalog_item(
    request: Request,
    catalog_kind: str,
    payload: CreateCatalogItemRequest,
    profile: CurrentProfile,
) -> OrganizationCatalogItem:
    require_system_admin(profile)
    try:
        return await _service(request).create_item(
            profile.organization_id,
            profile.id,
            _kind(catalog_kind),
            key=payload.key,
            name=payload.name,
            description=payload.description,
        )
    except (CatalogConflictError, CatalogReferenceError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.patch("/{catalog_kind}/{item_id}")
async def update_catalog_item(
    request: Request,
    catalog_kind: str,
    item_id: str,
    payload: UpdateCatalogItemRequest,
    profile: CurrentProfile,
) -> OrganizationCatalogItem:
    require_system_admin(profile)
    try:
        return await _service(request).update_item(
            profile.organization_id,
            profile.id,
            _kind(catalog_kind),
            item_id,
            name=payload.name,
            description=payload.description,
            active=payload.active,
            expected_version=payload.expected_version,
            update_description="description" in payload.model_fields_set,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Catalog item not found") from error
    except (CatalogConflictError, CatalogReferenceError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/organization/bootstrap-report")
async def catalog_bootstrap_report(request: Request, profile: CurrentProfile) -> dict[str, object]:
    require_system_admin(profile)
    return await _service(request).bootstrap_from_existing_profiles(profile.organization_id)
