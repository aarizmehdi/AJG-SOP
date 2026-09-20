"""Atomically link a Firebase UID to one existing authorized MongoDB profile."""

import asyncio
from argparse import ArgumentParser
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pymongo import AsyncMongoClient


async def link_identity(
    mongo_uri: str,
    database_name: str,
    organization_id: str,
    profile_id: str,
    expected_current_subject: str,
    firebase_uid: str,
    actor_id: str,
    apply: bool,
) -> None:
    if not firebase_uid.strip() or len(firebase_uid) > 128:
        raise ValueError("Firebase UID must be between 1 and 128 characters")

    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(mongo_uri)
    database = client[database_name]
    profiles = database["employee_profiles"]
    try:
        await profiles.create_index(
            "identity_subject", unique=True, name="uq_employee_identity_subject"
        )
        async with client.start_session() as session:
            async with await session.start_transaction():
                profile = await profiles.find_one(
                    {"organization_id": organization_id, "id": profile_id}, session=session
                )
                if not profile:
                    raise RuntimeError("The exact organization/profile pair does not exist")
                if not profile.get("active", False):
                    raise RuntimeError("The target profile is inactive")
                if "system_admin" not in profile.get("application_roles", []):
                    raise RuntimeError("The target profile is not already a System Admin")

                current_subject = str(profile.get("identity_subject", ""))
                if current_subject == firebase_uid:
                    print("[OK] Profile is already linked to this Firebase UID; no change made")
                    return
                if current_subject != expected_current_subject:
                    raise RuntimeError(
                        "Current identity subject differs from --expected-current-subject"
                    )

                duplicate = await profiles.find_one(
                    {"identity_subject": firebase_uid, "_id": {"$ne": profile["_id"]}},
                    session=session,
                )
                if duplicate:
                    raise RuntimeError("Firebase UID is already linked to another profile")

                print(
                    f"Validated existing System Admin profile {profile_id!r} "
                    f"in organization {organization_id!r}"
                )
                if not apply:
                    print("[DRY RUN] No database changes made. Re-run with --apply to commit.")
                    return

                update = await profiles.update_one(
                    {
                        "_id": profile["_id"],
                        "organization_id": organization_id,
                        "id": profile_id,
                        "identity_subject": expected_current_subject,
                        "active": True,
                        "application_roles": "system_admin",
                    },
                    {"$set": {"identity_subject": firebase_uid}},
                    session=session,
                )
                if update.modified_count != 1:
                    raise RuntimeError("Profile changed during migration; no link was made")

                await database["audit_events"].insert_one(
                    {
                        "id": f"audit-{uuid4().hex[:12]}",
                        "organization_id": organization_id,
                        "actor_id": actor_id,
                        "action": "identity.firebase_uid_linked",
                        "entity_type": "employee_profile",
                        "entity_id": profile_id,
                        "occurred_at": datetime.now(UTC),
                        "metadata": {
                            "previous_identity_subject": expected_current_subject,
                            "firebase_uid": firebase_uid,
                        },
                    },
                    session=session,
                )
        print("[OK] Firebase UID linked atomically; profile roles and organization were preserved")
    finally:
        await client.close()


def main() -> None:
    parser = ArgumentParser(
        description="Link a Firebase UID to one existing, explicitly selected System Admin profile."
    )
    parser.add_argument("--mongo-uri", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--expected-current-subject", required=True)
    parser.add_argument("--firebase-uid", required=True)
    parser.add_argument("--actor-id", required=True)
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    asyncio.run(
        link_identity(
            mongo_uri=arguments.mongo_uri,
            database_name=arguments.database,
            organization_id=arguments.organization_id,
            profile_id=arguments.profile_id,
            expected_current_subject=arguments.expected_current_subject,
            firebase_uid=arguments.firebase_uid,
            actor_id=arguments.actor_id,
            apply=arguments.apply,
        )
    )


if __name__ == "__main__":
    main()
