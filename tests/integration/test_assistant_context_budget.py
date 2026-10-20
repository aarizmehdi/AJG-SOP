"""Context allocation preserves authorized candidates within the existing budget."""

import pytest
from fastapi.testclient import TestClient

from apps.api.app.auth.identity import FIXTURE_PROFILES
from apps.api.app.main import app
from packages.contracts.access import AccessDimension, AccessMode


@pytest.mark.asyncio
async def test_long_early_chunks_do_not_starve_later_authorized_section():
    with TestClient(app) as client:
        state = client.app.state
        profile = FIXTURE_PROFILES["fixture|employee"]
        service = state.retrieval_service
        prototype = service.authorization.eligible_chunks(profile)[0]
        chunks = [
            prototype.model_copy(update={"id": f"context-{i}", "text": "Early material. " * 500})
            for i in range(6)
        ]
        chunks += [
            prototype.model_copy(
                update={
                    "id": "exact-later",
                    "text": "RGP must be signed by the listed departments. " * 25,
                }
            ),
            prototype.model_copy(update={"id": "last", "text": "Final authorized evidence."}),
        ]
        denied = prototype.model_copy(
            update={
                "id": "denied",
                "text": "CONFIDENTIAL_MUST_NOT_ENTER_CONTEXT",
                "access": prototype.access.model_copy(
                    update={
                        "departments": AccessDimension(
                            mode=AccessMode.SELECTED, values={"private-board"}
                        )
                    }
                ),
            }
        )
        state.foundation_store.chunks[prototype.version_id] = [*chunks, denied]
        items = [service._evidence("Fixture policy", c, 1) for c in [*chunks, denied]]
        context = await service.assistant_context(profile, items)
        assert [c.chunk_id for c in context] == [c.id for c in chunks]
        assert sum(len(c.full_text) for c in context) <= 16000
        assert all(0 < len(c.full_text) <= 5000 for c in context)
        assert context[-2].full_text == chunks[-2].text
        assert context[-1].full_text == chunks[-1].text
        assert not any("CONFIDENTIAL" in c.full_text for c in context)
        assert await service.revalidate_evidence(profile, context)
        state.foundation_store.policies[prototype.policy_id].active_version_id = "replaced-version"
        assert not await service.revalidate_evidence(profile, context)
