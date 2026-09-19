import pytest
from pydantic import ValidationError

from apps.api.app.auth.permissions import can_manage_scope
from apps.api.app.models.organization import ApplicationRole, EmployeeProfile
from packages.contracts.access import (
    AccessDimension,
    AccessMode,
    AccessScope,
    EmployeeScope,
)


def test_access_is_or_within_and_and_across_dimensions() -> None:
    rule = AccessScope(
        departments=AccessDimension(
            mode=AccessMode.SELECTED, values=frozenset({"store", "operations"})
        ),
        locations=AccessDimension(
            mode=AccessMode.SELECTED, values=frozenset({"peshawar-main", "islamabad"})
        ),
        roles=AccessDimension(
            mode=AccessMode.SELECTED, values=frozenset({"store_keeper", "manager"})
        ),
    )
    allowed = EmployeeScope(
        organization_id="ajt",
        departments=frozenset({"store"}),
        locations=frozenset({"peshawar-main"}),
        organizational_roles=frozenset({"store_keeper"}),
    )
    wrong_location = allowed.model_copy(update={"locations": frozenset({"quetta"})})

    assert rule.allows(allowed)
    assert not rule.allows(wrong_location)


def test_empty_selected_scope_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AccessDimension(mode=AccessMode.SELECTED)


def test_all_scope_must_be_explicit_and_cannot_carry_values() -> None:
    assert AccessDimension(mode=AccessMode.ALL).allows(frozenset())
    with pytest.raises(ValidationError):
        AccessDimension(mode=AccessMode.ALL, values=frozenset({"store"}))


def test_sop_admin_management_scope_must_contain_every_dimension() -> None:
    profile = EmployeeProfile(
        id="admin",
        organization_id="ajt",
        identity_subject="fixture|admin",
        display_name="Admin",
        email="admin@example.test",
        application_roles=frozenset({ApplicationRole.SOP_ADMIN}),
        management_departments=frozenset({"store"}),
        management_locations=frozenset({"peshawar"}),
        management_roles=frozenset({"owner"}),
    )
    allowed = AccessScope(
        departments=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"store"})),
        locations=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"peshawar"})),
        roles=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"owner"})),
    )
    outside = allowed.model_copy(
        update={
            "departments": AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"finance"}))
        }
    )

    assert can_manage_scope(profile, allowed)
    assert not can_manage_scope(profile, outside)
