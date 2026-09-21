"""Provision least-privilege Employee and SOP Admin profiles for verified Firebase users."""

import asyncio
import json
import os
from argparse import ArgumentParser
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast
from uuid import uuid4

import firebase_admin  # type: ignore[import-untyped]
from firebase_admin import auth, credentials
from pymongo import AsyncMongoClient

from apps.api.app.models.organization import ApplicationRole, EmployeeProfile
from packages.contracts.common import Language, utc_now


@dataclass(frozen=True)
class VerifiedFirebaseUser:
    uid: str
    email: str
    display_name: str | None
    email_verified: bool


@dataclass(frozen=True)
class ProfilePlan:
    profile_id: str
    firebase_uid: str
    fallback_display_name: str
    application_roles: frozenset[ApplicationRole]
    departments: frozenset[str]
    locations: frozenset[str]
    organizational_roles: frozenset[str]
    management_departments: frozenset[str] = frozenset()
    management_locations: frozenset[str] = frozenset()
    management_roles: frozenset[str] = frozenset()


def role_profile_plans(employee_uid: str, sop_admin_uid: str) -> tuple[ProfilePlan, ProfilePlan]:
    if not employee_uid.strip() or not sop_admin_uid.strip():
        raise ValueError("Both Firebase UIDs are required")
    if employee_uid == sop_admin_uid:
        raise ValueError("Employee and SOP Admin must use separate Firebase UIDs")
    return (
        ProfilePlan(
            profile_id="user-ajt-employee",
            firebase_uid=employee_uid,
            fallback_display_name="AJG Employee",
            application_roles=frozenset({ApplicationRole.EMPLOYEE}),
            departments=frozenset({"operations"}),
            locations=frozenset({"head-office"}),
            organizational_roles=frozenset({"employee"}),
        ),
        ProfilePlan(
            profile_id="user-ajt-sop-admin",
            firebase_uid=sop_admin_uid,
            fallback_display_name="AJG SOP Administrator",
            application_roles=frozenset({ApplicationRole.EMPLOYEE, ApplicationRole.SOP_ADMIN}),
            departments=frozenset({"operations"}),
            locations=frozenset({"head-office"}),
            organizational_roles=frozenset({"manager"}),
            management_departments=frozenset({"operations"}),
            management_locations=frozenset({"head-office"}),
            management_roles=frozenset({"employee", "manager"}),
        ),
    )


def build_profile(
    organization_id: str, plan: ProfilePlan, firebase_user: VerifiedFirebaseUser
) -> EmployeeProfile:
    if firebase_user.uid != plan.firebase_uid:
        raise ValueError("Verified Firebase UID does not match the profile plan")
    if ApplicationRole.SYSTEM_ADMIN in plan.application_roles:
        raise ValueError("This provisioning flow cannot grant System Admin")
    if not firebase_user.email:
        raise ValueError("A verified Firebase user record must include an email")
    return EmployeeProfile(
        id=plan.profile_id,
        organization_id=organization_id,
        identity_subject=firebase_user.uid,
        display_name=firebase_user.display_name or plan.fallback_display_name,
        email=firebase_user.email,
        application_roles=plan.application_roles,
        departments=plan.departments,
        locations=plan.locations,
        organizational_roles=plan.organizational_roles,
        management_departments=plan.management_departments,
        management_locations=plan.management_locations,
        management_roles=plan.management_roles,
        preferred_language=Language.ENGLISH,
        active=True,
    )


def profile_document(profile: EmployeeProfile) -> dict[str, Any]:
    document = profile.model_dump(mode="json")
    for field in (
        "application_roles",
        "departments",
        "locations",
        "organizational_roles",
        "management_departments",
        "management_locations",
        "management_roles",
    ):
        document[field] = sorted(document[field])
    return document


def _controlled_profile(document: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "id",
        "organization_id",
        "identity_subject",
        "display_name",
        "email",
        "application_roles",
        "departments",
        "locations",
        "organizational_roles",
        "management_departments",
        "management_locations",
        "management_roles",
        "preferred_language",
        "active",
    )
    normalized = {field: document.get(field) for field in fields}
    for field in (
        "application_roles",
        "departments",
        "locations",
        "organizational_roles",
        "management_departments",
        "management_locations",
        "management_roles",
    ):
        normalized[field] = sorted(normalized[field] or [])
    return normalized


def _firebase_app(project_id: str, service_account_json: str) -> Any:
    service_account = json.loads(service_account_json)
    if service_account.get("project_id") != project_id:
        raise RuntimeError("Firebase service-account project does not match FIREBASE_PROJECT_ID")
    try:
        return firebase_admin.get_app("ajt-role-provisioning")
    except ValueError:
        return firebase_admin.initialize_app(
            credentials.Certificate(service_account),
            {"projectId": project_id},
            name="ajt-role-provisioning",
        )


async def verify_firebase_users(
    plans: tuple[ProfilePlan, ProfilePlan], project_id: str, service_account_json: str
) -> dict[str, VerifiedFirebaseUser]:
    app = _firebase_app(project_id, service_account_json)
    verified: dict[str, VerifiedFirebaseUser] = {}
    for plan in plans:
        try:
            record = await asyncio.to_thread(auth.get_user, plan.firebase_uid, app=app)
        except Exception as error:
            raise RuntimeError(
                f"Firebase UID verification failed for profile {plan.profile_id!r}"
            ) from error
        if record.disabled:
            raise RuntimeError(f"Firebase user for profile {plan.profile_id!r} is disabled")
        if not record.email:
            raise RuntimeError(f"Firebase user for profile {plan.profile_id!r} has no email")
        verified[plan.profile_id] = VerifiedFirebaseUser(
            uid=record.uid,
            email=record.email,
            display_name=record.display_name,
            email_verified=bool(record.email_verified),
        )
    return verified


async def _existing_collisions(
    profiles: Any, documents: Sequence[dict[str, Any]], session: Any = None
) -> list[dict[str, Any]]:
    query = {
        "$or": [
            {"id": {"$in": [document["id"] for document in documents]}},
            {"identity_subject": {"$in": [document["identity_subject"] for document in documents]}},
            {"email": {"$in": [document["email"] for document in documents]}},
        ]
    }
    return cast(
        list[dict[str, Any]], await profiles.find(query, session=session).to_list(length=10)
    )


def _documents_to_insert(
    existing: list[dict[str, Any]], intended: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    inserts: list[dict[str, Any]] = []
    for document in intended:
        matches = [
            item
            for item in existing
            if item.get("id") == document["id"]
            or item.get("identity_subject") == document["identity_subject"]
            or item.get("email") == document["email"]
        ]
        if not matches:
            inserts.append(document)
            continue
        if len(matches) != 1 or _controlled_profile(matches[0]) != _controlled_profile(document):
            raise RuntimeError(
                f"Existing profile collision for {document['id']!r}; refusing to overwrite"
            )
    return inserts


async def provision_role_profiles(
    *,
    mongo_uri: str,
    database_name: str,
    organization_id: str,
    employee_uid: str,
    sop_admin_uid: str,
    firebase_project_id: str,
    firebase_service_account_json: str,
    actor_id: str,
    apply: bool,
) -> None:
    if organization_id != "ajt":
        raise ValueError("This provisioning plan is restricted to organization 'ajt'")
    plans = role_profile_plans(employee_uid, sop_admin_uid)
    verified = await verify_firebase_users(
        plans, firebase_project_id, firebase_service_account_json
    )
    intended = tuple(
        profile_document(build_profile(organization_id, plan, verified[plan.profile_id]))
        for plan in plans
    )
    if len({document["email"].casefold() for document in intended}) != len(intended):
        raise RuntimeError("The Firebase users must have separate email addresses")

    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(mongo_uri)
    database = client[database_name]
    profiles = database["employee_profiles"]
    try:
        organization_count = await database["organizations"].count_documents(
            {"organization_id": organization_id}
        )
        if organization_count != 1:
            raise RuntimeError(
                f"Expected exactly one organization {organization_id!r}, found {organization_count}"
            )

        existing = await _existing_collisions(profiles, intended)
        inserts = _documents_to_insert(existing, intended)
        unverified = [
            plan.profile_id for plan in plans if not verified[plan.profile_id].email_verified
        ]
        print(
            f"Verified two enabled Firebase users in project {firebase_project_id!r}; "
            f"email verification pending for {len(unverified)} account(s)"
        )
        print(
            f"Validated organization {organization_id!r}; profiles to create={len(inserts)}; "
            f"already exact={len(intended) - len(inserts)}"
        )
        if not apply:
            print("[DRY RUN] No database changes made. Re-run with --apply to commit.")
            return

        await profiles.create_index(
            "identity_subject", unique=True, name="uq_employee_identity_subject"
        )
        async with client.start_session() as session:
            async with await session.start_transaction():
                existing = await _existing_collisions(profiles, intended, session=session)
                inserts = _documents_to_insert(existing, intended)
                system_admins_before = await profiles.find(
                    {
                        "organization_id": organization_id,
                        "application_roles": ApplicationRole.SYSTEM_ADMIN.value,
                    },
                    session=session,
                ).to_list(length=100)
                for document in inserts:
                    if ApplicationRole.SYSTEM_ADMIN.value in document["application_roles"]:
                        raise RuntimeError("Refusing to provision a System Admin role")
                    await profiles.insert_one(document, session=session)
                    await database["audit_events"].insert_one(
                        {
                            "id": f"audit-{uuid4().hex[:12]}",
                            "organization_id": organization_id,
                            "actor_id": actor_id,
                            "action": "identity.profile_provisioned",
                            "entity_type": "employee_profile",
                            "entity_id": document["id"],
                            "occurred_at": utc_now(),
                            "metadata": {
                                "firebase_uid": document["identity_subject"],
                                "application_roles": document["application_roles"],
                            },
                        },
                        session=session,
                    )
                system_admins_after = await profiles.find(
                    {
                        "organization_id": organization_id,
                        "application_roles": ApplicationRole.SYSTEM_ADMIN.value,
                    },
                    session=session,
                ).to_list(length=100)
                if system_admins_after != system_admins_before:
                    raise RuntimeError("System Admin profiles changed; aborting transaction")
        print(f"[OK] Created {len(inserts)} least-privilege employee profile(s) atomically")
    finally:
        await client.close()


def main() -> None:
    parser = ArgumentParser(
        description="Verify Firebase users and provision Employee/SOP Admin MongoDB profiles."
    )
    parser.add_argument("--employee-uid", required=True)
    parser.add_argument("--sop-admin-uid", required=True)
    parser.add_argument("--organization-id", default="ajt")
    parser.add_argument("--actor-id", default="firebase-role-provisioning")
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()

    required_environment = (
        "MONGODB_URI",
        "FIREBASE_PROJECT_ID",
        "FIREBASE_SERVICE_ACCOUNT_JSON",
    )
    missing = [name for name in required_environment if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    asyncio.run(
        provision_role_profiles(
            mongo_uri=os.environ["MONGODB_URI"],
            database_name=os.environ.get("MONGODB_DATABASE", "aziz_jan_sop"),
            organization_id=arguments.organization_id,
            employee_uid=arguments.employee_uid,
            sop_admin_uid=arguments.sop_admin_uid,
            firebase_project_id=os.environ["FIREBASE_PROJECT_ID"],
            firebase_service_account_json=os.environ["FIREBASE_SERVICE_ACCOUNT_JSON"],
            actor_id=arguments.actor_id,
            apply=arguments.apply,
        )
    )


if __name__ == "__main__":
    main()
