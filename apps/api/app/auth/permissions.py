from fastapi import HTTPException, status

from apps.api.app.models.organization import ApplicationRole, EmployeeProfile
from packages.contracts.access import AccessMode, AccessScope


def require_admin(profile: EmployeeProfile) -> None:
    if not {
        ApplicationRole.SOP_ADMIN,
        ApplicationRole.SYSTEM_ADMIN,
    } & set(profile.application_roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")


def can_manage_scope(profile: EmployeeProfile, access: AccessScope) -> bool:
    if ApplicationRole.SYSTEM_ADMIN in profile.application_roles:
        return True
    dimensions = (
        (access.departments, profile.management_departments),
        (access.locations, profile.management_locations),
        (access.roles, profile.management_roles),
    )
    return all(
        requested.mode is AccessMode.SELECTED and requested.values.issubset(assigned)
        for requested, assigned in dimensions
    )


def require_management_scope(profile: EmployeeProfile, access: AccessScope) -> None:
    if not can_manage_scope(profile, access):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requested access exceeds the administrator's assigned scope",
        )
