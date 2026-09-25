from types import SimpleNamespace

from packages.contracts.access import AccessDimension, AccessMode, AccessScope
from packages.contracts.canonical import RetrievalChunk, SourceLocator
from services.ingestion.indexing.pinecone_index import PineconeRetrievalIndex


class FakeIndex:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, dict[str, object]]] = {}

    def upsert(self, vectors: list[dict[str, object]], namespace: str) -> SimpleNamespace:
        self.records[namespace] = {str(record["id"]): record for record in vectors}
        return SimpleNamespace(upserted_count=len(vectors))

    def fetch(self, ids: list[str], namespace: str) -> SimpleNamespace:
        records = self.records.get(namespace, {})
        return SimpleNamespace(
            vectors={
                record_id: SimpleNamespace(metadata=records[record_id]["metadata"])
                for record_id in ids
                if record_id in records
            }
        )

    def update(self, id: str, namespace: str, set_metadata: dict[str, object]) -> None:
        metadata = self.records[namespace][id]["metadata"]
        assert isinstance(metadata, dict)
        metadata.update(set_metadata)


def chunk() -> RetrievalChunk:
    return RetrievalChunk(
        id="chunk-1",
        organization_id="ajt",
        policy_id="policy-1",
        version_id="version-1",
        source_document_id="source-1",
        section_id="section-1",
        heading_path=("Policy", "Rule"),
        policy_number="1",
        text="Authorized policy text",
        access=AccessScope(
            departments=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"store"})),
            locations=AccessDimension(mode=AccessMode.ALL),
            roles=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"employee"})),
        ),
        source=SourceLocator(source_document_id="source-1", block_anchor="line-2"),
        chunk_index=0,
        publication_status="staged",
    )


async def test_pinecone_stage_verify_and_activate_preserves_security_metadata() -> None:
    fake = FakeIndex()
    index = PineconeRetrievalIndex(
        "secret-not-used",
        "aziz-jan-sop",
        "aziz-jan-trust",
        index=fake,
    )
    item = chunk()

    revision = await index.stage("ajt", "version-1", [item], [[0.1, 0.2]])

    assert revision == "pinecone:aziz-jan-trust--ajt:version-1"
    assert await index.verify("ajt", "version-1", {"chunk-1"})
    metadata = fake.records["aziz-jan-trust--ajt"]["chunk-1"]["metadata"]
    assert metadata == {
        "organization_id": "ajt",
        "chunk_id": "chunk-1",
        "policy_id": "policy-1",
        "version_id": "version-1",
        "section_id": "section-1",
        "publication_status": "staged",
        "departments_mode": "selected",
        "departments": ["store"],
        "locations_mode": "all",
        "locations": [],
        "roles_mode": "selected",
        "roles": ["employee"],
        "text": "Authorized policy text",
    }

    await index.activate("ajt", "version-1", [item])

    assert metadata["publication_status"] == "published"
