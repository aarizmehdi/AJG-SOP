from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast
from uuid import uuid4

from pydantic import JsonValue

from apps.api.app.models.organization import (
    ApplicationRole,
    CatalogKind,
    EmployeeProfile,
    MembershipStatus,
)
from apps.api.app.repositories.database import CanonicalDatabase
from apps.api.app.services.admin_audit_service import AdminAuditService
from apps.api.app.services.identity_admin_service import (
    IdentityAdminError,
    IdentityAdminService,
)
from apps.api.app.services.organization_service import OrganizationService
from packages.contracts.common import Language, utc_now


class UserAdminError(ValueError):
    pass


class UserConflictError(UserAdminError):
    pass


@dataclass(frozen=True)
class UserPage:
    items: list[EmployeeProfile]
    total: int
    page: int
    limit: int


@dataclass(frozen=True)
class CreatedUser:
    profile: EmployeeProfile
    activation_link: str


class UserAdminService:
    def __init__(
        self,
        database: CanonicalDatabase,
        identities: IdentityAdminService,
        organization: OrganizationService,
        audit: AdminAuditService,
    ) -> None:
        self._database = database
        self._identities = identities
        self._organization = organization
        self._audit = audit

    @staticmethod
    def _normalize_email(value: str) -> str:
        normalized = value.strip().casefold()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise UserAdminError("Enter a valid email address")
        return normalized

    @staticmethod
    def _validate_roles(roles: frozenset[ApplicationRole]) -> None:
        if ApplicationRole.EMPLOYEE not in roles:
            raise UserAdminError("Every application role set must include employee")
        if ApplicationRole.SYSTEM_ADMIN in roles and ApplicationRole.SOP_ADMIN not in roles:
            raise UserAdminError("System administrators must also include sop_admin")

    async def _validate_scopes(
        self,
        organization_id: str,
        *,
        departments: frozenset[str],
        locations: frozenset[str],
        organizational_roles: frozenset[str],
        roles: frozenset[ApplicationRole],
        management_departments: frozenset[str],
        management_locations: frozenset[str],
        management_roles: frozenset[str],
        existing: EmployeeProfile | None = None,
    ) -> None:
        await self._organization.validate_keys(
            organization_id,
            CatalogKind.DEPARTMENT,
            departments,
            allowed_inactive=existing.departments if existing else frozenset(),
        )
        if locations:
            await self._organization.validate_keys(
                organization_id,
                CatalogKind.LOCATION,
                locations,
                allowed_inactive=existing.locations if existing else frozenset(),
            )
        if organizational_roles:
            await self._organization.validate_keys(
                organization_id,
                CatalogKind.ORGANIZATIONAL_ROLE,
                organizational_roles,
                allowed_inactive=existing.organizational_roles if existing else frozenset(),
            )
        management_values = (
            management_departments,
            management_locations,
            management_roles,
        )
        if ApplicationRole.SOP_ADMIN not in roles and any(management_values):
            raise UserAdminError("Management scope is only valid for administrators")
        if ApplicationRole.SOP_ADMIN in roles and ApplicationRole.SYSTEM_ADMIN not in roles:
            await self._organization.validate_keys(
                organization_id,
                CatalogKind.DEPARTMENT,
                management_departments,
                allowed_inactive=(existing.management_departments if existing else frozenset()),
            )
            await self._organization.validate_keys(
                organization_id,
                CatalogKind.LOCATION,
                management_locations,
                allowed_inactive=existing.management_locations if existing else frozenset(),
            )
            await self._organization.validate_keys(
                organization_id,
                CatalogKind.ORGANIZATIONAL_ROLE,
                management_roles,
                allowed_inactive=existing.management_roles if existing else frozenset(),
            )
        elif ApplicationRole.SYSTEM_ADMIN in roles:
            for kind, values, historical in (
                (
                    CatalogKind.DEPARTMENT,
                    management_departments,
                    existing.management_departments if existing else frozenset(),
                ),
                (
                    CatalogKind.LOCATION,
                    management_locations,
                    existing.management_locations if existing else frozenset(),
                ),
                (
                    CatalogKind.ORGANIZATIONAL_ROLE,
                    management_roles,
                    existing.management_roles if existing else frozenset(),
                ),
            ):
                if values:
                    await self._organization.validate_keys(
                        organization_id,
                        kind,
                        values,
                        allowed_inactive=historical,
                    )

    async def list_users(
        self,
        organization_id: str,
        *,
        page: int = 1,
        limit: int = 25,
        search: str | None = None,
        status: MembershipStatus | None = None,
        application_role: ApplicationRole | None = None,
        department: str | None = None,
        location: str | None = None,
        organizational_role: str | None = None,
    ) -> UserPage:
        records = await self._database.find_many(
            "employee_profiles", organization_id, {}, sort=(("display_name", 1),), limit=100_000
        )
        users = [EmployeeProfile.model_validate(record) for record in records]
        if search:
            needle = search.casefold()
            users = [
                user
                for user in users
                if needle in user.display_name.casefold() or needle in user.email.casefold()
            ]
        if status:
            users = [user for user in users if user.status is status]
        if application_role:
            users = [user for user in users if application_role in user.application_roles]
        if department:
            users = [user for user in users if department in user.departments]
        if location:
            users = [user for user in users if location in user.locations]
        if organizational_role:
            users = [user for user in users if organizational_role in user.organizational_roles]
        total = len(users)
        start = (page - 1) * limit
        return UserPage(users[start : start + limit], total, page, limit)

    async def get_user(self, organization_id: str, user_id: str) -> EmployeeProfile:
        record = await self._database.get_one("employee_profiles", organization_id, {"id": user_id})
        if not record:
            raise KeyError(user_id)
        return EmployeeProfile.model_validate(record)

    async def create_user(
        self,
        organization_id: str,
        actor_id: str,
        *,
        display_name: str,
        email: str,
        preferred_language: Language,
        application_roles: frozenset[ApplicationRole],
        departments: frozenset[str],
        locations: frozenset[str],
        organizational_roles: frozenset[str],
        management_departments: frozenset[str],
        management_locations: frozenset[str],
        management_roles: frozenset[str],
        idempotency_key: str,
    ) -> CreatedUser:
        self._validate_roles(application_roles)
        normalized_email = self._normalize_email(email)
        if not idempotency_key.strip():
            raise UserAdminError("Idempotency-Key is required")
        existing_request = await self._database.get_one(
            "admin_idempotency", organization_id, {"key": idempotency_key}
        )
        if existing_request:
            existing_user = await self.get_user(organization_id, str(existing_request["user_id"]))
            reset_link = await self._identities.generate_password_reset_link(existing_user.email)
            return CreatedUser(existing_user, reset_link)
        if await self._database.get_one(
            "employee_profiles", organization_id, {"email": normalized_email}
        ):
            raise UserConflictError("An account already exists for this email address")
        await self._validate_scopes(
            organization_id,
            departments=departments,
            locations=locations,
            organizational_roles=organizational_roles,
            roles=application_roles,
            management_departments=management_departments,
            management_locations=management_locations,
            management_roles=management_roles,
        )
        identity = await self._identities.create_identity(normalized_email, display_name.strip())
        profile = EmployeeProfile(
            id=f"user-{uuid4().hex[:12]}",
            organization_id=organization_id,
            identity_subject=identity.uid,
            display_name=display_name.strip(),
            email=normalized_email,
            application_roles=application_roles,
            departments=departments,
            locations=locations,
            organizational_roles=organizational_roles,
            management_departments=management_departments,
            management_locations=management_locations,
            management_roles=management_roles,
            preferred_language=preferred_language,
            active=True,
            status=MembershipStatus.PENDING_ACTIVATION,
        )
        try:
            await self._database.insert_one(
                "employee_profiles",
                organization_id,
                profile.model_dump(mode="json", exclude={"organization_id"}),
            )
            await self._database.insert_one(
                "admin_idempotency",
                organization_id,
                {"id": f"idem-{uuid4().hex[:12]}", "key": idempotency_key, "user_id": profile.id},
            )
            await self._audit.record(
                organization_id,
                actor_id,
                "identity.user_created",
                "employee_profile",
                profile.id,
                {
                    "application_roles": cast(
                        JsonValue, sorted(role.value for role in application_roles)
                    ),
                    "status": profile.status.value,
                },
            )
            if ApplicationRole.SYSTEM_ADMIN in application_roles:
                await self._audit.record(
                    organization_id,
                    actor_id,
                    "access.system_admin_granted",
                    "employee_profile",
                    profile.id,
                    {"severity": "high"},
                )
            activation_link = await self._identities.generate_password_reset_link(normalized_email)
            return CreatedUser(profile, activation_link)
        except Exception as error:
            await self._database.delete_one(
                "admin_idempotency", organization_id, {"key": idempotency_key}
            )
            await self._database.delete_one(
                "employee_profiles", organization_id, {"id": profile.id}
            )
            try:
                await self._identities.delete_identity(identity.uid)
            except IdentityAdminError:
                await self._identities.disable_identity(identity.uid)
            if isinstance(error, UserAdminError | IdentityAdminError):
                raise
            raise UserConflictError("User could not be created consistently") from error

    async def _active_system_admin_count(self, organization_id: str) -> int:
        records = await self._database.find_many(
            "employee_profiles", organization_id, {"active": True}, limit=100_000
        )
        return sum(
            1
            for record in records
            if ApplicationRole.SYSTEM_ADMIN.value in record.get("application_roles", [])
        )

    async def update_user(
        self,
        organization_id: str,
        actor_id: str,
        user_id: str,
        *,
        display_name: str,
        email: str,
        preferred_language: Language,
        application_roles: frozenset[ApplicationRole],
        departments: frozenset[str],
        locations: frozenset[str],
        organizational_roles: frozenset[str],
        management_departments: frozenset[str],
        management_locations: frozenset[str],
        management_roles: frozenset[str],
        expected_version: int,
        confirm_self_role_change: bool,
    ) -> EmployeeProfile:
        current = await self.get_user(organization_id, user_id)
        self._validate_roles(application_roles)
        normalized_email = self._normalize_email(email)
        removes_system_admin = (
            ApplicationRole.SYSTEM_ADMIN in current.application_roles
            and ApplicationRole.SYSTEM_ADMIN not in application_roles
        )
        if removes_system_admin:
            if await self._active_system_admin_count(organization_id) <= 1:
                raise UserConflictError("The last active System Administrator cannot be removed")
            if actor_id == user_id and not confirm_self_role_change:
                raise UserConflictError(
                    "Confirm the removal of your own System Administrator access"
                )
        await self._validate_scopes(
            organization_id,
            departments=departments,
            locations=locations,
            organizational_roles=organizational_roles,
            roles=application_roles,
            management_departments=management_departments,
            management_locations=management_locations,
            management_roles=management_roles,
            existing=current,
        )
        duplicate = await self._database.get_one(
            "employee_profiles", organization_id, {"email": normalized_email}
        )
        if duplicate and duplicate.get("id") != user_id:
            raise UserConflictError("An account already exists for this email address")
        await self._identities.update_identity(
            current.identity_subject,
            email=normalized_email if normalized_email != current.email else None,
            display_name=display_name.strip()
            if display_name.strip() != current.display_name
            else None,
        )
        updated = current.model_copy(
            update={
                "display_name": display_name.strip(),
                "email": normalized_email,
                "preferred_language": preferred_language,
                "application_roles": application_roles,
                "departments": departments,
                "locations": locations,
                "organizational_roles": organizational_roles,
                "management_departments": management_departments,
                "management_locations": management_locations,
                "management_roles": management_roles,
                "version": current.version + 1,
                "updated_at": utc_now(),
            }
        )
        changed = await self._database.update_one(
            "employee_profiles",
            organization_id,
            {
                "id": user_id,
                # Legacy profiles default to version 1 without a stored version field.
                "version": {"$in": [1, None]} if expected_version == 1 else expected_version,
            },
            updated.model_dump(mode="json", exclude={"id", "organization_id", "created_at"}),
        )
        if not changed:
            await self._identities.update_identity(
                current.identity_subject, email=current.email, display_name=current.display_name
            )
            raise UserConflictError("This user changed since you opened it. Reload before saving")
        await self._audit_role_and_scope_changes(organization_id, actor_id, current, updated)
        await self._audit.record(
            organization_id,
            actor_id,
            "identity.user_updated",
            "employee_profile",
            updated.id,
            {
                "display_name_changed": current.display_name != updated.display_name,
                "email_changed": current.email != updated.email,
                "preferred_language_changed": (
                    current.preferred_language != updated.preferred_language
                ),
            },
        )
        return updated

    async def _audit_role_and_scope_changes(
        self,
        organization_id: str,
        actor_id: str,
        old: EmployeeProfile,
        new: EmployeeProfile,
    ) -> None:
        if old.application_roles != new.application_roles:
            await self._audit.record(
                organization_id,
                actor_id,
                "access.application_roles_changed",
                "employee_profile",
                new.id,
                {
                    "before": cast(JsonValue, sorted(role.value for role in old.application_roles)),
                    "after": cast(JsonValue, sorted(role.value for role in new.application_roles)),
                },
            )
            if ApplicationRole.SYSTEM_ADMIN in new.application_roles - old.application_roles:
                await self._audit.record(
                    organization_id,
                    actor_id,
                    "access.system_admin_granted",
                    "employee_profile",
                    new.id,
                    {"severity": "high"},
                )
            if ApplicationRole.SYSTEM_ADMIN in old.application_roles - new.application_roles:
                await self._audit.record(
                    organization_id,
                    actor_id,
                    "access.system_admin_removed",
                    "employee_profile",
                    new.id,
                    {"severity": "high"},
                )
        employee_fields: Iterable[str] = ("departments", "locations", "organizational_roles")
        if any(getattr(old, field) != getattr(new, field) for field in employee_fields):
            await self._audit.record(
                organization_id,
                actor_id,
                "access.employee_scope_changed",
                "employee_profile",
                new.id,
            )
        management_fields: Iterable[str] = (
            "management_departments",
            "management_locations",
            "management_roles",
        )
        if any(getattr(old, field) != getattr(new, field) for field in management_fields):
            await self._audit.record(
                organization_id,
                actor_id,
                "access.management_scope_changed",
                "employee_profile",
                new.id,
            )

    async def disable_user(
        self,
        organization_id: str,
        actor_id: str,
        user_id: str,
        *,
        confirmation_email: str,
    ) -> EmployeeProfile:
        current = await self.get_user(organization_id, user_id)
        if ApplicationRole.SYSTEM_ADMIN in current.application_roles:
            if await self._active_system_admin_count(organization_id) <= 1:
                raise UserConflictError("The last active System Administrator cannot be disabled")
            if actor_id == user_id and confirmation_email.casefold() != current.email.casefold():
                raise UserConflictError(
                    "Enter your email address to confirm disabling your own account"
                )
        await self._identities.disable_identity(current.identity_subject)
        updated = current.model_copy(
            update={
                "active": False,
                "status": MembershipStatus.DISABLED,
                "version": current.version + 1,
                "updated_at": utc_now(),
            }
        )
        changed = await self._database.update_one(
            "employee_profiles",
            organization_id,
            {"id": user_id, "version": current.version},
            updated.model_dump(mode="json", exclude={"id", "organization_id", "created_at"}),
        )
        if not changed:
            await self._identities.enable_identity(current.identity_subject)
            raise UserConflictError("This user changed since you opened it. Reload before saving")
        await self._audit.record(
            organization_id, actor_id, "identity.user_disabled", "employee_profile", user_id
        )
        return updated

    async def reactivate_user(
        self, organization_id: str, actor_id: str, user_id: str
    ) -> EmployeeProfile:
        current = await self.get_user(organization_id, user_id)
        await self._validate_scopes(
            organization_id,
            departments=current.departments,
            locations=current.locations,
            organizational_roles=current.organizational_roles,
            roles=current.application_roles,
            management_departments=current.management_departments,
            management_locations=current.management_locations,
            management_roles=current.management_roles,
        )
        identity = await self._identities.get_identity(current.identity_subject)
        if not identity or identity.email.casefold() != current.email.casefold():
            raise UserConflictError(
                "Firebase identity is missing or no longer matches this profile"
            )
        await self._identities.enable_identity(current.identity_subject)
        updated = current.model_copy(
            update={
                "active": True,
                "status": MembershipStatus.ACTIVE,
                "version": current.version + 1,
                "updated_at": utc_now(),
            }
        )
        changed = await self._database.update_one(
            "employee_profiles",
            organization_id,
            {"id": user_id, "version": current.version},
            updated.model_dump(mode="json", exclude={"id", "organization_id", "created_at"}),
        )
        if not changed:
            await self._identities.disable_identity(current.identity_subject)
            raise UserConflictError("This user changed since you opened it. Reload before saving")
        await self._audit.record(
            organization_id, actor_id, "identity.user_reactivated", "employee_profile", user_id
        )
        return updated

    async def generate_password_reset(
        self, organization_id: str, actor_id: str, user_id: str
    ) -> str:
        current = await self.get_user(organization_id, user_id)
        link = await self._identities.generate_password_reset_link(current.email)
        await self._audit.record(
            organization_id,
            actor_id,
            "identity.password_reset_generated",
            "employee_profile",
            user_id,
        )
        return link
