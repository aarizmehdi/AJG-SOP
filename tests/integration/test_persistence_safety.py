import pytest

from apps.api.app.repositories.foundation_persistence import MongoFoundationPersistence
from apps.api.app.services.foundation_store import FoundationStore
from packages.contracts.common import utc_now
from packages.contracts.policy import AuditEvent


def test_mutation_tracking_isolation():
    """Verify that FoundationStore tracks mutations explicitly."""
    store = FoundationStore()
    event = AuditEvent(
        id="evt-1",
        organization_id="ajt",
        actor_id="user-1",
        action="policy.created",
        entity_type="policy",
        entity_id="pol-1",
        occurred_at=utc_now(),
    )
    store.audit_events.append(event)
    store.mark_appended("audit_events", event)

    mutations = store.get_mutations()
    assert "audit_events" in mutations
    assert len(mutations["audit_events"].appended) == 1
    assert mutations["audit_events"].appended[0].id == "evt-1"

    store.clear_mutations()
    mutations_after = store.get_mutations()
    has_events = (
        "audit_events" in mutations_after and len(mutations_after["audit_events"].appended) > 0
    )
    assert not has_events


@pytest.mark.asyncio
async def test_mongo_persistence_scoped_flush():
    """Verify that flush only operates on tracked mutations, never deleting untracked records."""

    class MockCollection:
        def __init__(self):
            self.docs = {}

        async def replace_one(self, filter_spec, doc, upsert=True):
            key = (filter_spec["organization_id"], filter_spec["_foundation_key"])
            self.docs[key] = doc

        async def update_one(self, filter_spec, update_spec, upsert=True):
            key = (filter_spec["organization_id"], filter_spec["_foundation_key"])
            doc = update_spec.get("$setOnInsert", {})
            self.docs[key] = doc

        async def insert_many(self, docs):
            for doc in docs:
                key = (doc["organization_id"], doc["id"])
                self.docs[key] = doc

        async def delete_many(self, filter_spec):
            pytest.fail("delete_many should NEVER be called during mutation-scoped flush")

    class MockMongoDatabase:
        def __init__(self):
            self.collections = {}

        def __getitem__(self, name):
            if name not in self.collections:
                self.collections[name] = MockCollection()
            return self.collections[name]

    class MockMongoPersistence(MongoFoundationPersistence):
        def __init__(self, db):
            self._database = db

    db = MockMongoDatabase()
    persistence = MockMongoPersistence(db)

    store = FoundationStore()
    event = AuditEvent(
        id="evt-100",
        organization_id="ajt",
        actor_id="user-1",
        action="policy.created",
        entity_type="policy",
        entity_id="pol-100",
        occurred_at=utc_now(),
    )
    store.audit_events.append(event)
    store.mark_appended("audit_events", event)

    await persistence.flush(store)

    audit_coll = db["audit_events"]
    assert ("ajt", "evt-100") in audit_coll.docs
