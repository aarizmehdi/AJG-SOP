"""Exact structured references only. Never infer ownership from prose or filenames."""

from typing import Any

from pydantic import BaseModel

from apps.api.app.services.foundation_store import FoundationStore
from packages.contracts.purge import PurgeGraph

CORE = {
    "policies": "policies",
    "policy_versions": "versions",
    "source_documents": "sources",
    "canonical_sops": "canonicals",
    "raw_parser_results": "raw_results",
    "ingestion_jobs": "jobs",
    "retrieval_chunks": "chunks",
}
PROTECTED = {
    "employee_profiles",
    "organizations",
    "departments",
    "locations",
    "organizational_roles",
    "configuration",
    "settings",
}
INTERNAL = {"policy_purges", "purge_locks"}
REFERENCE_KEYS = {
    "id",
    "_foundation_key",
    "entity_id",
    "policy_id",
    "policy_ids",
    "version_id",
    "version_ids",
    "active_version_id",
    "source_document_id",
    "source_document_ids",
    "source_id",
    "source_ids",
    "document_id",
    "document_ids",
    "chunk_id",
    "chunk_ids",
    "canonical_document_ids",
    "canonical_id",
    "canonical_ids",
    "section_id",
    "section_ids",
    "parent_section_id",
}


def references(value: Any, ids: set[str], key: str = "") -> bool:
    if isinstance(value, dict):
        return any(references(item, ids, str(name)) for name, item in value.items())
    if isinstance(value, list):
        return any(references(item, ids, key) for item in value)
    return key in REFERENCE_KEYS and isinstance(value, str) and value in ids


def store_rows(store: FoundationStore) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {}
    for collection, attribute in CORE.items():
        records = getattr(store, attribute)
        values = (
            [chunk for chunks in records.values() for chunk in chunks]
            if collection == "retrieval_chunks"
            else list(records.values())
        )
        rows[collection] = [v.model_dump(mode="json") for v in values if isinstance(v, BaseModel)]
    for collection in ("audit_events", "chat_messages", "chat_sessions"):
        records = getattr(store, collection)
        values = list(records.values()) if isinstance(records, dict) else records
        rows[collection] = [v.model_dump(mode="json") for v in values]
    return rows


def discover(
    rows: dict[str, list[dict[str, Any]]], org: str, policy: str, known_ids: set[str] | None = None
) -> PurgeGraph:
    ids = {policy, *(known_ids or set())}
    selected: dict[str, list[dict[str, Any]]] = {}
    # Closure discovers orphan sources via their policy/version IDs, not version.source_ids alone.
    changed = True
    while changed:
        changed = False
        for name, documents in rows.items():
            if name in INTERNAL:
                continue
            if any(d.get("organization_id") is None and references(d, ids) for d in documents):
                raise ValueError("An exact linked record has no organization; review required")
            matches = [
                d
                for d in documents
                if d.get("organization_id") == org
                and d.get("action") != "policy.purged"
                and references(d, ids)
            ]
            if matches and name in PROTECTED:
                raise ValueError(
                    f"Protected collection {name} references this policy; review required"
                )
            selected[name] = matches
            for document in matches:
                # Only owned resource rows extend the graph; audit/chat IDs do not.
                if name in CORE:
                    if document.get("policy_id") not in (None, policy):
                        raise ValueError("Shared resource has conflicting policy ownership")
                    if name == "policies" and document.get("id") != policy:
                        raise ValueError("Shared resource links a different policy")
                    for key in ("id", "policy_id", "version_id", "source_document_id"):
                        value = document.get(key)
                        if isinstance(value, str) and value not in ids:
                            ids.add(value)
                            changed = True
                    for key in ("source_document_ids", "canonical_document_ids"):
                        for value in document.get(key, []):
                            if isinstance(value, str) and value not in ids:
                                ids.add(value)
                                changed = True
                    if name == "canonical_sops":
                        for section in document.get("sections", []):
                            value = section.get("id")
                            if isinstance(value, str) and value not in ids:
                                ids.add(value)
                                changed = True

    def row_ids(name: str) -> list[str]:
        return sorted({d["id"] for d in selected.get(name, []) if isinstance(d.get("id"), str)})

    source_ids = set(row_ids("source_documents"))
    version_ids = set(row_ids("policy_versions"))
    for name in CORE:
        for d in selected.get(name, []):
            source_ids.update(d.get("source_document_ids", []))
            if d.get("source_document_id"):
                source_ids.add(d["source_document_id"])
            if d.get("version_id"):
                version_ids.add(d["version_id"])
    return PurgeGraph(
        organization_id=org,
        policy_id=policy,
        version_ids=sorted(version_ids),
        source_ids=sorted(source_ids),
        canonical_ids=row_ids("canonical_sops"),
        chunk_ids=row_ids("retrieval_chunks"),
        entity_ids=sorted(ids),
        records={
            name: [
                {
                    "key": str(d.get("_id", d.get("id", d.get("source_document_id")))),
                    "object_id": type(d.get("_id")).__name__ == "ObjectId",
                }
                for d in documents
            ]
            for name, documents in selected.items()
            if documents
        },
    )


def evict(store: FoundationStore, org: str, policy: str) -> set[str]:
    graph = discover(store_rows(store), org, policy)
    ids = set(graph.entity_ids)
    for attribute in CORE.values():
        records = getattr(store, attribute)
        for key, value in list(records.items()):
            values = value if isinstance(value, list) else [value]
            kept = [
                v
                for v in values
                if not (
                    isinstance(v, BaseModel)
                    and getattr(v, "organization_id", None) == org
                    and references(v.model_dump(mode="json"), ids)
                )
            ]
            if not kept:
                del records[key]
            elif isinstance(value, list):
                records[key] = kept
    for attribute in ("audit_events", "chat_messages"):
        records = getattr(store, attribute)
        records[:] = [
            v
            for v in records
            if v.organization_id != org
            or getattr(v, "action", None) == "policy.purged"
            or not references(v.model_dump(mode="json"), ids)
        ]
    for key, value in list(store.chat_sessions.items()):
        if value.organization_id == org and references(value.model_dump(mode="json"), ids):
            del store.chat_sessions[key]
    for mutation in store.get_mutations().values():

        def owned(item: object) -> bool:
            return (
                isinstance(item, BaseModel)
                and getattr(item, "organization_id", None) == org
                and getattr(item, "action", None) != "policy.purged"
                and references(item.model_dump(mode="json"), ids)
            )

        mutation.upserted = {k: v for k, v in mutation.upserted.items() if not owned(v)}
        mutation.appended[:] = [v for v in mutation.appended if not owned(v)]
    return set(graph.chunk_ids)
