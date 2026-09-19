from collections.abc import Callable, Coroutine
from typing import Annotated, Any, cast

from fastapi import Depends, Header, HTTPException, Request, status

from apps.api.app.auth.identity import FIXTURE_PROFILES, AuthenticatedIdentity, IdentityProvider
from apps.api.app.models.organization import ApplicationRole, EmployeeProfile


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
    else:
        if identity.subject.startswith("fixture|"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Fixture identity prohibited in live mode",
            )
        stored = await request.app.state.database.resolve_identity_profile(
            identity.subject,
            identity.external_organization_id,
        )
        profile = EmployeeProfile.model_validate(stored) if stored else None
    if not profile or not profile.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No active membership")
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
