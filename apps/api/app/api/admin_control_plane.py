from typing import cast

from fastapi import APIRouter, HTTPException, Request

from apps.api.app.auth.dependencies import CurrentProfile
from apps.api.app.auth.permissions import require_system_admin
from apps.api.app.models.organization import ApplicationRole, CatalogKind
from apps.api.app.services.admin_audit_service import AdminAuditService
from apps.api.app.services.foundation_store import FoundationStore
from apps.api.app.services.organization_service import OrganizationService
from apps.api.app.services.user_admin_service import UserAdminService
from packages.contracts.access import AccessMode
from packages.contracts.policy import VersionStatus

router = APIRouter(prefix="/admin", tags=["system-admin-control-plane"])


@router.get("/overview")
async def overview(request: Request, profile: CurrentProfile) -> dict[str, object]:
    require_system_admin(profile)
    users = await cast(UserAdminService, request.app.state.user_admin_service).list_users(
        profile.organization_id, page=1, limit=100_000
    )
    organization = cast(OrganizationService, request.app.state.organization_service)
    store = cast(FoundationStore, request.app.state.foundation_store)
    events, _ = await cast(AdminAuditService, request.app.state.admin_audit_service).list_events(
        profile.organization_id, limit=8
    )
    active_users = [user for user in users.items if user.active]
    versions = [
        version
        for version in store.versions.values()
        if version.organization_id == profile.organization_id
    ]
    return {
        "users": {
            "active": len(active_users),
            "employees": sum(
                ApplicationRole.EMPLOYEE in user.application_roles for user in active_users
            ),
            "sop_administrators": sum(
                ApplicationRole.SOP_ADMIN in user.application_roles for user in active_users
            ),
            "system_administrators": sum(
                ApplicationRole.SYSTEM_ADMIN in user.application_roles for user in active_users
            ),
        },
        "catalogs": {
            kind.value: len(
                await organization.list_items(profile.organization_id, kind, include_inactive=False)
            )
            for kind in CatalogKind
        },
        "policies": {
            "published": sum(version.status is VersionStatus.PUBLISHED for version in versions),
            "review_required": sum(
                version.status in {VersionStatus.DRAFT, VersionStatus.EXTRACTION_REVIEW}
                for version in versions
            ),
            "failed_jobs": sum(
                job.organization_id == profile.organization_id and job.state.value == "failed"
                for job in store.jobs.values()
            ),
        },
        "recent_activity": [event.model_dump(mode="json") for event in events],
    }


@router.get("/access/users/{user_id}/policies/{policy_id}")
async def inspect_access(
    request: Request, user_id: str, policy_id: str, profile: CurrentProfile
) -> dict[str, object]:
    require_system_admin(profile)
    user = await cast(UserAdminService, request.app.state.user_admin_service).get_user(
        profile.organization_id, user_id
    )
    store = cast(FoundationStore, request.app.state.foundation_store)
    policy = store.policies.get(policy_id)
    if (
        not policy
        or policy.organization_id != profile.organization_id
        or not policy.active_version_id
    ):
        raise HTTPException(status_code=404, detail="Published policy not found")
    version = store.versions.get(policy.active_version_id)
    if not version or version.organization_id != profile.organization_id:
        raise HTTPException(status_code=404, detail="Published policy not found")
    dimensions = {
        "departments": (version.access.departments, user.departments),
        "locations": (version.access.locations, user.locations),
        "organizational_roles": (version.access.roles, user.organizational_roles),
    }
    checks = {
        name: {
            "policy_mode": dimension.mode.value,
            "policy_values": sorted(dimension.values),
            "user_values": sorted(values),
            "matched_values": sorted(dimension.values & values),
            "allowed": dimension.mode is AccessMode.ALL or bool(dimension.values & values),
        }
        for name, (dimension, values) in dimensions.items()
    }
    return {
        "user": {"id": user.id, "display_name": user.display_name, "email": user.email},
        "policy": {"id": policy.id, "title": policy.title, "policy_number": policy.policy_number},
        "dimensions": checks,
        "authorized": user.active and all(bool(check["allowed"]) for check in checks.values()),
    }
