from collections.abc import Callable, Coroutine
from typing import Annotated, Any, cast

from fastapi import Depends, Header, HTTPException, Request, status

from apps.api.app.auth.identity import FIXTURE_PROFILES, AuthenticatedIdentity, IdentityProvider
from apps.api.app.models.organization import (
    ApplicationRole,
    EmployeeProfile,
    MembershipStatus,
)
from packages.contracts.common import utc_now


async def current_identity(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> AuthenticatedIdentity:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    try:
        provider = cast(IdentityProvider, request.app.state.identity_provider)
        return await provider.authenticate(authorization)
    except (ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication"
        ) from None


async def current_profile(
    request: Request,
    identity: Annotated[AuthenticatedIdentity, Depends(current_identity)],
) -> EmployeeProfile:
    if request.app.state.settings.app_mode == "fixture":
        profile = FIXTURE_PROFILES.get(identity.subject)
        if not profile:
            stored = await request.app.state.database.resolve_identity_profile(identity.subject)
            profile = EmployeeProfile.model_validate(stored) if stored else None
    else:
        if identity.subject.startswith("fixture|"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Fixture identity prohibited in live mode",
            )
        stored = await request.app.state.database.resolve_identity_profile(identity.subject)
        profile = EmployeeProfile.model_validate(stored) if stored else None
    if not profile or not profile.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No active membership")
    if profile.status is MembershipStatus.PENDING_ACTIVATION:
        activated = profile.model_copy(
            update={
                "status": MembershipStatus.ACTIVE,
                "version": profile.version + 1,
                "updated_at": utc_now(),
            }
        )
        changed = await request.app.state.database.update_one(
            "employee_profiles",
            profile.organization_id,
            {"id": profile.id, "version": profile.version},
            {
                "status": MembershipStatus.ACTIVE.value,
                "version": activated.version,
                "updated_at": activated.updated_at.isoformat(),
            },
        )
        if changed:
            profile = activated
            audit = getattr(request.app.state, "admin_audit_service", None)
            if audit is not None:
                await audit.record(
                    profile.organization_id,
                    profile.id,
                    "identity.user_activated",
                    "employee_profile",
                    profile.id,
                )
        else:
            stored = await request.app.state.database.get_one(
                "employee_profiles", profile.organization_id, {"id": profile.id}
            )
            profile = EmployeeProfile.model_validate(stored) if stored else None
            if not profile or not profile.active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No active membership",
                )
            if profile.status is MembershipStatus.PENDING_ACTIVATION:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Account activation changed concurrently. Retry sign-in",
                )
    request.state.organization_id = profile.organization_id
    return profile


def require_roles(
    *roles: ApplicationRole,
) -> Callable[[EmployeeProfile], Coroutine[Any, Any, EmployeeProfile]]:
    async def dependency(
        profile: Annotated[EmployeeProfile, Depends(current_profile)],
    ) -> EmployeeProfile:
        if not set(roles) & set(profile.application_roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return profile

    return dependency


CurrentProfile = Annotated[EmployeeProfile, Depends(current_profile)]
