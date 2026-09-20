"""CLI script to provision initial organization and employee profiles in MongoDB Atlas."""

import asyncio
from argparse import ArgumentParser
from typing import Any

from pymongo import AsyncMongoClient

from apps.api.app.models.organization import ApplicationRole, EmployeeProfile, Organization
from packages.contracts.common import Language, utc_now


async def provision(
    mongo_uri: str,
    db_name: str,
    org_id: str,
    org_name: str,
    org_slug: str,
    firebase_uid: str,
    admin_email: str,
    admin_name: str,
    assign_system_admin: bool,
) -> None:
    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(mongo_uri)
    db = client[db_name]

    print(f"Connecting to MongoDB database '{db_name}'...")

    # 1. Provision Organization
    org = Organization(
        organization_id=org_id,
        name=org_name,
        slug=org_slug,
        created_at=utc_now(),
    )
    await db["organizations"].replace_one(
        {"organization_id": org_id},
        org.model_dump(mode="json"),
        upsert=True,
    )
    print(f"[OK] Provisioned organization '{org_name}' (ID: {org_id})")

    # 2. Provision Admin Profile
    roles = {ApplicationRole.EMPLOYEE, ApplicationRole.SOP_ADMIN}
    if assign_system_admin:
        roles.add(ApplicationRole.SYSTEM_ADMIN)

    profile = EmployeeProfile(
        id=f"user-{org_id}-admin",
        organization_id=org_id,
        identity_subject=firebase_uid,
        display_name=admin_name,
        email=admin_email,
        application_roles=frozenset(roles),
        departments=frozenset({"management", "operations", "technology"}),
        locations=frozenset({"head-office"}),
        organizational_roles=frozenset({"admin"}),
        management_departments=frozenset({"management", "operations", "technology"}),
        management_locations=frozenset({"head-office"}),
        management_roles=frozenset({"admin"}),
        preferred_language=Language.ENGLISH,
        active=True,
    )

    doc = profile.model_dump(mode="json")
    # Convert sets/frozensets for mongodb storage
    doc["application_roles"] = list(doc["application_roles"])
    doc["departments"] = list(doc["departments"])
    doc["locations"] = list(doc["locations"])
    doc["organizational_roles"] = list(doc["organizational_roles"])
    doc["management_departments"] = list(doc["management_departments"])
    doc["management_locations"] = list(doc["management_locations"])
    doc["management_roles"] = list(doc["management_roles"])

    existing = await db["employee_profiles"].find_one(
        {
            "organization_id": org_id,
            "$or": [
                {"id": profile.id},
                {"identity_subject": firebase_uid},
                {"email": admin_email},
            ],
        }
    )
    if existing and existing.get("identity_subject") != firebase_uid:
        raise RuntimeError(
            "An existing administrator/profile matched. Use the explicit Firebase UID link "
            "procedure instead of creating a duplicate."
        )
    await db["employee_profiles"].create_index(
        "identity_subject", unique=True, name="uq_employee_identity_subject"
    )
    await db["employee_profiles"].replace_one(
        {"organization_id": org_id, "identity_subject": firebase_uid},
        doc,
        upsert=True,
    )
    print(
        f"[OK] Provisioned employee profile '{admin_name}' ({admin_email}) "
        f"with Firebase UID '{firebase_uid}'"
    )
    print(f"  Roles: {[r.value for r in roles]}")
    await client.close()


def main() -> None:
    parser = ArgumentParser(
        description="Provision initial organization and employee profile in MongoDB."
    )
    parser.add_argument("--mongo-uri", required=True, help="MongoDB connection string")
    parser.add_argument("--db-name", default="ajt_sop", help="Database name (default: ajt_sop)")
    parser.add_argument("--org-id", default="ajt", help="Organization ID (default: ajt)")
    parser.add_argument("--org-name", default="Aziz Jan Trust", help="Organization name")
    parser.add_argument("--org-slug", default="ajt", help="Organization slug")
    parser.add_argument(
        "--firebase-uid", required=True, help="Existing Firebase Authentication UID"
    )
    parser.add_argument("--admin-email", required=True, help="Admin user email")
    parser.add_argument("--admin-name", required=True, help="Admin user display name")
    parser.add_argument(
        "--with-system-admin", action="store_true", help="Explicitly assign system_admin role"
    )

    args = parser.parse_args()

    asyncio.run(
        provision(
            mongo_uri=args.mongo_uri,
            db_name=args.db_name,
            org_id=args.org_id,
            org_name=args.org_name,
            org_slug=args.org_slug,
            firebase_uid=args.firebase_uid,
            admin_email=args.admin_email,
            admin_name=args.admin_name,
            assign_system_admin=args.with_system_admin,
        )
    )


if __name__ == "__main__":
    main()
