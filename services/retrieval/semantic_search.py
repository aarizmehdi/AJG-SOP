from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

import anyio
from pinecone import Pinecone

from apps.api.app.models.organization import EmployeeProfile
from packages.contracts.canonical import RetrievalChunk
from packages.contracts.retrieval import CandidateChannel, RetrievalCandidate
from services.ingestion.embeddings.base import EmbeddingProvider


class SemanticCandidateRetriever(ABC):
    @abstractmethod
    async def search(
        self,
        query: str,
        profile: EmployeeProfile,
        eligible_chunks: Sequence[RetrievalChunk],
        limit: int,  # noqa: E501
    ) -> list[RetrievalCandidate]:
        raise NotImplementedError


class FixtureSemanticRetriever(SemanticCandidateRetriever):
    def __init__(self, embeddings: EmbeddingProvider) -> None:
        self._embeddings = embeddings

    async def search(
        self,
        query: str,
        profile: EmployeeProfile,
        eligible_chunks: Sequence[RetrievalChunk],
        limit: int,  # noqa: E501
    ) -> list[RetrievalCandidate]:
        if not eligible_chunks:
            return []
        query_vector = await self._embeddings.embed_query(query)
        vectors = await self._embeddings.embed_documents([chunk.text for chunk in eligible_chunks])
        scored = [
            (chunk, sum(left * right for left, right in zip(query_vector, vector, strict=True)))
            for chunk, vector in zip(eligible_chunks, vectors, strict=True)
        ]
        scored.sort(key=lambda item: (-item[1], item[0].id))
        return [
            RetrievalCandidate(
                tenant_id=chunk.organization_id,
                organization_id=chunk.organization_id,
                chunk_id=chunk.id,
                channel=CandidateChannel.SEMANTIC,
                score=score,
                rank=rank,
                text=chunk.text,
                policy_number=chunk.policy_number,
                heading_path=chunk.heading_path,
                allowed_roles=list(chunk.access.roles.values),
                department=next(iter(chunk.access.departments.values)) if chunk.access.departments.values else None,
                location=next(iter(chunk.access.locations.values)) if chunk.access.locations.values else None,
            )
            for rank, (chunk, score) in enumerate(scored[:limit], start=1)
            if score > 0
        ]


class PineconeSemanticRetriever(SemanticCandidateRetriever):
    """Live semantic adapter; authorization is encoded in the query filter before search."""

    def __init__(
        self,
        api_key: str,
        index_name: str,
        namespace_prefix: str,
        embeddings: EmbeddingProvider,
        *,
        index: Any | None = None,
    ) -> None:
        self._index: Any = index or Pinecone(api_key=api_key).Index(index_name)
        self._namespace_prefix = namespace_prefix
        self._embeddings = embeddings

    async def search(
        self,
        query: str,
        profile: EmployeeProfile,
        eligible_chunks: Sequence[RetrievalChunk],
        limit: int,  # noqa: E501
    ) -> list[RetrievalCandidate]:
        if not eligible_chunks:
            return []
        organization_id = profile.organization_id
        vector = await self._embeddings.embed_query(query)
        active_version_ids = list({chunk.version_id for chunk in eligible_chunks})
        namespace = f"{self._namespace_prefix}--{self._safe_tenant(organization_id)}"

        filter_expr = pinecone_authorization_filter(
            organization_id=organization_id,
            active_version_ids=active_version_ids,
            departments=list(profile.departments) if profile.departments else [],
            locations=list(profile.locations) if profile.locations else [],
            roles=list(profile.organizational_roles) if profile.organizational_roles else [],
        )

        response = await anyio.to_thread.run_sync(
            lambda: self._index.query(
                namespace=namespace,
                vector=vector,
                top_k=limit,
                include_metadata=True,
                filter=filter_expr,
            )
        )
        matches = getattr(response, "matches", [])
        return [
            RetrievalCandidate(
                tenant_id=organization_id,
                organization_id=organization_id,
                chunk_id=str(match.id),
                channel=CandidateChannel.SEMANTIC,
                score=float(match.score),
                rank=rank,
                text=match.metadata.get("text") if match.metadata else None,
                policy_number=match.metadata.get("policy_number") if match.metadata else None,
                heading_path=tuple(match.metadata.get("heading_path", []))
                if match.metadata
                else None,  # noqa: E501
                allowed_roles=match.metadata.get("roles", []) if match.metadata else [],
                department=match.metadata.get("department") if match.metadata else None,
                location=match.metadata.get("location") if match.metadata else None,
                publication_state=match.metadata.get("publication_status", "published")
                if match.metadata
                else "published",  # noqa: E501
            )
            for rank, match in enumerate(matches, start=1)
        ]

    @staticmethod
    def _safe_tenant(organization_id: str) -> str:
        return "".join(
            character
            for character in organization_id.lower()
            if character.isalnum() or character == "-"
        )


def pinecone_authorization_filter(
    organization_id: str,
    active_version_ids: list[str],
    departments: list[str],
    locations: list[str],
    roles: list[str],
) -> dict[str, object]:
    """Mandatory pre-retrieval metadata filter for the live semantic adapter."""
    return {
        "$and": [
            {"organization_id": {"$eq": organization_id}},
            {"version_id": {"$in": active_version_ids}},
            {"publication_status": {"$eq": "published"}},
            {
                "$or": [
                    {"departments_mode": {"$eq": "all"}},
                    {"departments": {"$in": departments}},
                ]
            },
            {
                "$or": [
                    {"locations_mode": {"$eq": "all"}},
                    {"locations": {"$in": locations}},
                ]
            },
            {
                "$or": [
                    {"roles_mode": {"$eq": "all"}},
                    {"roles": {"$in": roles}},
                ]
            },
        ]
    }
