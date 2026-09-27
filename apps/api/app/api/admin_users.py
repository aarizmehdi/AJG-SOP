from typing import Annotated, cast

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from apps.api.app.auth.dependencies import CurrentProfile
from apps.api.app.auth.permissions import require_system_admin
from apps.api.app.models.organization import ApplicationRole, MembershipStatus
from apps.api.app.services.identity_admin_service import (
    IdentityAdminError,
    IdentityAdminService,
    IdentityConflictError,
)
from apps.api.app.services.organization_service import CatalogReferenceError
from apps.api.app.services.user_admin_service import (
    UserAdminError,
    UserAdminService,
    UserConflictError,
)
from packages.contracts.common import Language

router = APIRouter(prefix="/admin/users", tags=["system-admin-users"])


class UserMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=160)
    email: str = Field(min_length=3, max_length=320)
    preferred_language: Language = Language.ENGLISH
    application_roles: frozenset[ApplicationRole]
    departments: frozenset[str] = Field(min_length=1)
    locations: frozenset[str] = Field(min_length=1)
    organizational_roles: frozenset[str] = Field(min_length=1)
    management_departments: frozenset[str] = Field(default_factory=frozenset)
    management_locations: frozenset[str] = Field(default_factory=frozenset)
    management_roles: frozenset[str] = Field(default_factory=frozenset)


class UpdateUserRequest(UserMutationRequest):
    expected_version: int = Field(ge=1)
    confirm_self_role_change: bool = False


class DisableUserRequest(BaseModel):
    confirmation_email: str = ""


def _service(request: Request) -> UserAdminService:
    return cast(UserAdminService, request.app.state.user_admin_service)


def _identities(request: Request) -> IdentityAdminService:
    return cast(IdentityAdminService, request.app.state.identity_admin_service)


def _error(error: Exception) -> HTTPException:
    if isinstance(error, (UserConflictError, IdentityConflictError)):
        return HTTPException(status_code=409, detail=str(error))
    if isinstance(error, (UserAdminError, CatalogReferenceError)):
        return HTTPException(status_code=422, detail=str(error))
    return HTTPException(status_code=502, detail=str(error))


@router.get("")
async def list_users(
    request: Request,
    profile: CurrentProfile,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    search: str | None = None,
    user_status: Annotated[MembershipStatus | None, Query(alias="status")] = None,
    application_role: ApplicationRole | None = None,
    department: str | None = None,
    location: str | None = None,
    organizational_role: str | None = None,
) -> dict[str, object]:
    require_system_admin(profile)
    page_result = await _service(request).list_users(
        profile.organization_id,
        page=page,
        limit=limit,
        search=search,
        status=user_status,
        application_role=application_role,
        department=department,
        location=location,
        organizational_role=organizational_role,
    )
    return {
        "items": [item.model_dump(mode="json") for item in page_result.items],
        "total": page_result.total,
        "page": page_result.page,
        "limit": page_result.limit,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(
    request: Request,
    payload: UserMutationRequest,
    profile: CurrentProfile,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8)],
) -> dict[str, object]:
    require_system_admin(profile)
    try:
        created = await _service(request).create_user(
            profile.organization_id,
            profile.id,
            **payload.model_dump(),
            idempotency_key=idempotency_key,
        )
        return {
            "user": created.profile.model_dump(mode="json"),
            "activation_link": created.activation_link,
        }
    except (UserAdminError, CatalogReferenceError, IdentityAdminError) as error:
        raise _error(error) from error


@router.get("/{user_id}")
async def get_user(request: Request, user_id: str, profile: CurrentProfile) -> dict[str, object]:
    require_system_admin(profile)
    try:
        user = await _service(request).get_user(profile.organization_id, user_id)
        identity = await _identities(request).get_identity(user.identity_subject)
        return {**user.model_dump(mode="json"), "identity_linked": identity is not None}
    except KeyError as error:
        raise HTTPException(status_code=404, detail="User not found") from error
    except IdentityAdminError as error:
        raise _error(error) from error


@router.patch("/{user_id}")
async def update_user(
    request: Request,
    user_id: str,
    payload: UpdateUserRequest,
    profile: CurrentProfile,
) -> object:
    require_system_admin(profile)
    try:
        return await _service(request).update_user(
            profile.organization_id, profile.id, user_id, **payload.model_dump()
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="User not found") from error
    except (UserAdminError, CatalogReferenceError, IdentityAdminError) as error:
        raise _error(error) from error


@router.post("/{user_id}/disable")
async def disable_user(
    request: Request,
    user_id: str,
    payload: DisableUserRequest,
    profile: CurrentProfile,
) -> object:
    require_system_admin(profile)
    try:
        return await _service(request).disable_user(
            profile.organization_id,
            profile.id,
            user_id,
            confirmation_email=payload.confirmation_email,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="User not found") from error
    except (UserAdminError, IdentityAdminError) as error:
        raise _error(error) from error


@router.post("/{user_id}/reactivate")
async def reactivate_user(request: Request, user_id: str, profile: CurrentProfile) -> object:
    require_system_admin(profile)
    try:
        return await _service(request).reactivate_user(profile.organization_id, profile.id, user_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="User not found") from error
    except (UserAdminError, CatalogReferenceError, IdentityAdminError) as error:
        raise _error(error) from error


@router.post("/{user_id}/password-reset")
async def reset_password(request: Request, user_id: str, profile: CurrentProfile) -> dict[str, str]:
    require_system_admin(profile)
    try:
        link = await _service(request).generate_password_reset(
            profile.organization_id, profile.id, user_id
        )
        return {"message": "Password reset initiated", "reset_link": link}
    except KeyError as error:
        raise HTTPException(status_code=404, detail="User not found") from error
    except IdentityAdminError as error:
        raise _error(error) from error
