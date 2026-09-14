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
