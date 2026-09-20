from collections.abc import Mapping
from typing import Any, Protocol

from pymongo import AsyncMongoClient


class CanonicalDatabase(Protocol):
    async def resolve_identity_profile(
        self,
        identity_subject: str,
        external_organization_id: str | None,
        email: str | None = None,
        display_name: str | None = None,
    ) -> dict[str, Any] | None: ...

    async def get_one(
        self, collection: str, organization_id: str, query: Mapping[str, Any]
    ) -> dict[str, Any] | None: ...

    async def insert_one(
        self, collection: str, organization_id: str, document: Mapping[str, Any]
    ) -> str: ...

    async def replace_one(
        self,
        collection: str,
        organization_id: str,
        query: Mapping[str, Any],
        document: Mapping[str, Any],
    ) -> bool: ...


class MongoCanonicalDatabase:
    """Canonical persistence boundary. Every operation injects the trusted tenant id."""

    def __init__(self, uri: str, database: str) -> None:
        self._client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(uri)
        self._database = self._client[database]

    async def resolve_identity_profile(
        self,
        identity_subject: str,
        external_organization_id: str | None,
        email: str | None = None,
        display_name: str | None = None,
    ) -> dict[str, Any] | None:
        """Resolve the tenant from validated identity data, never from request parameters."""
        if external_organization_id:
            organization = await self._database["organizations"].find_one(
                {"auth0_organization_id": external_organization_id}
            )
            if not organization:
                return None
            profile = await self._database["employee_profiles"].find_one(
                {
                    "organization_id": organization["organization_id"],
                    "identity_subject": identity_subject,
                    "active": True,
                }
            )
            if profile:
                return profile
            if email:
                profile = await self._database["employee_profiles"].find_one(
                    {
                        "organization_id": organization["organization_id"],
                        "email": email,
                        "active": True,
                    }
                )
                if profile:
                    await self._database["employee_profiles"].update_one(
                        {"_id": profile["_id"]},
                        {"$set": {"identity_subject": identity_subject}},
                    )
                    profile["identity_subject"] = identity_subject
                    return profile
            return None

        # Standard single-tenant MVP resolution by identity_subject:
        profile = await self._database["employee_profiles"].find_one(
            {
                "identity_subject": identity_subject,
                "active": True,
            }
        )
        if profile:
            return profile

        # Email fallback for seeded admin or provisioned users:
        if email:
            profile = await self._database["employee_profiles"].find_one(
                {
                    "email": email,
                    "active": True,
                }
            )
            if profile:
                await self._database["employee_profiles"].update_one(
                    {"_id": profile["_id"]},
                    {"$set": {"identity_subject": identity_subject}},
                )
                profile["identity_subject"] = identity_subject
                return profile

        # Live auto-provisioning for organization 'ajt':
        org = await self._database["organizations"].find_one({"organization_id": "ajt"})
        if not org:
            org = {
                "organization_id": "ajt",
                "name": "Aziz Jan Trust",
                "slug": "ajt",
                "created_at": "2026-09-20T00:00:00Z",
            }
            await self._database["organizations"].replace_one(
                {"organization_id": "ajt"}, org, upsert=True
            )

        total_profiles = await self._database["employee_profiles"].count_documents(
            {"organization_id": "ajt"}
        )
        is_first = total_profiles == 0
        roles = ["employee", "sop_admin", "system_admin"] if is_first else ["employee"]
        new_profile = {
            "id": f"user-ajt-{identity_subject.replace('|', '-')}",
            "organization_id": "ajt",
            "identity_subject": identity_subject,
            "display_name": display_name or email or "Live User",
            "email": email or f"{identity_subject}@ajt.org",
            "application_roles": roles,
            "departments": ["management", "operations", "technology"],
            "locations": ["head-office"],
            "organizational_roles": ["admin"] if is_first else ["employee"],
            "management_departments": ["management", "operations", "technology"],
            "management_locations": ["head-office"],
            "management_roles": ["admin"],
            "preferred_language": "english",
            "active": True,
        }
        await self._database["employee_profiles"].replace_one(
            {"organization_id": "ajt", "identity_subject": identity_subject},
            new_profile,
            upsert=True,
        )
        return new_profile

    @staticmethod
    def _tenant_query(organization_id: str, query: Mapping[str, Any]) -> dict[str, Any]:
        return {**query, "organization_id": organization_id}

    async def get_one(
        self, collection: str, organization_id: str, query: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        return await self._database[collection].find_one(self._tenant_query(organization_id, query))

    async def insert_one(
        self, collection: str, organization_id: str, document: Mapping[str, Any]
    ) -> str:
        result = await self._database[collection].insert_one(
            {**document, "organization_id": organization_id}
        )
        return str(result.inserted_id)

    async def replace_one(
        self,
        collection: str,
        organization_id: str,
        query: Mapping[str, Any],
        document: Mapping[str, Any],
    ) -> bool:
        result = await self._database[collection].replace_one(
            self._tenant_query(organization_id, query),
            {**document, "organization_id": organization_id},
        )
        return result.modified_count == 1


class InMemoryCanonicalDatabase:
    def __init__(self) -> None:
        self.collections: dict[str, list[dict[str, Any]]] = {}

    async def resolve_identity_profile(
        self,
        identity_subject: str,
        external_organization_id: str | None,
        email: str | None = None,
        display_name: str | None = None,
    ) -> dict[str, Any] | None:
        if external_organization_id:
            organization = next(
                (
                    item
                    for item in self.collections.get("organizations", [])
                    if item.get("auth0_organization_id") == external_organization_id
                ),
                None,
            )
            if not organization:
                return None
            return await self.get_one(
                "employee_profiles",
                str(organization["organization_id"]),
                {"identity_subject": identity_subject, "active": True},
            )
        for profile in self.collections.get("employee_profiles", []):
            if profile.get("identity_subject") == identity_subject and profile.get("active", True):
                return profile.copy()
        if email:
            for profile in self.collections.get("employee_profiles", []):
                if profile.get("email") == email and profile.get("active", True):
                    profile["identity_subject"] = identity_subject
                    return profile.copy()
        return None

    async def get_one(
        self, collection: str, organization_id: str, query: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        for document in self.collections.get(collection, []):
            if document.get("organization_id") == organization_id and all(
                document.get(key) == value for key, value in query.items()
            ):
                return document.copy()
        return None

    async def insert_one(
        self, collection: str, organization_id: str, document: Mapping[str, Any]
    ) -> str:
        stored = {**document, "organization_id": organization_id}
        self.collections.setdefault(collection, []).append(stored)
        return str(stored.get("id", len(self.collections[collection])))

    async def replace_one(
        self,
        collection: str,
        organization_id: str,
        query: Mapping[str, Any],
        document: Mapping[str, Any],
    ) -> bool:
        for index, stored in enumerate(self.collections.get(collection, [])):
            if stored.get("organization_id") == organization_id and all(
                stored.get(key) == value for key, value in query.items()
            ):
                self.collections[collection][index] = {
                    **document,
                    "organization_id": organization_id,
                }
                return True
        return False
