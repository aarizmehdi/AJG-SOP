from dataclasses import dataclass

import pytest
from fastapi import HTTPException

from apps.api.app.auth.identity import FIXTURE_PROFILES, FixtureIdentityDirectory
from apps.api.app.auth.permissions import require_system_admin
from apps.api.app.models.organization import ApplicationRole, CatalogKind
from apps.api.app.repositories.database import InMemoryCanonicalDatabase
from apps.api.app.services.admin_audit_service import AdminAuditService
from apps.api.app.services.identity_admin_service import (
    FixtureIdentityAdminService,
    IdentityAdminError,
    IdentityConflictError,
)
from apps.api.app.services.organization_service import (
    CatalogConflictError,
    CatalogReferenceError,
    OrganizationService,
)
from apps.api.app.services.user_admin_service import UserAdminService, UserConflictError
from packages.contracts.common import Language


@dataclass
class ControlPlane:
    database: InMemoryCanonicalDatabase
    directory: FixtureIdentityDirectory
    organization: OrganizationService
    users: UserAdminService


async def build_control_plane(
    database: InMemoryCanonicalDatabase | None = None,
) -> ControlPlane:
    database = database or InMemoryCanonicalDatabase()
    directory = FixtureIdentityDirectory()
    identities = FixtureIdentityAdminService(directory)
    audit = AdminAuditService(database)
    organization = OrganizationService(database, audit)
    users = UserAdminService(database, identities, organization, audit)
    admin = FIXTURE_PROFILES["fixture|system-admin"]
    await database.insert_one(
        "employee_profiles",
        "ajt",
        admin.model_dump(mode="json", exclude={"organization_id"}),
    )
    for kind, key, name in (
        (CatalogKind.DEPARTMENT, "store", "Store"),
        (CatalogKind.DEPARTMENT, "finance", "Finance"),
        (CatalogKind.DEPARTMENT, "technology", "Technology"),
        (CatalogKind.LOCATION, "mill-1", "Mill 1"),
        (CatalogKind.LOCATION, "head-office", "Head Office"),
        (CatalogKind.ORGANIZATIONAL_ROLE, "store_keeper", "Store Keeper"),
        (CatalogKind.ORGANIZATIONAL_ROLE, "manager", "Manager"),
        (CatalogKind.ORGANIZATIONAL_ROLE, "system_admin", "System Administrator"),
    ):
        await organization.create_item("ajt", admin.id, kind, key=key, name=name, description=None)
    return ControlPlane(database, directory, organization, users)


async def create_employee(control: ControlPlane, *, idempotency_key: str = "request-0001"):
    return await control.users.create_user(
        "ajt",
        "user-system-admin",
        display_name="Test Store Employee",
        email="store.employee@example.test",
        preferred_language=Language.ENGLISH,
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
        departments=frozenset({"store"}),
        locations=frozenset({"mill-1"}),
        organizational_roles=frozenset({"store_keeper"}),
        management_departments=frozenset(),
        management_locations=frozenset(),
        management_roles=frozenset(),
        idempotency_key=idempotency_key,
    )


@pytest.mark.asyncio
async def test_user_creation_is_idempotent_and_audited_without_secrets() -> None:
    control = await build_control_plane()

    first = await create_employee(control)
    repeated = await create_employee(control)

    assert first.profile.id == repeated.profile.id
    assert first.profile.identity_subject == repeated.profile.identity_subject
    created_identities = [
        identity
        for uid, identity in control.directory.identities.items()
        if uid.startswith("fixture|managed-")
    ]
    assert len(created_identities) == 1
    events = control.database.collections["audit_events"]
    assert any(event["action"] == "identity.user_created" for event in events)
    assert all("reset" not in str(event.get("metadata", {})).casefold() for event in events)


@pytest.mark.asyncio
async def test_duplicate_firebase_email_does_not_create_a_profile() -> None:
    control = await build_control_plane()
    control.directory.identities["fixture|external"] = {
        "uid": "fixture|external",
        "email": "store.employee@example.test",
        "display_name": "Existing Firebase Account",
        "disabled": False,
    }

    with pytest.raises(IdentityConflictError, match="already exists"):
        await create_employee(control)

    profiles = await control.database.find_many("employee_profiles", "ajt", {}, limit=100)
    assert all(profile["email"] != "store.employee@example.test" for profile in profiles)


@pytest.mark.asyncio
async def test_catalog_key_is_stable_and_referenced_item_cannot_be_deactivated() -> None:
    control = await build_control_plane()
    created = await create_employee(control)
    department = next(
        item
        for item in await control.organization.list_items("ajt", CatalogKind.DEPARTMENT)
        if item.key == "store"
    )

    renamed = await control.organization.update_item(
        "ajt",
        "user-system-admin",
        CatalogKind.DEPARTMENT,
        department.id,
        name="Central Store",
        description=None,
        active=None,
        expected_version=department.version,
    )

    assert renamed.key == "store"
    assert "store" in created.profile.departments
    with pytest.raises(CatalogConflictError, match="still referenced"):
        await control.organization.update_item(
            "ajt",
            "user-system-admin",
            CatalogKind.DEPARTMENT,
            department.id,
            name=None,
            description=None,
            active=False,
            expected_version=renamed.version,
        )


@pytest.mark.asyncio
async def test_existing_inactive_scope_is_readable_but_cannot_be_newly_assigned() -> None:
    control = await build_control_plane()
    created = await create_employee(control)
    finance = next(
        item
        for item in await control.organization.list_items("ajt", CatalogKind.DEPARTMENT)
        if item.key == "finance"
    )
    await control.organization.update_item(
        "ajt",
        "user-system-admin",
        CatalogKind.DEPARTMENT,
        finance.id,
        name=None,
        description=None,
        active=False,
        expected_version=finance.version,
        update_description=False,
    )

    updated = await control.users.update_user(
        "ajt",
        "user-system-admin",
        created.profile.id,
        display_name="Renamed Store Employee",
        email=created.profile.email,
        preferred_language=Language.ENGLISH,
        application_roles=created.profile.application_roles,
        departments=created.profile.departments,
        locations=created.profile.locations,
        organizational_roles=created.profile.organizational_roles,
        management_departments=created.profile.management_departments,
        management_locations=created.profile.management_locations,
        management_roles=created.profile.management_roles,
        expected_version=created.profile.version,
        confirm_self_role_change=False,
    )

    assert updated.departments == frozenset({"store"})
    with pytest.raises(CatalogReferenceError, match="Inactive department"):
        await control.users.update_user(
            "ajt",
            "user-system-admin",
            updated.id,
            display_name=updated.display_name,
            email=updated.email,
            preferred_language=Language.ENGLISH,
            application_roles=updated.application_roles,
            departments=frozenset({"store", "finance"}),
            locations=updated.locations,
            organizational_roles=updated.organizational_roles,
            management_departments=updated.management_departments,
            management_locations=updated.management_locations,
            management_roles=updated.management_roles,
            expected_version=updated.version,
            confirm_self_role_change=False,
        )


@pytest.mark.asyncio
async def test_last_system_administrator_cannot_be_disabled_or_demoted() -> None:
    control = await build_control_plane()
    admin = FIXTURE_PROFILES["fixture|system-admin"]

    with pytest.raises(UserConflictError, match="last active System Administrator"):
        await control.users.disable_user("ajt", admin.id, admin.id, confirmation_email=admin.email)

    with pytest.raises(UserConflictError, match="last active System Administrator"):
        await control.users.update_user(
            "ajt",
            admin.id,
            admin.id,
            display_name=admin.display_name,
            email=admin.email,
            preferred_language=Language.ENGLISH,
            application_roles=frozenset({ApplicationRole.EMPLOYEE}),
            departments=admin.departments,
            locations=admin.locations,
            organizational_roles=admin.organizational_roles,
            management_departments=frozenset(),
            management_locations=frozenset(),
            management_roles=frozenset(),
            expected_version=admin.version,
            confirm_self_role_change=True,
        )


@pytest.mark.asyncio
async def test_cross_tenant_user_lookup_and_privilege_escalation_are_rejected() -> None:
    control = await build_control_plane()
    created = await create_employee(control)

    with pytest.raises(KeyError):
        await control.users.get_user("another-organization", created.profile.id)

    employee = created.profile
    with pytest.raises(HTTPException) as denied:
        require_system_admin(employee)
    assert denied.value.status_code == 403


class FailingProfileDatabase(InMemoryCanonicalDatabase):
    async def insert_one(self, collection, organization_id, document):  # type: ignore[no-untyped-def]
        if collection == "employee_profiles":
            raise RuntimeError("simulated Mongo failure")
        return await super().insert_one(collection, organization_id, document)


@pytest.mark.asyncio
async def test_firebase_identity_is_compensated_when_profile_creation_fails() -> None:
    database = FailingProfileDatabase()
    directory = FixtureIdentityDirectory()
    identities = FixtureIdentityAdminService(directory)
    audit = AdminAuditService(database)
    organization = OrganizationService(database, audit)
    users = UserAdminService(database, identities, organization, audit)
    for kind, key in (
        (CatalogKind.DEPARTMENT, "store"),
        (CatalogKind.LOCATION, "mill-1"),
        (CatalogKind.ORGANIZATIONAL_ROLE, "store_keeper"),
    ):
        await organization.create_item("ajt", "admin", kind, key=key, name=key, description=None)
    before = set(directory.identities)

    with pytest.raises(UserConflictError, match="consistently"):
        await users.create_user(
            "ajt",
            "admin",
            display_name="Failure Test",
            email="failure@example.test",
            preferred_language=Language.ENGLISH,
            application_roles=frozenset({ApplicationRole.EMPLOYEE}),
            departments=frozenset({"store"}),
            locations=frozenset({"mill-1"}),
            organizational_roles=frozenset({"store_keeper"}),
            management_departments=frozenset(),
            management_locations=frozenset(),
            management_roles=frozenset(),
            idempotency_key="failure-case-1",
        )

    assert set(directory.identities) == before


class FailOnceProfileDatabase(InMemoryCanonicalDatabase):
    def __init__(self) -> None:
        super().__init__()
        self.should_fail = False

    async def insert_one(self, collection, organization_id, document):  # type: ignore[no-untyped-def]
        if collection == "employee_profiles" and self.should_fail:
            self.should_fail = False
            raise RuntimeError("simulated one-time Mongo failure")
        return await super().insert_one(collection, organization_id, document)


@pytest.mark.asyncio
async def test_create_retry_after_compensated_mongo_failure_succeeds() -> None:
    database = FailOnceProfileDatabase()
    control = await build_control_plane(database)
    database.should_fail = True

    with pytest.raises(UserConflictError, match="consistently"):
        await create_employee(control)
    created = await create_employee(control)

    assert created.profile.email == "store.employee@example.test"
    idempotency = await database.find_many("admin_idempotency", "ajt", {}, limit=100)
    assert len(idempotency) == 1


class FailingMembershipUpdateDatabase(InMemoryCanonicalDatabase):
    def __init__(self) -> None:
        super().__init__()
        self.fail_updates = False

    async def update_one(  # type: ignore[no-untyped-def]
        self, collection, organization_id, query, updates
    ):
        if collection == "employee_profiles" and self.fail_updates:
            return False
        return await super().update_one(collection, organization_id, query, updates)


@pytest.mark.asyncio
async def test_mongo_disable_failure_reenables_firebase_identity() -> None:
    database = FailingMembershipUpdateDatabase()
    control = await build_control_plane(database)
    created = await create_employee(control)
    database.fail_updates = True

    with pytest.raises(UserConflictError, match="changed since"):
        await control.users.disable_user(
            "ajt", "user-system-admin", created.profile.id, confirmation_email=""
        )

    identity = control.directory.identities[created.profile.identity_subject]
    assert identity["disabled"] is False


class FailingDisableIdentityService(FixtureIdentityAdminService):
    async def disable_identity(self, uid):  # type: ignore[no-untyped-def]
        raise IdentityAdminError("simulated Firebase failure")


@pytest.mark.asyncio
async def test_firebase_disable_failure_leaves_membership_active() -> None:
    control = await build_control_plane()
    created = await create_employee(control)
    users = UserAdminService(
        control.database,
        FailingDisableIdentityService(control.directory),
        control.organization,
        AdminAuditService(control.database),
    )

    with pytest.raises(IdentityAdminError, match="Firebase failure"):
        await users.disable_user(
            "ajt", "user-system-admin", created.profile.id, confirmation_email=""
        )

    stored = await control.database.get_one("employee_profiles", "ajt", {"id": created.profile.id})
    assert stored is not None and stored["active"] is True
