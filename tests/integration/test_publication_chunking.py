from pathlib import Path

import pytest

from apps.api.app.services.audit_service import AuditService
from apps.api.app.services.foundation_store import FoundationStore
from apps.api.app.services.policy_service import PolicyService
from apps.api.app.services.storage_service import LocalArtifactStore
from packages.contracts.access import AccessDimension, AccessMode, AccessScope
from packages.contracts.policy import VersionStatus
from packages.contracts.source import SourceFormat
from services.ingestion.chunking.semantic_chunker import SectionAwareFixtureChunker
from services.ingestion.embeddings.base import FixtureEmbeddingProvider
from services.ingestion.extractors.fixtures import FixtureDocumentParser
from services.ingestion.indexing.pinecone_index import FixtureRetrievalIndex
from services.ingestion.pipeline import IngestionPipeline
from services.ingestion.structure.canonical_document import Canonicalizer


@pytest.mark.asyncio
async def test_real_publication_pipeline_fixture_mode_stores_valid_chunks(tmp_path: Path) -> None:
    store = FoundationStore()
    index = FixtureRetrievalIndex()
    artifact_store = LocalArtifactStore(tmp_path)
    audit = AuditService(store)
    chunker = SectionAwareFixtureChunker()
    embeddings = FixtureEmbeddingProvider()

    pipeline = IngestionPipeline(FixtureDocumentParser(), Canonicalizer(), artifact_store, store)
    service = PolicyService(store, chunker, embeddings, index, audit)

    policy = service.create_policy(
        "ajt", "admin-1", "Plant Safety Operations", "Operations", "SOP-OPS-2026"
    )

    access_scope = AccessScope(
        departments=AccessDimension(
            mode=AccessMode.SELECTED, values=frozenset({"Operations", "Maintenance"})
        ),
        locations=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"Peshawar"})),
        roles=AccessDimension(mode=AccessMode.ALL),
    )

    # Synthetic English Markdown SOP:
    # 1. Table with an oversized row
    # 2. Nested list
    # 3. Long section exceeding MAX_WORDS
    oversized_desc = (
        "Immediately isolate the containment area, apply neutralizing compound powder evenly "
        "across the spill perimeter, verify that exhaust fans operate at maximum airflow capacity, "
        "deploy protective breathing apparatus for all response personnel, and log the incident "
        "with plant safety officer within one hour of occurrence"
    )
    long_section_words = [f"maintenance_guideline_item_{i}" for i in range(420)]
    long_section_text = " ".join(long_section_words)

    markdown_sop = f"""# Plant Safety Operations
## Chemical Safety Matrix
| Chemical | Storage Location | Emergency Protocol |
|---|---|---|
| Solvent-X | Bay 4 Ventilated Locker | {oversized_desc} |

## Inspection Checklist
1. Pre-operational check
   1. Inspect electrical connections
   2. Verify calibration seal
2. Post-operational log

## Routine Maintenance Procedures
{long_section_text}
"""

    version = service.create_version("ajt", "admin-1", policy.id, "1.0", access_scope)
    source = await pipeline.ingest(
        "ajt",
        policy.id,
        version.id,
        "safety_sop.md",
        "text/markdown",
        SourceFormat.MARKDOWN,
        markdown_sop.encode("utf-8"),
    )

    service.attach_source("ajt", version.id, source.id)
    service.approve_structure("ajt", "admin-1", source.id)
    await service.prepare_for_publication("ajt", "admin-1", version.id)
    await service.publish("ajt", "admin-1", version.id)

    # Verify version state
    assert store.versions[version.id].status is VersionStatus.PUBLISHED
    assert policy.active_version_id == version.id

    # Verify stored chunks
    stored_chunks = store.chunks.get(version.id, [])
    assert len(stored_chunks) >= 3

    # 1. Check ID format: f"{version_id}:{section_id}:{chunk_index}"
    for c in stored_chunks:
        assert c.id.startswith(f"{version.id}:")
        parts = c.id.split(":")
        assert len(parts) >= 3
        assert parts[-1].isdigit()
        assert c.organization_id == "ajt"
        assert c.policy_id == policy.id
        assert c.version_id == version.id
        assert c.publication_status == "published"
        assert c.access == access_scope

    # 2. Check table chunks with oversized row
    table_chunks = [
        c for c in stored_chunks if "Chemical Safety Matrix" in " > ".join(c.heading_path)
    ]
    assert len(table_chunks) >= 1
    for tc in table_chunks:
        # Repeating table header lines
        assert "| Chemical | Storage Location | Emergency Protocol |" in tc.text
        assert "|---|---|---|" in tc.text
        # Row context carried
        assert "Solvent-X" in tc.text

    # Verify all words of the oversized description are recovered (no text loss)
    combined_table_text = " ".join(tc.text for tc in table_chunks)
    for word in oversized_desc.split():
        assert word in combined_table_text

    # 3. Check nested list chunk
    list_chunks = [c for c in stored_chunks if "Inspection Checklist" in " > ".join(c.heading_path)]
    assert len(list_chunks) >= 1
    assert any("Pre-operational check" in lc.text for lc in list_chunks)

    # 4. Check long section chunking
    long_chunks = [
        c for c in stored_chunks if "Routine Maintenance Procedures" in " > ".join(c.heading_path)
    ]
    assert len(long_chunks) >= 2  # 420 words must be split into at least 2 chunks
    for idx, lc in enumerate(long_chunks):
        assert lc.chunk_index == idx
        assert lc.id.endswith(f":{idx}")

    # Verify all maintenance tokens are recovered
    combined_long_text = " ".join(lc.text for lc in long_chunks)
    for w in long_section_words:
        assert w in combined_long_text
