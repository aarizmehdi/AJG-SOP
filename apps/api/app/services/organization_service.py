import re
from dataclasses import dataclass
from uuid import uuid4

from apps.api.app.models.organization import CatalogKind, OrganizationCatalogItem
from apps.api.app.repositories.database import CanonicalDatabase
from apps.api.app.services.admin_audit_service import AdminAuditService
from packages.contracts.access import AccessMode, AccessScope
from packages.contracts.common import utc_now


class CatalogConflictError(ValueError):
    pass


class CatalogReferenceError(ValueError):
    pass


@dataclass(frozen=True)
class CatalogUsage:
    active_users: int = 0
    policies: int = 0
    sop_administrators: int = 0

    @property
    def total(self) -> int:
        return self.active_users + self.policies + self.sop_administrators


class OrganizationService:
    _profile_fields = {
        CatalogKind.DEPARTMENT: ("departments", "management_departments"),
        CatalogKind.LOCATION: ("locations", "management_locations"),
        CatalogKind.ORGANIZATIONAL_ROLE: ("organizational_roles", "management_roles"),
    }
    _access_fields = {
        CatalogKind.DEPARTMENT: "departments",
        CatalogKind.LOCATION: "locations",
        CatalogKind.ORGANIZATIONAL_ROLE: "roles",
    }

    def __init__(self, database: CanonicalDatabase, audit: AdminAuditService) -> None:
        self._database = database
        self._audit = audit

    @staticmethod
    def normalize_key(value: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", value.strip().lower()).strip("-_")
        if not normalized or len(normalized) > 80:
            raise ValueError(
                "Catalog key must contain letters or numbers and be at most 80 characters"
            )
        return normalized

    async def list_items(
        self, organization_id: str, kind: CatalogKind, *, include_inactive: bool = True
    ) -> list[OrganizationCatalogItem]:
        query = {} if include_inactive else {"active": True}
        records = await self._database.find_many(
            kind.value, organization_id, query, sort=(("name", 1),), limit=1_000
        )
        return [OrganizationCatalogItem.model_validate(record) for record in records]

    async def create_item(
        self,
        organization_id: str,
        actor_id: str,
        kind: CatalogKind,
        *,
        key: str,
        name: str,
        description: str | None,
    ) -> OrganizationCatalogItem:
        normalized = self.normalize_key(key)
        if await self._database.get_one(kind.value, organization_id, {"key": normalized}):
            raise CatalogConflictError(
                f"A {kind.name.lower().replace('_', ' ')} with this key already exists"
            )
        item = OrganizationCatalogItem(
            id=f"{kind.value.rstrip('s')}-{uuid4().hex[:12]}",
            organization_id=organization_id,
            key=normalized,
            name=name.strip(),
            description=description.strip() if description else None,
        )
        try:
            await self._database.insert_one(
                kind.value,
                organization_id,
                item.model_dump(mode="json", exclude={"organization_id"}),
            )
        except Exception as error:
            if await self._database.get_one(kind.value, organization_id, {"key": normalized}):
                raise CatalogConflictError(
                    f"A {kind.name.lower().replace('_', ' ')} with this key already exists"
                ) from error
            raise
        await self._audit.record(
            organization_id,
            actor_id,
            f"organization.{kind.value.rstrip('s')}_created",
            kind.value.rstrip("s"),
            item.id,
            {"key": item.key, "name": item.name},
        )
        return item

    async def get_item(
        self, organization_id: str, kind: CatalogKind, item_id: str
    ) -> OrganizationCatalogItem:
        record = await self._database.get_one(kind.value, organization_id, {"id": item_id})
        if not record:
            raise KeyError(item_id)
        return OrganizationCatalogItem.model_validate(record)

    async def usage(self, organization_id: str, kind: CatalogKind, key: str) -> CatalogUsage:
        profiles = await self._database.find_many(
            "employee_profiles", organization_id, {}, limit=100_000
        )
        employee_field, management_field = self._profile_fields[kind]
        active_users = sum(
            1
            for profile in profiles
            if profile.get("active", True) and key in profile.get(employee_field, [])
        )
        sop_admins = sum(
            1
            for profile in profiles
            if profile.get("active", True)
            and "sop_admin" in profile.get("application_roles", [])
            and key in profile.get(management_field, [])
        )
        versions = await self._database.find_many(
            "policy_versions", organization_id, {}, limit=100_000
        )
        access_field = self._access_fields[kind]
        policies = sum(
            1
            for version in versions
            if version.get("status") in {"published", "ready_to_publish", "indexing"}
            and version.get("access", {}).get(access_field, {}).get("mode") == "selected"
            and key in version.get("access", {}).get(access_field, {}).get("values", [])
        )
        return CatalogUsage(active_users, policies, sop_admins)

    async def update_item(
        self,
        organization_id: str,
        actor_id: str,
        kind: CatalogKind,
        item_id: str,
        *,
        name: str | None,
        description: str | None,
        active: bool | None,
        expected_version: int,
        update_description: bool = True,
    ) -> OrganizationCatalogItem:
        current = await self.get_item(organization_id, kind, item_id)
        if active is False and current.active:
            usage = await self.usage(organization_id, kind, current.key)
            if usage.total:
                raise CatalogConflictError(
                    "Catalog item is still referenced by active users, policies, "
                    "or SOP administrators"
                )
        updated = current.model_copy(
            update={
                "name": name.strip() if name is not None else current.name,
                "description": (description.strip() if description else None)
                if update_description
                else current.description,
                "active": active if active is not None else current.active,
                "version": current.version + 1,
                "updated_at": utc_now(),
            }
        )
        changed = await self._database.update_one(
            kind.value,
            organization_id,
            {"id": item_id, "version": expected_version},
            updated.model_dump(mode="json", exclude={"id", "organization_id", "created_at"}),
        )
        if not changed:
            raise CatalogConflictError(
                "This record changed since you opened it. Reload before saving"
            )
        action = (
            "reactivated"
            if active is True and not current.active
            else "deactivated"
            if active is False and current.active
            else "updated"
        )
        await self._audit.record(
            organization_id,
            actor_id,
            f"organization.{kind.value.rstrip('s')}_{action}",
            kind.value.rstrip("s"),
            item_id,
            {"key": current.key, "name": updated.name},
        )
        return updated

    async def validate_keys(
        self,
        organization_id: str,
        kind: CatalogKind,
        keys: set[str] | frozenset[str],
        *,
        require_active: bool = True,
        allowed_inactive: set[str] | frozenset[str] = frozenset(),
    ) -> None:
        if not keys:
            raise CatalogReferenceError(
                f"At least one {kind.name.lower().replace('_', ' ')} is required"
            )
        items = await self.list_items(organization_id, kind, include_inactive=True)
        by_key = {item.key: item for item in items}
        missing = sorted(key for key in keys if key not in by_key)
        inactive = sorted(
            key
            for key in keys
            if key in by_key and not by_key[key].active and key not in allowed_inactive
        )
        if missing:
            raise CatalogReferenceError(
                f"Unknown {kind.name.lower().replace('_', ' ')}: {', '.join(missing)}"
            )
        if require_active and inactive:
            raise CatalogReferenceError(
                f"Inactive {kind.name.lower().replace('_', ' ')} cannot be assigned: "
                f"{', '.join(inactive)}"
            )

    async def validate_access_scope(
        self,
        organization_id: str,
        access: AccessScope,
        existing_access: AccessScope | None = None,
    ) -> None:
        dimensions = (
            (
                CatalogKind.DEPARTMENT,
                access.departments,
                existing_access.departments if existing_access else None,
            ),
            (
                CatalogKind.LOCATION,
                access.locations,
                existing_access.locations if existing_access else None,
            ),
            (
                CatalogKind.ORGANIZATIONAL_ROLE,
                access.roles,
                existing_access.roles if existing_access else None,
            ),
        )
        for kind, dimension, existing_dimension in dimensions:
            if dimension.mode is AccessMode.SELECTED:
                allowed_inactive = (
                    existing_dimension.values
                    if existing_dimension and existing_dimension.mode is AccessMode.SELECTED
                    else frozenset()
                )
                await self.validate_keys(
                    organization_id,
                    kind,
                    dimension.values,
                    allowed_inactive=allowed_inactive,
                )

    async def bootstrap_from_existing_profiles(self, organization_id: str) -> dict[str, object]:
        profiles = await self._database.find_many(
            "employee_profiles", organization_id, {}, limit=100_000
        )
        discovered: dict[CatalogKind, set[str]] = {kind: set() for kind in CatalogKind}
        for profile in profiles:
            for kind, (employee_field, management_field) in self._profile_fields.items():
                discovered[kind].update(str(value) for value in profile.get(employee_field, []))
                discovered[kind].update(str(value) for value in profile.get(management_field, []))
        report: dict[str, object] = {
            "organization_id": organization_id,
            "created": {},
            "existing": {},
        }
        for kind, keys in discovered.items():
            existing = {item.key for item in await self.list_items(organization_id, kind)}
            report["existing"][kind.value] = sorted(existing & keys)  # type: ignore[index]
            report["created"][kind.value] = sorted(keys - existing)  # type: ignore[index]
        return report
