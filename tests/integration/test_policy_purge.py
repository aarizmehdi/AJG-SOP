from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from apps.api.app.auth.identity import FIXTURE_PROFILES
from apps.api.app.main import app
from apps.api.app.repositories.purge_graph import discover, references, store_rows
from apps.api.app.repositories.purge_repository import PurgeRepository
from apps.api.app.services.audit_service import AuditService
from apps.api.app.services.foundation_store import FoundationStore
from apps.api.app.services.policy_purge_service import PolicyPurgeService
from apps.api.app.services.policy_service import PolicyService
from apps.api.app.services.storage_service import LocalArtifactStore, S3ArtifactStore
from packages.contracts.access import AccessDimension, AccessMode, AccessScope
from packages.contracts.purge import PurgeConfirmation
from packages.contracts.source import SourceFormat
from services.ingestion.chunking.semantic_chunker import SectionAwareFixtureChunker
from services.ingestion.embeddings.base import FixtureEmbeddingProvider
from services.ingestion.extractors.fixtures import FixtureDocumentParser
from services.ingestion.indexing.pinecone_index import FixtureRetrievalIndex, PineconeRetrievalIndex
from services.ingestion.pipeline import IngestionPipeline
from services.ingestion.structure.canonical_document import Canonicalizer
from services.retrieval.authorization_filter import AuthorizationFilter
from services.retrieval.fusion import ReciprocalRankFusion
from services.retrieval.lexical_search import FixtureLexicalRetriever
from services.retrieval.reranker import FixtureReranker
from services.retrieval.retriever import RetrievalService
from services.retrieval.semantic_search import FixtureSemanticRetriever

SYSTEM = FIXTURE_PROFILES["fixture|system-admin"]


async def setup(root: Path):
    store = FoundationStore()
    storage = LocalArtifactStore(root)
    index = FixtureRetrievalIndex()
    service = PolicyService(
        store, SectionAwareFixtureChunker(), FixtureEmbeddingProvider(), index, AuditService(store)
    )
    pipeline = IngestionPipeline(FixtureDocumentParser(), Canonicalizer(), storage, store)
    access = AccessScope(
        departments=AccessDimension(mode=AccessMode.ALL),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )
    target = service.create_policy("ajt", "admin", "AJG test policy", "Operations", None)
    other = service.create_policy("ajt", "admin", "AJG retained policy", "Operations", None)
    for policy, labels in [(target, ["old", "current", "staged"]), (other, ["1"])]:
        for label in labels:
            version = service.create_version("ajt", "admin", policy.id, label, access)
            source = await pipeline.ingest(
                "ajt",
                policy.id,
                version.id,
                f"{label}.md",
                "text/markdown",
                SourceFormat.MARKDOWN,
                (
                    f"# {policy.title}\n## 1 Stock\nInspect returned stock before acceptance. "
                    f"Revision {label}."
                ).encode(),
            )
            service.attach_source("ajt", version.id, source.id)
            service.approve_structure("ajt", "admin", source.id)
            await service.prepare_for_publication("ajt", "admin", version.id)
            if label != "staged":
                await service.publish("ajt", "admin", version.id)
    legacy = next(s for s in store.sources.values() if s.policy_id == target.id)
    legacy.original_artifact_uri = await storage.put(
        "ajt", f"sources/{legacy.id}/legacy.pdf", b"%PDF-old"
    )
    await storage.put("ajt", f"sources/{legacy.id}/orphan/unreferenced.md", b"legacy content")
    repository = PurgeRepository(store)
    purge = PolicyPurgeService(repository, storage, index)
    retrieval = RetrievalService(
        store,
        AuthorizationFilter(store),
        FixtureLexicalRetriever(),
        FixtureSemanticRetriever(FixtureEmbeddingProvider()),
        ReciprocalRankFusion(),
        FixtureReranker(),
    )
    repository.cache_listener = retrieval.evict_chunks
    return store, storage, index, repository, purge, retrieval, target, other


async def confirmed(service, policy_id):
    preview = await service.preview(SYSTEM, policy_id)
    return preview, PurgeConfirmation(
        title=preview.title, phrase="DELETE PERMANENTLY", preview_token=preview.preview_token
    )


async def test_preview_cascade_idempotence_and_unrelated_policy_survives(tmp_path):
    store, storage, index, repo, purge, retrieval, target, other = await setup(tmp_path)
    snapshot = store_rows(store)
    files = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    preview, confirmation = await confirmed(purge, target.id)
    graph = await repo.graph("ajt", target.id)
    assert store_rows(store) == snapshot and repo._operations == {}
    assert preview.published and preview.counts.mongo["policy_versions"] == 3
    assert preview.counts.r2_objects >= 11 and preview.counts.pinecone_vectors == 3
    before = await retrieval.retrieve(SYSTEM, "returned stock", 10)
    assert {e.policy_id for e in before} == {target.id, other.id}
    async with repo.write_guard():
        result = await purge.purge(SYSTEM, target.id, confirmation)
    assert result.status == "complete", result
    assert result.remaining == {"mongo_references": 0, "r2_objects": 0, "pinecone_vectors": 0}
    assert await purge.verify(graph) == result.remaining
    for source in graph.source_ids:
        assert await storage.list_source("ajt", source) == []
    after = await retrieval.retrieve(SYSTEM, "returned stock", 10)
    assert {e.policy_id for e in after} == {other.id}
    retained_files = sorted(
        p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()
    )
    assert retained_files and set(retained_files) < set(files)
    for mutation in store.get_mutations().values():
        assert all(
            not references(v.model_dump(mode="json"), set(graph.entity_ids))
            for v in mutation.upserted.values()
        )
    again = await purge.purge(SYSTEM, target.id, confirmation)
    assert again.status == "already_complete" and again.counts == result.counts
    assert {e.policy_id for e in await retrieval.retrieve(SYSTEM, "stock", 10)} == {other.id}
    tombstones = [e for e in store.audit_events if e.action == "policy.purged"]
    assert len(tombstones) == 1 and set(tombstones[0].metadata) == {"counts"}
    operation = await repo.operation("ajt", target.id)
    assert "title" not in str(operation) and "graph" not in operation and "preview" not in operation


async def test_failure_blocks_exposure_and_retry_finishes(tmp_path, monkeypatch):
    store, storage, index, repo, purge, retrieval, target, other = await setup(tmp_path)
    preview, confirmation = await confirmed(purge, target.id)
    real_delete = storage.delete_source
    calls = 0

    async def fail_second(org, source):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("Injected storage outage")
        return await real_delete(org, source)

    monkeypatch.setattr(storage, "delete_source", fail_second)
    failed = await purge.purge(SYSTEM, target.id, confirmation)
    assert failed.status == "failed" and failed.stages["pinecone"] == "complete"
    assert target.id not in store.policies
    assert {e.policy_id for e in await retrieval.retrieve(SYSTEM, "returned stock", 10)} == {
        other.id
    }
    assert (await purge.preview(SYSTEM, target.id)) == preview
    monkeypatch.setattr(storage, "delete_source", real_delete)
    result = await purge.purge(SYSTEM, target.id, confirmation)
    assert result.status == "complete"
    assert result.counts.r2_objects == preview.counts.r2_objects
    assert result.counts.pinecone_vectors == 3


async def test_pinecone_failure_still_blocks_policy_and_preserves_retry_graph(
    tmp_path, monkeypatch
):
    store, storage, index, repo, purge, retrieval, target, other = await setup(tmp_path)
    _, confirmation = await confirmed(purge, target.id)
    original = index.purge_policy

    async def fail(*args):
        raise RuntimeError("Injected Pinecone outage")

    monkeypatch.setattr(index, "purge_policy", fail)
    result = await purge.purge(SYSTEM, target.id, confirmation)
    assert result.status == "failed" and result.stages["pinecone"] == "failed"
    assert target.id not in store.policies
    assert {e.policy_id for e in await retrieval.retrieve(SYSTEM, "stock", 10)} == {other.id}
    assert (await repo.operation("ajt", target.id))["graph"]["source_ids"]
    monkeypatch.setattr(index, "purge_policy", original)
    assert (await purge.purge(SYSTEM, target.id, confirmation)).status == "complete"


async def test_wrong_confirmations_and_changed_inventory_do_not_delete(tmp_path):
    store, storage, index, repo, purge, retrieval, target, other = await setup(tmp_path)
    preview, confirmation = await confirmed(purge, target.id)
    for update in [{"title": "wrong"}, {"phrase": "yes"}, {"preview_token": "wrong"}]:
        with pytest.raises(HTTPException):
            await purge.purge(SYSTEM, target.id, confirmation.model_copy(update=update))
    assert target.id in store.policies and not repo._operations
    source = next(s for s in store.sources.values() if s.policy_id == target.id)
    await storage.put("ajt", f"sources/{source.id}/late.json", b"late artifact")
    with pytest.raises(HTTPException, match="409"):
        await purge.purge(SYSTEM, target.id, confirmation)
    assert target.id in store.policies and not repo._operations


def test_http_role_org_boundaries_and_preview_read_only():
    with TestClient(app) as client:
        system = {"Authorization": "Fixture system-admin"}
        policy = client.get("/api/v1/admin/policies", headers=system).json()[0]
        url = f"/api/v1/admin/policies/{policy['id']}"
        snapshot = store_rows(client.app.state.foundation_store)
        assert client.get(url + "/purge-preview").status_code == 401
        for role in ["employee", "sop-admin"]:
            headers = {"Authorization": f"Fixture {role}"}
            assert client.get(url + "/purge-preview", headers=headers).status_code == 403
            assert (
                client.post(
                    url + "/purge",
                    headers=headers,
                    json={
                        "title": policy["title"],
                        "phrase": "DELETE PERMANENTLY",
                        "preview_token": "x",
                    },
                ).status_code
                == 403
            )
        foreign = client.app.state.foundation_store.policies[policy["id"]].model_copy(
            update={"id": "foreign", "organization_id": "other"}
        )
        client.app.state.foundation_store.policies["foreign"] = foreign
        assert (
            client.get("/api/v1/admin/policies/foreign/purge-preview", headers=system).status_code
            == 404
        )
        assert (
            client.post(
                "/api/v1/admin/policies/foreign/purge",
                headers=system,
                json={"title": foreign.title, "phrase": "DELETE PERMANENTLY", "preview_token": "x"},
            ).status_code
            == 404
        )
        del client.app.state.foundation_store.policies["foreign"]
        preview = client.get(url + "/purge-preview", headers=system)
        assert (
            preview.status_code == 200 and store_rows(client.app.state.foundation_store) == snapshot
        )
        body = {
            "title": policy["title"],
            "phrase": "DELETE PERMANENTLY",
            "preview_token": preview.json()["preview_token"],
        }
        assert (
            client.post(
                url + "/purge", headers=system, json={**body, "source_ids": ["other"]}
            ).status_code
            == 422
        )
        response = client.post(url + "/purge", headers=system, json=body)
        assert response.status_code == 200 and response.json()["status"] == "complete"
        assert client.get(url + "/viewer", headers=system).status_code == 404
        assert (
            client.post(url + "/purge", headers=system, json=body).json()["status"]
            == "already_complete"
        )


def test_graph_discovers_unattached_sources_and_exact_nested_references():
    rows = {
        "policies": [{"organization_id": "ajt", "id": "p"}],
        "source_documents": [
            {"organization_id": "ajt", "id": "s", "policy_id": "p", "version_id": "v"}
        ],
        "raw_parser_results": [{"organization_id": "ajt", "source_document_id": "s"}],
        "audit_events": [
            {"organization_id": "ajt", "id": "a", "metadata": {"source_document_id": "s"}},
            {"organization_id": "ajt", "id": "unrelated", "metadata": {"text": "p"}},
        ],
        "chat_messages": [
            {"organization_id": "ajt", "id": "m", "citations": [{"policy_id": "p"}]},
            {"organization_id": "ajt", "id": "retained", "content": "p"},
        ],
        "unknown_collection": [{"organization_id": "ajt", "id": "u", "version_id": "v"}],
        "employee_profiles": [{"organization_id": "ajt", "id": "employee", "display_name": "p"}],
        "source_foreign": [{"organization_id": "other", "id": "sf", "policy_id": "p"}],
    }
    graph = discover(rows, "ajt", "p")
    assert graph.source_ids == ["s"] and graph.version_ids == ["v"]
    assert len(graph.records["audit_events"]) == 1 and len(graph.records["chat_messages"]) == 1
    assert len(graph.records["unknown_collection"]) == 1
    assert "employee_profiles" not in graph.records and "source_foreign" not in graph.records
    rows["source_documents"].append({"organization_id": "ajt", "id": "s", "policy_id": "other"})
    with pytest.raises(ValueError, match="conflicting"):
        discover(rows, "ajt", "p")


async def test_local_prefix_traversal_and_other_tenant_survive(tmp_path):
    store = LocalArtifactStore(tmp_path)
    await store.put("ajt", "sources/s/orphan.json", b"one")
    await store.put("ajt", "sources/sibling/original.pdf", b"two")
    other = await store.put("other", "sources/s/original.pdf", b"three")
    with pytest.raises(ValueError):
        await store.delete_source("ajt", "../s")
    deleted = await store.delete_source("ajt", "s")
    assert len(deleted) == 1 and deleted[0].size == 3
    assert await store.get("other", other) == b"three"
    assert len(await store.list_source("ajt", "sibling")) == 1
    assert await store.delete_source("ajt", "s") == []


async def test_pinecone_full_inventory_deletes_stale_versions_and_all_pages(monkeypatch):
    class Index:
        def __init__(self):
            self.rows = {
                f"chunk-{n}": {
                    "organization_id": "ajt",
                    "policy_id": "target",
                    "version_id": f"unknown-{n}",
                    "publication_status": "failed",
                }
                for n in range(1010)
            }
            self.rows["other"] = {"organization_id": "ajt", "policy_id": "other"}

        def list(self, namespace):
            assert namespace == "ajg--ajt"
            keys = sorted(self.rows)
            for i in range(0, len(keys), 100):
                yield SimpleNamespace(
                    vectors=[SimpleNamespace(id=key) for key in keys[i : i + 100]]
                )

        def fetch(self, ids, namespace):
            return SimpleNamespace(
                vectors={
                    key: SimpleNamespace(metadata=self.rows[key]) for key in ids if key in self.rows
                }
            )

        def delete(self, ids, namespace):
            assert len(ids) <= 1000 and namespace == "ajg--ajt"
            for key in ids:
                self.rows.pop(key, None)

    async def no_wait(_):
        pass

    monkeypatch.setattr("services.ingestion.indexing.pinecone_index.anyio.sleep", no_wait)
    fake = Index()
    adapter = PineconeRetrievalIndex("unused", "existing", "ajg", index=fake)
    assert len(await adapter.policy_vectors("ajt", "target", set(), set())) == 1010
    assert await adapter.purge_policy("ajt", "target", set(), set()) == 1010
    assert fake.rows == {"other": {"organization_id": "ajt", "policy_id": "other"}}
    assert await adapter.purge_policy("ajt", "target", set(), set()) == 0


async def test_s3_prefix_pagination_and_partial_delete_errors():
    class Client:
        def __init__(self):
            self.rows = {
                "ajt/sources/s/original.pdf": 10,
                "ajt/sources/s/orphan.md": 4,
                "ajt/sources/sibling/keep.pdf": 9,
            }

        def get_paginator(self, _):
            return self

        def paginate(self, Bucket, Prefix):
            assert Bucket == "private" and Prefix == "ajt/sources/s/"
            for key, size in self.rows.items():
                if key.startswith(Prefix):
                    yield {"Contents": [{"Key": key, "Size": size}]}

        def delete_objects(self, Bucket, Delete):
            for item in Delete["Objects"]:
                self.rows.pop(item["Key"], None)
            return {}

    adapter = S3ArtifactStore.__new__(S3ArtifactStore)
    adapter._bucket = "private"
    adapter._client = Client()
    objects = await adapter.list_source("ajt", "s")
    assert len(objects) == 2 and sum(o.size for o in objects) == 14
    assert await adapter.delete_source("ajt", "s") == objects
    assert adapter._client.rows == {"ajt/sources/sibling/keep.pdf": 9}


async def test_answer_generating_during_purge_is_never_released(tmp_path):
    from apps.api.app.services.assistant_service import AssistantService, VerificationError
    from packages.contracts.common import Language
    from services.assistant.answer_generator import FixtureLLMProvider
    from services.assistant.answerability import FixtureAnswerabilityGate
    from services.assistant.citations import CitationValidator
    from services.assistant.grounding import GroundingVerifier

    store, storage, index, repo, purge, retrieval, target, other = await setup(tmp_path)
    _, confirmation = await confirmed(purge, target.id)

    class PurgingProvider(FixtureLLMProvider):
        async def generate(self, question, evidence, language):
            response = await super().generate(question, evidence, language)
            assert (await purge.purge(SYSTEM, target.id, confirmation)).status == "complete"
            return response

    assistant = AssistantService(
        store,
        retrieval,
        FixtureAnswerabilityGate(),
        PurgingProvider(),
        CitationValidator(),
        GroundingVerifier(),
    )
    with pytest.raises(VerificationError, match="no longer available"):
        await assistant.answer(SYSTEM, "returned stock", Language.ENGLISH)
    assert all(message.role.value != "assistant" for message in store.chat_messages)


async def test_mongo_cascade_uses_exact_row_identity_tenant_and_retry_graph(tmp_path):
    from bson import ObjectId

    store, storage, index, repo, purge, retrieval, target, other = await setup(tmp_path)
    initial = store_rows(store)
    for rows in initial.values():
        for row in rows:
            row["_id"] = ObjectId()
    initial["unknown_links"] = [
        {"_id": ObjectId(), "organization_id": "ajt", "metadata": {"policy_id": target.id}},
        {"_id": ObjectId(), "organization_id": "other", "metadata": {"policy_id": target.id}},
        {"_id": ObjectId(), "organization_id": "ajt", "text": target.id},
    ]

    class Cursor:
        def __init__(self, values):
            self.values = values

        async def to_list(self, _):
            return self.values

    class Collection:
        def __init__(self, name):
            self.name = name

        def find(self, query):
            assert query == {"$or": [{"organization_id": "ajt"}, {"organization_id": None}]}
            return Cursor([d for d in initial.get(self.name, []) if d["organization_id"] == "ajt"])

        async def delete_many(self, query):
            assert query["organization_id"] == "ajt" and set(query) == {"organization_id", "_id"}
            before = initial[self.name]
            initial[self.name] = [
                d
                for d in before
                if d["organization_id"] != "ajt" or d["_id"] not in query["_id"]["$in"]
            ]
            return SimpleNamespace(deleted_count=len(before) - len(initial[self.name]))

    class Database:
        async def list_collection_names(self):
            return list(initial)

        def __getitem__(self, name):
            return Collection(name)

    mongo = PurgeRepository(store, Database())
    graph = await mongo.graph("ajt", target.id)
    assert len(graph.records["unknown_links"]) == 1
    # Simulate process death halfway through Mongo deletion. The durable graph still
    # finds remaining records even when policy/version metadata was already removed.
    initial["policies"] = [r for r in initial["policies"] if r["id"] != target.id]
    initial["policy_versions"] = [
        r for r in initial["policy_versions"] if r["policy_id"] != target.id
    ]
    await mongo.delete_graph(graph)
    for documents in initial.values():
        for row in documents:
            assert row["organization_id"] != "ajt" or not references(row, set(graph.entity_ids))
    assert len(initial["unknown_links"]) == 2
    assert initial["policies"][0]["id"] == other.id
    assert all(count == 0 for count in (await mongo.delete_graph(graph)).values())


async def test_mongo_write_lease_serializes_workers_and_releases_after_failure():
    import asyncio

    from pymongo.errors import DuplicateKeyError

    class Locks:
        def __init__(self):
            self.row = None

        async def find_one_and_update(self, query, update, **kwargs):
            if self.row is not None:
                raise DuplicateKeyError("Busy fixture lease")
            self.row = {"_id": query["_id"], **update["$set"]}
            return self.row

        async def delete_one(self, query):
            assert self.row["owner"] == query["owner"]
            self.row = None

        async def update_one(self, query, update):
            assert self.row["owner"] == query["owner"]
            self.row.update(update["$set"])
            return SimpleNamespace(matched_count=1)

    database = SimpleNamespace(purge_locks=Locks())
    first = PurgeRepository(FoundationStore(), database)
    second = PurgeRepository(FoundationStore(), database)
    entered = asyncio.Event()

    async def worker():
        async with second.write_guard():
            entered.set()

    async with first.write_guard():
        task = asyncio.create_task(worker())
        await asyncio.sleep(0.05)
        assert not entered.is_set()
    await task
    assert entered.is_set() and database.purge_locks.row is None
    with pytest.raises(ExceptionGroup):
        async with first.write_guard():
            raise ValueError("Injected writer failure")
    assert database.purge_locks.row is None
