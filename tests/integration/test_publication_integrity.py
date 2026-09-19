from pathlib import Path

import pytest

from apps.api.app.services.audit_service import AuditService
from apps.api.app.services.foundation_store import FoundationStore
from apps.api.app.services.policy_service import PolicyService, PublicationError
from apps.api.app.services.storage_service import LocalArtifactStore
from packages.contracts.access import AccessDimension, AccessMode, AccessScope
from packages.contracts.policy import SectionChangeKind, VersionStatus
from packages.contracts.source import SourceFormat
from services.ingestion.chunking.semantic_chunker import SectionAwareFixtureChunker
from services.ingestion.embeddings.base import FixtureEmbeddingProvider
from services.ingestion.extractors.fixtures import FixtureDocumentParser
from services.ingestion.indexing.pinecone_index import FixtureRetrievalIndex
from services.ingestion.pipeline import IngestionPipeline
from services.ingestion.structure.canonical_document import Canonicalizer


def access() -> AccessScope:
    return AccessScope(
        departments=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"store"})),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"store_keeper"})),
    )


async def build_version(
    root: Path,
    service: PolicyService,
    pipeline: IngestionPipeline,
    organization_id: str,
    policy_id: str,
    label: str,
    content: bytes,
) -> str:
    version = service.create_version(organization_id, "admin", policy_id, label, access())
    source = await pipeline.ingest(
        organization_id,
        policy_id,
        version.id,
        f"{label}.md",
        "text/markdown",
        SourceFormat.MARKDOWN,
        content,
    )
    assert all(
        section.access == version.access
        for section in pipeline.store.canonicals[source.id].sections
    )
    service.attach_source(organization_id, version.id, source.id)
    service.set_access(organization_id, "admin", version.id, access())
    service.approve_structure(organization_id, "admin", source.id)
    return version.id


@pytest.mark.asyncio
async def test_failed_new_index_keeps_current_version_active(tmp_path: Path) -> None:
    store = FoundationStore()
    index = FixtureRetrievalIndex()
    pipeline = IngestionPipeline(
        FixtureDocumentParser(), Canonicalizer(), LocalArtifactStore(tmp_path), store
    )
    service = PolicyService(
        store,
        SectionAwareFixtureChunker(),
        FixtureEmbeddingProvider(),
        index,
        AuditService(store),
    )
    policy = service.create_policy("ajt", "admin", "Test policy", "Operations", None)
    first_id = await build_version(
        tmp_path, service, pipeline, "ajt", policy.id, "1", b"# Policy\n## 1 Rule\nOld text"
    )
    await service.prepare_for_publication("ajt", "admin", first_id)
    service.publish("ajt", "admin", first_id)
    second_id = await build_version(
        tmp_path,
        service,
        pipeline,
        "ajt",
        policy.id,
        "2",
        b"# Policy\n## 1 Rule\nNew text\n## 2 Added\nAdded text",
    )
    index.fail_next_stage = True

    with pytest.raises(PublicationError):
        await service.prepare_for_publication("ajt", "admin", second_id)

    assert policy.active_version_id == first_id
    assert store.versions[first_id].status is VersionStatus.PUBLISHED
    assert store.versions[second_id].status is VersionStatus.FAILED


@pytest.mark.asyncio
async def test_version_diff_reports_changed_and_added_sections(tmp_path: Path) -> None:
    store = FoundationStore()
    pipeline = IngestionPipeline(
        FixtureDocumentParser(), Canonicalizer(), LocalArtifactStore(tmp_path), store
    )
    service = PolicyService(
        store,
        SectionAwareFixtureChunker(),
        FixtureEmbeddingProvider(),
        FixtureRetrievalIndex(),
        AuditService(store),
    )
    policy = service.create_policy("ajt", "admin", "Test policy", "Operations", None)
    old_id = await build_version(
        tmp_path, service, pipeline, "ajt", policy.id, "1", b"# Policy\n## 1 Rule\nOld text"
    )
    new_id = await build_version(
        tmp_path,
        service,
        pipeline,
        "ajt",
        policy.id,
        "2",
        b"# Policy\n## 1 Rule\nNew text\n## 2 Added\nAdded text",
    )

    changes = service.diff("ajt", old_id, new_id)

    assert {change.kind for change in changes} == {
        SectionChangeKind.CHANGED,
        SectionChangeKind.ADDED,
    }
