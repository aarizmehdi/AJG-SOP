from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

import anyio
from pinecone import Pinecone

from packages.contracts.canonical import RetrievalChunk
from packages.contracts.retrieval import CandidateChannel, RetrievalCandidate
from services.ingestion.embeddings.base import EmbeddingProvider


class SemanticCandidateRetriever(ABC):
    @abstractmethod
    async def search(
        self, query: str, eligible_chunks: Sequence[RetrievalChunk], limit: int
    ) -> list[RetrievalCandidate]:
        raise NotImplementedError


class FixtureSemanticRetriever(SemanticCandidateRetriever):
    def __init__(self, embeddings: EmbeddingProvider) -> None:
        self._embeddings = embeddings

    async def search(
        self, query: str, eligible_chunks: Sequence[RetrievalChunk], limit: int
    ) -> list[RetrievalCandidate]:
        if not eligible_chunks:
            return []
        vectors = await self._embeddings.embed([query, *(chunk.text for chunk in eligible_chunks)])
        query_vector = vectors[0]
        scored = [
            (chunk, sum(left * right for left, right in zip(query_vector, vector, strict=True)))
            for chunk, vector in zip(eligible_chunks, vectors[1:], strict=True)
        ]
        scored.sort(key=lambda item: (-item[1], item[0].id))
        return [
            RetrievalCandidate(
                organization_id=chunk.organization_id,
                chunk_id=chunk.id,
                channel=CandidateChannel.SEMANTIC,
                score=score,
                rank=rank,
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
    ) -> None:
        self._index: Any = Pinecone(api_key=api_key).Index(index_name)
        self._namespace_prefix = namespace_prefix
        self._embeddings = embeddings

    async def search(
        self, query: str, eligible_chunks: Sequence[RetrievalChunk], limit: int
    ) -> list[RetrievalCandidate]:
        if not eligible_chunks:
            return []
        organization_id = eligible_chunks[0].organization_id
        if any(chunk.organization_id != organization_id for chunk in eligible_chunks):
            raise PermissionError("Semantic corpus cannot cross organizations")
        vector = (await self._embeddings.embed([query]))[0]
        eligible_ids = [chunk.id for chunk in eligible_chunks]
        namespace = f"{self._namespace_prefix}--{self._safe_tenant(organization_id)}"
        response = await anyio.to_thread.run_sync(
            lambda: self._index.query(
                namespace=namespace,
                vector=vector,
                top_k=limit,
                filter={
                    "$and": [
                        {"organization_id": {"$eq": organization_id}},
                        {"publication_status": {"$eq": "published"}},
                        {"chunk_id": {"$in": eligible_ids}},
                    ]
                },
            )
        )
        matches = getattr(response, "matches", [])
        return [
            RetrievalCandidate(
                organization_id=organization_id,
                chunk_id=str(match.id),
                channel=CandidateChannel.SEMANTIC,
                score=float(match.score),
                rank=rank,
            )
            for rank, match in enumerate(matches, start=1)
            if str(match.id) in eligible_ids
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
