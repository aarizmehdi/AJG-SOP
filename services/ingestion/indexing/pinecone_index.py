from abc import ABC, abstractmethod
from collections.abc import Sequence
from functools import partial
from typing import Any

import anyio
from pinecone import Pinecone

from packages.contracts.canonical import RetrievalChunk


class DerivedRetrievalIndex(ABC):
    @abstractmethod
    async def stage(
        self,
        organization_id: str,
        version_id: str,
        chunks: Sequence[RetrievalChunk],
        vectors: Sequence[Sequence[float]],
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    async def verify(self, organization_id: str, version_id: str, expected_ids: set[str]) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def activate(
        self,
        organization_id: str,
        version_id: str,
        chunks: Sequence[RetrievalChunk],
    ) -> None:
        raise NotImplementedError


class FixtureRetrievalIndex(DerivedRetrievalIndex):
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], dict[str, tuple[RetrievalChunk, list[float]]]] = {}
        self.fail_next_stage = False
        self.fail_next_activate = False

    async def stage(
        self,
        organization_id: str,
        version_id: str,
        chunks: Sequence[RetrievalChunk],
        vectors: Sequence[Sequence[float]],
    ) -> str:
        if self.fail_next_stage:
            self.fail_next_stage = False
            raise RuntimeError("Injected indexing failure")
        if any(chunk.organization_id != organization_id for chunk in chunks):
            raise PermissionError("Cannot stage a chunk from another organization")
        self.records[(organization_id, version_id)] = {
            chunk.id: (chunk, list(vector)) for chunk, vector in zip(chunks, vectors, strict=True)
        }
        return f"fixture:{organization_id}:{version_id}"

    async def verify(self, organization_id: str, version_id: str, expected_ids: set[str]) -> bool:
        return set(self.records.get((organization_id, version_id), {})) == expected_ids

    async def activate(
        self,
        organization_id: str,
        version_id: str,
        chunks: Sequence[RetrievalChunk],
    ) -> None:
        if self.fail_next_activate:
            self.fail_next_activate = False
            raise RuntimeError("Injected index activation failure")
        records = self.records.get((organization_id, version_id), {})
        if set(records) != {chunk.id for chunk in chunks}:
            raise RuntimeError("Cannot activate an unverified fixture index revision")


class PineconeRetrievalIndex(DerivedRetrievalIndex):
    """Derived index adapter. Canonical text remains in MongoDB."""

    def __init__(
        self,
        api_key: str,
        index_name: str,
        namespace_prefix: str,
        *,
        index: Any | None = None,
    ) -> None:
        self._index: Any = index or Pinecone(api_key=api_key).Index(index_name)
        self._namespace_prefix = namespace_prefix

    def namespace(self, organization_id: str) -> str:
        safe_tenant = "".join(
            char for char in organization_id.lower() if char.isalnum() or char == "-"
        )
        return f"{self._namespace_prefix}--{safe_tenant}"

    async def stage(
        self,
        organization_id: str,
        version_id: str,
        chunks: Sequence[RetrievalChunk],
        vectors: Sequence[Sequence[float]],
    ) -> str:
        records = [
            {
                "id": chunk.id,
                "values": list(vector),
                "metadata": {
                    "organization_id": organization_id,
                    "chunk_id": chunk.id,
                    "policy_id": chunk.policy_id,
                    "version_id": version_id,
                    "section_id": chunk.section_id,
                    "publication_status": "staged",
                    "departments_mode": chunk.access.departments.mode.value,
                    "departments": list(chunk.access.departments.values),
                    "locations_mode": chunk.access.locations.mode.value,
                    "locations": list(chunk.access.locations.values),
                    "roles_mode": chunk.access.roles.mode.value,
                    "roles": list(chunk.access.roles.values),
                    "text": chunk.text,
                },
            }
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        await anyio.to_thread.run_sync(
            lambda: self._index.upsert(vectors=records, namespace=self.namespace(organization_id))
        )
        return f"pinecone:{self.namespace(organization_id)}:{version_id}"

    async def verify(self, organization_id: str, version_id: str, expected_ids: set[str]) -> bool:
        response = await anyio.to_thread.run_sync(
            lambda: self._index.fetch(
                ids=list(expected_ids), namespace=self.namespace(organization_id)
            )
        )
        vectors = getattr(response, "vectors", {})
        return set(vectors) == expected_ids and all(
            getattr(vector, "metadata", {}).get("version_id") == version_id
            and getattr(vector, "metadata", {}).get("publication_status") == "staged"
            for vector in vectors.values()
        )

    async def activate(
        self,
        organization_id: str,
        version_id: str,
        chunks: Sequence[RetrievalChunk],
    ) -> None:
        namespace = self.namespace(organization_id)
        for chunk in chunks:
            if chunk.organization_id != organization_id or chunk.version_id != version_id:
                raise PermissionError("Cannot activate a chunk outside the requested version")
            await anyio.to_thread.run_sync(
                partial(
                    self._index.update,
                    id=chunk.id,
                    namespace=namespace,
                    set_metadata={"publication_status": "published"},
                )
            )
        expected_ids = {chunk.id for chunk in chunks}
        for _ in range(6):
            response = await anyio.to_thread.run_sync(
                lambda: self._index.fetch(ids=list(expected_ids), namespace=namespace)
            )
            vectors = getattr(response, "vectors", {})
            if set(vectors) == expected_ids and all(
                getattr(vector, "metadata", {}).get("publication_status") == "published"
                for vector in vectors.values()
            ):
                return
            await anyio.sleep(0.5)
        raise RuntimeError("Published Pinecone metadata could not be verified")
