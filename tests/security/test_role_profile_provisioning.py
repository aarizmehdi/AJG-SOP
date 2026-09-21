import pytest
from fastapi import HTTPException

from apps.api.app.auth.permissions import (
    can_manage_scope,
    require_admin,
    require_system_admin,
)
from apps.api.app.models.organization import ApplicationRole, EmployeeProfile
from packages.contracts.access import AccessDimension, AccessMode, AccessScope
from scripts.identity.provision_role_profiles import (
    VerifiedFirebaseUser,
    _documents_to_insert,
    build_profile,
    profile_document,
    role_profile_plans,
)

EMPLOYEE_UID = "employee-firebase-uid"
SOP_ADMIN_UID = "sop-admin-firebase-uid"


def profiles() -> tuple[EmployeeProfile, EmployeeProfile]:
    employee_plan, sop_admin_plan = role_profile_plans(EMPLOYEE_UID, SOP_ADMIN_UID)
    employee = build_profile(
        "ajt",
        employee_plan,
        VerifiedFirebaseUser(
            uid=EMPLOYEE_UID,
            email="employee@example.test",
            display_name="Employee",
            email_verified=True,
        ),
    )
    sop_admin = build_profile(
        "ajt",
        sop_admin_plan,
        VerifiedFirebaseUser(
            uid=SOP_ADMIN_UID,
            email="sop-admin@example.test",
            display_name="SOP Admin",
            email_verified=True,
        ),
    )
    return employee, sop_admin


def selected_scope(department: str, location: str, role: str) -> AccessScope:
    return AccessScope(
        departments=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({department})),
        locations=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({location})),
        roles=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({role})),
    )


def test_employee_has_no_admin_or_management_privileges() -> None:
    employee, _ = profiles()

    assert employee.application_roles == frozenset({ApplicationRole.EMPLOYEE})
    assert not employee.management_departments
    assert not employee.management_locations
    assert not employee.management_roles
    with pytest.raises(HTTPException) as admin_denied:
        require_admin(employee)
    assert admin_denied.value.status_code == 403
    with pytest.raises(HTTPException) as system_denied:
        require_system_admin(employee)
    assert system_denied.value.status_code == 403


def test_sop_admin_is_limited_to_assigned_management_scope() -> None:
    _, sop_admin = profiles()

    assert sop_admin.application_roles == frozenset(
        {ApplicationRole.EMPLOYEE, ApplicationRole.SOP_ADMIN}
    )
    require_admin(sop_admin)
    with pytest.raises(HTTPException) as system_denied:
        require_system_admin(sop_admin)
    assert system_denied.value.status_code == 403
    assert can_manage_scope(sop_admin, selected_scope("operations", "head-office", "employee"))
    assert not can_manage_scope(sop_admin, selected_scope("technology", "head-office", "employee"))
    assert not can_manage_scope(
        sop_admin, selected_scope("operations", "branch-office", "employee")
    )


def test_provisioning_plan_cannot_grant_system_admin() -> None:
    employee, sop_admin = profiles()

    assert ApplicationRole.SYSTEM_ADMIN not in employee.application_roles
    assert ApplicationRole.SYSTEM_ADMIN not in sop_admin.application_roles


def test_profile_requires_the_verified_uid_to_match() -> None:
    employee_plan, _ = role_profile_plans(EMPLOYEE_UID, SOP_ADMIN_UID)
    with pytest.raises(ValueError, match="does not match"):
        build_profile(
            "ajt",
            employee_plan,
            VerifiedFirebaseUser(
                uid="different-uid",
                email="employee@example.test",
                display_name=None,
                email_verified=False,
            ),
        )


def test_exact_existing_profile_is_idempotent_but_role_collision_is_rejected() -> None:
    employee, _ = profiles()
    intended = profile_document(employee)

    assert _documents_to_insert([intended.copy()], [intended]) == []
    escalated = {**intended, "application_roles": ["employee", "system_admin"]}
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        _documents_to_insert([escalated], [intended])


def test_separate_firebase_uids_are_required() -> None:
    with pytest.raises(ValueError, match="separate Firebase UIDs"):
        role_profile_plans(EMPLOYEE_UID, EMPLOYEE_UID)
