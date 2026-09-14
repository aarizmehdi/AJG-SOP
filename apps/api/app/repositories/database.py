from collections.abc import Mapping
from typing import Any, Protocol

from pymongo import AsyncMongoClient


class CanonicalDatabase(Protocol):
    async def resolve_identity_profile(
        self, identity_subject: str, external_organization_id: str | None
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
        self, identity_subject: str, external_organization_id: str | None
    ) -> dict[str, Any] | None:
        """Resolve the tenant from validated identity data, never from request parameters."""
        if not external_organization_id:
            return None
        organization = await self._database["organizations"].find_one(
            {"auth0_organization_id": external_organization_id}
        )
        if not organization:
            return None
        return await self._database["employee_profiles"].find_one(
            {
                "organization_id": organization["organization_id"],
                "identity_subject": identity_subject,
                "active": True,
            }
        )

    @staticmethod
    def _tenant_query(organization_id: str, query: Mapping[str, Any]) -> dict[str, Any]:
        return {**query, "organization_id": organization_id}

    async def get_one(
        self, collection: str, organization_id: str, query: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        return await self._database[collection].find_one(
            self._tenant_query(organization_id, query)
        )

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
        self, identity_subject: str, external_organization_id: str | None
    ) -> dict[str, Any] | None:
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
