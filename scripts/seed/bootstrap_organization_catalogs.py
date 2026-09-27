"""Plan or apply tenant catalog bootstrap from existing production references.

Dry-run is the default. Use --apply with an authenticated System Administrator
profile id only after reviewing the JSON report.
"""

import argparse
import asyncio
import json
from collections import defaultdict
from typing import Any

from apps.api.app.config import Settings
from apps.api.app.models.organization import CatalogKind
from apps.api.app.repositories.database import MongoCanonicalDatabase
from apps.api.app.services.admin_audit_service import AdminAuditService
from apps.api.app.services.organization_service import OrganizationService
from packages.contracts.common import utc_now

PROFILE_FIELDS = {
    CatalogKind.DEPARTMENT: ("departments", "management_departments"),
    CatalogKind.LOCATION: ("locations", "management_locations"),
    CatalogKind.ORGANIZATIONAL_ROLE: ("organizational_roles", "management_roles"),
}
ACCESS_FIELDS = {
    CatalogKind.DEPARTMENT: "departments",
    CatalogKind.LOCATION: "locations",
    CatalogKind.ORGANIZATIONAL_ROLE: "roles",
}


def display_name(key: str) -> str:
    return key.replace("_", " ").replace("-", " ").title()


async def run(args: argparse.Namespace) -> None:
    settings = Settings()
    database = MongoCanonicalDatabase(settings.mongodb_uri, settings.mongodb_database)
    await database.initialize()
    audit = AdminAuditService(database)
    organization = OrganizationService(database, audit)
    discovered: dict[CatalogKind, set[str]] = defaultdict(set)
    profiles = await database.find_many(
        "employee_profiles", args.organization_id, {}, limit=100_000
    )
    versions = await database.find_many("policy_versions", args.organization_id, {}, limit=100_000)
    for profile in profiles:
        for kind, fields in PROFILE_FIELDS.items():
            for field in fields:
                discovered[kind].update(str(value) for value in profile.get(field, []))
    for version in versions:
        access = version.get("access", {})
        if not isinstance(access, dict):
            continue
        for kind, field in ACCESS_FIELDS.items():
            dimension = access.get(field, {})
            if isinstance(dimension, dict) and dimension.get("mode") == "selected":
                discovered[kind].update(str(value) for value in dimension.get("values", []))
    report: dict[str, Any] = {
        "mode": "apply" if args.apply else "dry-run",
        "organization_id": args.organization_id,
        "profiles_inspected": len(profiles),
        "policy_versions_inspected": len(versions),
        "catalogs": {},
        "profiles_requiring_lifecycle_backfill": [
            profile.get("id")
            for profile in profiles
            if "version" not in profile or "status" not in profile
        ],
    }
    if args.apply:
        for profile in profiles:
            updates: dict[str, Any] = {}
            if "version" not in profile:
                updates["version"] = 1
            if "status" not in profile:
                updates["status"] = "active" if profile.get("active", True) else "disabled"
            if "created_at" not in profile:
                updates["created_at"] = utc_now().isoformat()
            if "updated_at" not in profile:
                updates["updated_at"] = utc_now().isoformat()
            if updates:
                await database.update_one(
                    "employee_profiles",
                    args.organization_id,
                    {"id": profile["id"]},
                    updates,
                )
    for kind in CatalogKind:
        existing = {
            item.key: item
            for item in await organization.list_items(
                args.organization_id, kind, include_inactive=True
            )
        }
        missing = sorted(discovered[kind] - set(existing))
        report["catalogs"][kind.value] = {
            "referenced": sorted(discovered[kind]),
            "existing": sorted(existing),
            "to_create": missing,
        }
        if args.apply:
            for key in missing:
                await organization.create_item(
                    args.organization_id,
                    args.actor_id,
                    kind,
                    key=key,
                    name=display_name(key),
                    description="Bootstrapped from an existing AJG access reference",
                )
    print(json.dumps(report, indent=2, default=str))
    await database.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--organization-id", default="ajt")
    parser.add_argument("--actor-id")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.apply and not args.actor_id:
        parser.error("--actor-id is required with --apply")
    return args


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
