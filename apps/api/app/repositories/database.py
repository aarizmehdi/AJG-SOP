from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from pymongo import AsyncMongoClient


class CanonicalDatabase(Protocol):
    async def initialize(self) -> None: ...

    async def close(self) -> None: ...

    async def resolve_identity_profile(self, identity_subject: str) -> dict[str, Any] | None: ...

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

    async def find_many(
        self,
        collection: str,
        organization_id: str,
        query: Mapping[str, Any] | None = None,
        *,
        sort: Sequence[tuple[str, int]] | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]: ...

    async def count_documents(
        self, collection: str, organization_id: str, query: Mapping[str, Any] | None = None
    ) -> int: ...

    async def update_one(
        self,
        collection: str,
        organization_id: str,
        query: Mapping[str, Any],
        updates: Mapping[str, Any],
    ) -> bool: ...

    async def delete_one(
        self, collection: str, organization_id: str, query: Mapping[str, Any]
    ) -> bool: ...


class MongoCanonicalDatabase:
    """Canonical persistence boundary. Every operation injects the trusted tenant id."""

    def __init__(self, uri: str, database: str) -> None:
        self._client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(uri)
        self._database = self._client[database]

    async def initialize(self) -> None:
        """Create indexes for the tenant-scoped administration query patterns."""
        await self._database["employee_profiles"].create_index(
            "identity_subject", unique=True, name="uq_employee_identity_subject"
        )
        await self._database["employee_profiles"].create_index(
            [("organization_id", 1), ("email", 1)],
            unique=True,
            sparse=True,
            name="uq_employee_org_email",
        )
        for field in (
            "active",
            "application_roles",
            "departments",
            "locations",
            "organizational_roles",
        ):
            await self._database["employee_profiles"].create_index(
                [("organization_id", 1), (field, 1)], name=f"ix_employee_org_{field}"
            )
        for collection in ("departments", "locations", "organizational_roles"):
            await self._database[collection].create_index(
                [("organization_id", 1), ("key", 1)],
                unique=True,
                name=f"uq_{collection}_org_key",
            )
            await self._database[collection].create_index(
                [("organization_id", 1), ("active", 1)],
                name=f"ix_{collection}_org_active",
            )
        await self._database["admin_idempotency"].create_index(
            [("organization_id", 1), ("key", 1)],
            unique=True,
            name="uq_admin_idempotency_org_key",
        )
        await self._database["audit_events"].create_index(
            [("organization_id", 1), ("occurred_at", -1)], name="ix_audit_org_time"
        )
        await self._database["audit_events"].create_index(
            [("organization_id", 1), ("actor_id", 1), ("occurred_at", -1)],
            name="ix_audit_org_actor_time",
        )
        await self._database["audit_events"].create_index(
            [("organization_id", 1), ("action", 1), ("occurred_at", -1)],
            name="ix_audit_org_action_time",
        )

    async def close(self) -> None:
        await self._client.close()

    async def resolve_identity_profile(self, identity_subject: str) -> dict[str, Any] | None:
        """Resolve only a pre-provisioned active profile by its verified Firebase UID."""
        return await self._database["employee_profiles"].find_one(
            {
                "identity_subject": identity_subject,
                "active": True,
            },
            {"_id": 0},
        )

    @staticmethod
    def _tenant_query(organization_id: str, query: Mapping[str, Any]) -> dict[str, Any]:
        return {**query, "organization_id": organization_id}

    async def get_one(
        self, collection: str, organization_id: str, query: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        return await self._database[collection].find_one(
            self._tenant_query(organization_id, query), {"_id": 0, "_foundation_key": 0}
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

    async def find_many(
        self,
        collection: str,
        organization_id: str,
        query: Mapping[str, Any] | None = None,
        *,
        sort: Sequence[tuple[str, int]] | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        cursor = self._database[collection].find(
            self._tenant_query(organization_id, query or {}),
            {"_id": 0, "_foundation_key": 0},
        )
        if sort:
            cursor = cursor.sort(list(sort))
        cursor = cursor.skip(skip).limit(limit)
        return [document async for document in cursor]

    async def count_documents(
        self, collection: str, organization_id: str, query: Mapping[str, Any] | None = None
    ) -> int:
        return await self._database[collection].count_documents(
            self._tenant_query(organization_id, query or {})
        )

    async def update_one(
        self,
        collection: str,
        organization_id: str,
        query: Mapping[str, Any],
        updates: Mapping[str, Any],
    ) -> bool:
        result = await self._database[collection].update_one(
            self._tenant_query(organization_id, query), {"$set": dict(updates)}
        )
        return result.modified_count == 1

    async def delete_one(
        self, collection: str, organization_id: str, query: Mapping[str, Any]
    ) -> bool:
        result = await self._database[collection].delete_one(
            self._tenant_query(organization_id, query)
        )
        return result.deleted_count == 1


class InMemoryCanonicalDatabase:
    def __init__(self) -> None:
        self.collections: dict[str, list[dict[str, Any]]] = {}

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def resolve_identity_profile(self, identity_subject: str) -> dict[str, Any] | None:
        for profile in self.collections.get("employee_profiles", []):
            if profile.get("identity_subject") == identity_subject and profile.get("active", True):
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

    @staticmethod
    def _matches(document: Mapping[str, Any], query: Mapping[str, Any]) -> bool:
        for key, expected in query.items():
            actual = document.get(key)
            if isinstance(expected, Mapping):
                if "$in" in expected:
                    candidates = expected["$in"]
                    if isinstance(actual, (list, set, frozenset)):
                        if not any(item in candidates for item in actual):
                            return False
                    elif actual not in candidates:
                        return False
                elif "$ne" in expected and actual == expected["$ne"]:
                    return False
                else:
                    return False
            elif isinstance(actual, (list, set, frozenset)):
                if expected not in actual:
                    return False
            elif actual != expected:
                return False
        return True

    async def find_many(
        self,
        collection: str,
        organization_id: str,
        query: Mapping[str, Any] | None = None,
        *,
        sort: Sequence[tuple[str, int]] | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        documents = [
            document.copy()
            for document in self.collections.get(collection, [])
            if document.get("organization_id") == organization_id
            and self._matches(document, query or {})
        ]
        for field, direction in reversed(sort or []):
            documents.sort(key=lambda item: str(item.get(field, "")), reverse=direction < 0)
        return documents[skip : skip + limit]

    async def count_documents(
        self, collection: str, organization_id: str, query: Mapping[str, Any] | None = None
    ) -> int:
        return len(
            await self.find_many(collection, organization_id, query, skip=0, limit=1_000_000)
        )

    async def update_one(
        self,
        collection: str,
        organization_id: str,
        query: Mapping[str, Any],
        updates: Mapping[str, Any],
    ) -> bool:
        for document in self.collections.get(collection, []):
            if document.get("organization_id") == organization_id and self._matches(
                document, query
            ):
                document.update(updates)
                return True
        return False

    async def delete_one(
        self, collection: str, organization_id: str, query: Mapping[str, Any]
    ) -> bool:
        for index, document in enumerate(self.collections.get(collection, [])):
            if document.get("organization_id") == organization_id and self._matches(
                document, query
            ):
                self.collections[collection].pop(index)
                return True
        return False
