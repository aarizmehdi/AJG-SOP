from fastapi import FastAPI

from apps.api.app.services.policy_service import PolicyService
from packages.contracts.access import AccessDimension, AccessMode, AccessScope
from packages.contracts.source import SourceFormat


async def seed_fixture_data(app: FastAPI) -> None:
    service: PolicyService = app.state.policy_service
    policy = service.create_policy(
        "ajt",
        "fixture-system",
        "SYNTHETIC FIXTURE — Store Operations SOP",
        "Store Operations",
        "FIXTURE-SOP-001",
    )
    access = AccessScope(
        departments=AccessDimension(
            mode=AccessMode.SELECTED, values=frozenset({"store"})
        ),
        locations=AccessDimension(
            mode=AccessMode.SELECTED, values=frozenset({"peshawar-main"})
        ),
        roles=AccessDimension(
            mode=AccessMode.SELECTED, values=frozenset({"store_keeper"})
        ),
    )
    version = service.create_version(
        "ajt", "fixture-system", policy.id, "Fixture 1", access
    )
    content = b"""# Store Operations

## 4.3 Damaged Stock Handling

This is synthetic fixture content for architecture testing only.
Isolate a damaged item in the designated holding area and record its condition
in the fixture damage register.

1. Separate the item from saleable stock.
2. Record the item code and observed damage.
3. Keep the record with the isolated fixture item.

## 4.4 Receiving Log

This synthetic fixture requires the store keeper to record received item quantities
in the receiving log.
"""
    source = await app.state.ingestion_pipeline.ingest(
        organization_id="ajt",
        policy_id=policy.id,
        version_id=version.id,
        file_name="synthetic-store-operations.md",
        media_type="text/markdown",
        source_format=SourceFormat.MARKDOWN,
        content=content,
    )
    service.attach_source("ajt", version.id, source.id)
    service.set_access("ajt", "fixture-system", version.id, access)
    service.approve_structure("ajt", "fixture-system", source.id)
    await service.prepare_for_publication("ajt", "fixture-system", version.id)
    service.publish("ajt", "fixture-system", version.id)
