import pytest

from apps.api.app.repositories.database import InMemoryCanonicalDatabase


@pytest.mark.asyncio
async def test_canonical_database_never_crosses_tenant_boundary() -> None:
    database = InMemoryCanonicalDatabase()
    await database.insert_one("policies", "organization-a", {"id": "same", "title": "A"})
    await database.insert_one("policies", "organization-b", {"id": "same", "title": "B"})

    result = await database.get_one("policies", "organization-a", {"id": "same"})

    assert result is not None
    assert result["title"] == "A"
    assert result["organization_id"] == "organization-a"


@pytest.mark.asyncio
async def test_identity_resolution_requires_exact_preprovisioned_uid() -> None:
    database = InMemoryCanonicalDatabase()
    database.collections["employee_profiles"] = [
        {
            "id": "admin",
            "organization_id": "organization-a",
            "identity_subject": "known-firebase-uid",
            "email": "same@example.test",
            "application_roles": ["employee", "system_admin"],
            "active": True,
        }
    ]

    unknown = await database.resolve_identity_profile("unknown-firebase-uid")

    assert unknown is None
    assert len(database.collections["employee_profiles"]) == 1
    assert database.collections["employee_profiles"][0]["identity_subject"] == "known-firebase-uid"
