import hashlib
import json
from typing import Any

from fastapi import HTTPException

from apps.api.app.auth.permissions import require_system_admin
from apps.api.app.models.organization import EmployeeProfile
from apps.api.app.repositories.purge_graph import INTERNAL, references
from apps.api.app.repositories.purge_repository import PurgeRepository
from apps.api.app.services.storage_service import ArtifactStore
from packages.contracts.common import utc_now
from packages.contracts.purge import (
    PurgeConfirmation,
    PurgeCounts,
    PurgeGraph,
    PurgePreview,
    PurgeResult,
)
from services.ingestion.indexing.pinecone_index import DerivedRetrievalIndex

CHAT_LIMITATION = (
    "Existing chat messages contain no structured citation provenance. Historical answer text "
    "cannot be deterministically associated with this policy; unrelated chats are retained."
)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


class PolicyPurgeService:
    def __init__(
        self, repository: PurgeRepository, artifacts: ArtifactStore, index: DerivedRetrievalIndex
    ) -> None:
        self.repository = repository
        self.artifacts = artifacts
        self.index = index

    async def _inventory(self, graph: PurgeGraph, title: str, published: bool) -> PurgePreview:
        objects = [
            item
            for source in graph.source_ids
            for item in await self.artifacts.list_source(graph.organization_id, source)
        ]
        vectors = await self.index.policy_vectors(
            graph.organization_id, graph.policy_id, set(graph.version_ids), set(graph.chunk_ids)
        )
        counts = PurgeCounts(
            mongo={k: len(v) for k, v in graph.records.items()},
            r2_objects=len(objects),
            r2_bytes=sum(o.size for o in objects),
            pinecone_vectors=len(vectors),
        )
        token = digest(
            {
                "graph": graph.model_dump(),
                "title": title,
                "published": published,
                "objects": [(o.key, o.size) for o in objects],
                "vectors": sorted(vectors),
            }
        )
        return PurgePreview(
            policy_id=graph.policy_id,
            title=title,
            published=published,
            counts=counts,
            preview_token=token,
            limitations=[CHAT_LIMITATION],
        )

    async def preview(self, profile: EmployeeProfile, policy_id: str) -> PurgePreview:
        require_system_admin(profile)
        operation = await self.repository.operation(profile.organization_id, policy_id)
        if operation:
            if operation["status"] == "complete":
                raise HTTPException(404, "Policy permanently deleted")
            # Only pending operations retain the original confirmation/inventory for safe retries.
            return PurgePreview.model_validate(operation["preview"])
        rows = await self.repository.rows(profile.organization_id)
        policy = next(
            (
                r
                for r in rows.get("policies", [])
                if r.get("id") == policy_id and r.get("organization_id") == profile.organization_id
            ),
            None,
        )
        if policy is None:
            raise HTTPException(404, "Policy not found")
        graph = await self.repository.graph(profile.organization_id, policy_id)
        for source in rows.get("source_documents", []):
            if (
                source.get("organization_id") == profile.organization_id
                and source.get("id") in graph.source_ids
            ):
                for key, uri in source.items():
                    if (
                        key.endswith("_artifact_uri")
                        and uri
                        and not self.artifacts.owns_source_uri(
                            profile.organization_id, source["id"], uri
                        )
                    ):
                        raise HTTPException(
                            409,
                            "Source artifact is outside its exact source prefix; review required",
                        )
        return await self._inventory(
            graph,
            policy["title"],
            policy.get("status") == "active" and bool(policy.get("active_version_id")),
        )

    async def purge(
        self, profile: EmployeeProfile, policy_id: str, confirmation: PurgeConfirmation
    ) -> PurgeResult:
        """Caller holds repository.write_guard through response persistence."""
        require_system_admin(profile)
        org = profile.organization_id
        previous = await self.repository.operation(org, policy_id)
        if confirmation.phrase != "DELETE PERMANENTLY":
            raise HTTPException(422, "Exact permanent deletion confirmation is required")
        if previous and previous["status"] == "complete":
            if (
                previous.get("confirmation_digest")
                and digest(confirmation.model_dump()) != previous["confirmation_digest"]
            ):
                raise HTTPException(409, "Original purge confirmation is required for this retry")
            # Already deleted: no destructive action remains. Do not retain a title
            # or its hash solely to validate a no-op retry.
            await self.repository.finish(org, policy_id)
            return PurgeResult.model_validate(previous["result"]).model_copy(
                update={"status": "already_complete"}
            )
        preview = await self.preview(profile, policy_id)
        if (
            confirmation.title != preview.title
            or confirmation.preview_token != preview.preview_token
        ):
            raise HTTPException(
                409, "Confirmation or preview changed. Preview again before deleting"
            )
        graph = (
            PurgeGraph.model_validate(previous["graph"])
            if previous
            else await self.repository.graph(org, policy_id)
        )
        operation: dict[str, Any] = previous or {
            "graph": graph.model_dump(),
            "preview": preview.model_dump(),
            "actor_id": profile.id,
            "started_at": utc_now().isoformat(),
            "counts": PurgeCounts().model_dump(),
            "stages": {},
        }
        operation["status"] = "running"
        await self.repository.save(org, policy_id, operation)
        # Durable marker makes all workers evict this graph before allowing another request.
        await self.repository.synchronize_cache()
        counts = PurgeCounts.model_validate(operation["counts"])
        stages = operation["stages"]
        stage = "pinecone"
        try:
            if stages.get(stage) != "complete":
                await self.index.purge_policy(
                    org, policy_id, set(graph.version_ids), set(graph.chunk_ids)
                )
                counts.pinecone_vectors = preview.counts.pinecone_vectors
                stages[stage] = "complete"
                await self._checkpoint(org, policy_id, operation, counts)
            stage = "r2"
            if stages.get(stage) != "complete":
                for source in graph.source_ids:
                    await self.artifacts.delete_source(org, source)
                counts.r2_objects = preview.counts.r2_objects
                counts.r2_bytes = preview.counts.r2_bytes
                stages[stage] = "complete"
                await self._checkpoint(org, policy_id, operation, counts)
            stage = "mongo"
            if stages.get(stage) != "complete":
                await self.repository.delete_graph(graph)
                counts.mongo = preview.counts.mongo
                stages[stage] = "complete"
                await self._checkpoint(org, policy_id, operation, counts)
            stage = "verification"
            remaining = await self.verify(graph)
            if any(remaining.values()):
                for resource, stage_name in {
                    "mongo_references": "mongo",
                    "r2_objects": "r2",
                    "pinecone_vectors": "pinecone",
                }.items():
                    if remaining[resource]:
                        stages[stage_name] = "pending"
                raise RuntimeError("Some policy resources remain; retry the purge")
            stages[stage] = "complete"
            result = PurgeResult(
                policy_id=policy_id,
                status="complete",
                counts=counts,
                stages=stages,
                remaining=remaining,
            )
            await self.repository.tombstone(
                org, policy_id, operation["actor_id"], counts.model_dump()
            )
            # Scrub the entire temporary manifest; retain only the minimal audit event.
            await self.repository.finish(org, policy_id)
            return result
        except Exception:
            stages[stage] = "failed"
            operation["status"] = "failed"
            await self._checkpoint(org, policy_id, operation, counts)
            return PurgeResult(
                policy_id=policy_id,
                status="failed",
                counts=counts,
                stages=stages,
                remaining={},
                error=f"{stage} cleanup not verified. Retry this purge.",
            )

    async def _checkpoint(
        self, org: str, policy: str, operation: dict[str, Any], counts: PurgeCounts
    ) -> None:
        operation["counts"] = counts.model_dump()
        await self.repository.save(org, policy, operation)

    async def verify(self, graph: PurgeGraph) -> dict[str, int]:
        rows = await self.repository.rows(graph.organization_id)
        remaining = sum(
            1
            for name, records in rows.items()
            if name not in INTERNAL
            for row in records
            if row.get("action") != "policy.purged" and references(row, set(graph.entity_ids))
        )
        objects = sum(
            [
                len(await self.artifacts.list_source(graph.organization_id, source))
                for source in graph.source_ids
            ]
        )
        vectors = await self.index.policy_vectors(
            graph.organization_id, graph.policy_id, set(graph.version_ids), set(graph.chunk_ids)
        )
        return {
            "mongo_references": remaining,
            "r2_objects": objects,
            "pinecone_vectors": len(vectors),
        }
