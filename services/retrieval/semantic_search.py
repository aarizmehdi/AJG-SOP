import json
import math
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
        self,
        query: str,
        eligible_chunks: Sequence[RetrievalChunk],
        limit: int,
    ) -> list[RetrievalCandidate]:
        raise NotImplementedError


class FixtureSemanticRetriever(SemanticCandidateRetriever):
    def __init__(self, embeddings: EmbeddingProvider) -> None:
        self._embeddings = embeddings

    async def search(
        self,
        query: str,
        eligible_chunks: Sequence[RetrievalChunk],
        limit: int,
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
                department=next(iter(chunk.access.departments.values))
                if chunk.access.departments.values
                else None,  # noqa: E501
                location=next(iter(chunk.access.locations.values))
                if chunk.access.locations.values
                else None,  # noqa: E501
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
        eligible_chunks: Sequence[RetrievalChunk],
        limit: int,
    ) -> list[RetrievalCandidate]:
        if not eligible_chunks:
            return []

        organization_id = eligible_chunks[0].organization_id
        if any(chunk.organization_id != organization_id for chunk in eligible_chunks):
            raise PermissionError("Semantic corpus cannot cross organizations")
        vector = await self._embeddings.embed_query(query)
        namespace = f"{self._namespace_prefix}--{self._safe_tenant(organization_id)}"
        # Every partition contains only pre-authorized IDs. Never broaden to a
        # policy/tenant-only filter when the eligible corpus is large.
        by_id = {chunk.id: chunk for chunk in eligible_chunks}
        batches: list[list[str]] = []
        batch: list[str] = []
        size = 0
        for chunk_id in by_id:
            item_size = (
                len(json.dumps(chunk_id).encode("utf-8"))
                + len(json.dumps(by_id[chunk_id].version_id).encode("utf-8"))
                + 2
            )
            if item_size > 2000:
                raise ValueError("Chunk identifier exceeds the semantic filter budget")
            if batch and (len(batch) >= 500 or size + item_size > 24000):
                batches.append(batch)
                batch, size = [], 0
            batch.append(chunk_id)
            size += item_size
        if batch:
            batches.append(batch)
        scores: dict[str, float] = {}
        for ids in batches:
            allowed_ids = set(ids)
            versions = sorted({by_id[i].version_id for i in ids})
            filter_expr = {
                "$and": [
                    {"organization_id": {"$eq": organization_id}},
                    {"publication_status": {"$eq": "published"}},
                    {"chunk_id": {"$in": ids}},
                    {"version_id": {"$in": versions}},
                ]
            }
            if len(json.dumps(filter_expr).encode("utf-8")) > 30000:
                raise ValueError("Semantic authorization filter exceeds its byte budget")
            response = await anyio.to_thread.run_sync(
                lambda: self._index.query(  # noqa: B023 - awaited before advancing partition
                    namespace=namespace,
                    vector=vector,
                    top_k=limit,
                    filter=filter_expr,  # noqa: B023
                )
            )
            for match in getattr(response, "matches", []):
                chunk_id, score = str(match.id), float(match.score)
                if chunk_id in allowed_ids and math.isfinite(score):
                    scores[chunk_id] = max(scores.get(chunk_id, -math.inf), score)
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]
        return [
            RetrievalCandidate(
                tenant_id=organization_id,
                organization_id=organization_id,
                chunk_id=chunk_id,
                channel=CandidateChannel.SEMANTIC,
                score=score,
                rank=rank,
            )
            for rank, (chunk_id, score) in enumerate(ranked, 1)
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
    chunk_ids: list[str],
    departments: list[str],
    locations: list[str],
    roles: list[str],
    is_organization_wide_reader: bool = False,
) -> dict[str, object]:
    """Mandatory pre-retrieval metadata filter for the live semantic adapter."""
    base_filter: list[dict[str, object]] = [
        {"organization_id": {"$eq": organization_id}},
        {"version_id": {"$in": active_version_ids}},
        {"publication_status": {"$eq": "published"}},
        {"chunk_id": {"$in": chunk_ids}},
    ]

    if not is_organization_wide_reader:
        base_filter.extend(
            [
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
        )

    return {"$and": base_filter}
