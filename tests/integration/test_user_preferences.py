import asyncio

import pytest
from fastapi.testclient import TestClient

from apps.api.app.main import app
from apps.api.app.models.organization import ApplicationRole, EmployeeProfile


def _employee(
    client: TestClient, *, legacy: bool = False
) -> tuple[dict[str, object], dict[str, str]]:
    identity = asyncio.run(
        client.app.state.identity_admin_service.create_identity(
            "preferences@example.test", "Preferences Employee"
        )
    )
    record = EmployeeProfile(
        id="preferences-employee",
        organization_id="ajt",
        identity_subject=identity.uid,
        display_name="Preferences Employee",
        email=identity.email,
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
        departments=frozenset({"store"}),
    ).model_dump(mode="json")
    if legacy:
        record.pop("version")
    client.app.state.database.collections["employee_profiles"].append(record)
    return record, {"Authorization": f"Fixture {identity.uid}"}


@pytest.mark.parametrize("legacy", [False, True])
def test_employee_can_persist_and_change_every_language_without_admin_access(legacy: bool) -> None:
    with TestClient(app) as client:
        record, headers = _employee(client, legacy=legacy)
        # A same-ID record in another tenant must never be changed by self-service.
        other = {**record, "organization_id": "other", "identity_subject": "other-identity"}
        client.app.state.database.collections["employee_profiles"].append(other)
        for version, language in enumerate(["english", "urdu", "roman_urdu", "english"], 2):
            response = client.put(
                "/api/v1/profile/language", params={"language": language}, headers=headers
            )
            assert response.status_code == 200, response.text
            assert response.json() == {"preferred_language": language}
            assert record["preferred_language"] == language
            assert record["version"] == version
            # A fresh authenticated request resolves the persisted profile, like refresh/login.
            profile = client.get("/api/v1/profile/me", headers=headers).json()
            assert profile["preferred_language"] == language
            assert profile["application_roles"] == ["employee"]
            assert profile["locations"] == profile["organizational_roles"] == []
        assert other.get("preferred_language") is None
        assert client.get("/api/v1/admin/users", headers=headers).status_code == 403


def test_language_requires_authentication_and_rejects_unsupported_values() -> None:
    with TestClient(app) as client:
        record, headers = _employee(client)
        assert client.put("/api/v1/profile/language?language=urdu").status_code == 401
        assert (
            client.put("/api/v1/profile/language?language=invalid", headers=headers).status_code
            == 422
        )
        assert record["preferred_language"] is None
        assert record["version"] == 1
        record["active"] = False
        assert (
            client.put("/api/v1/profile/language?language=urdu", headers=headers).status_code == 403
        )


def test_language_save_does_not_overwrite_a_concurrently_changed_profile(monkeypatch) -> None:
    with TestClient(app) as client:
        record, headers = _employee(client)
        original = client.app.state.database.update_one

        async def concurrent_update(collection, organization_id, query, updates):
            record["version"] = 2
            record["display_name"] = "Changed by administrator"
            return await original(collection, organization_id, query, updates)

        monkeypatch.setattr(client.app.state.database, "update_one", concurrent_update)
        response = client.put("/api/v1/profile/language?language=urdu", headers=headers)
        assert response.status_code == 409
        assert record["preferred_language"] is None
        assert record["display_name"] == "Changed by administrator"


@pytest.mark.parametrize("omit_optional_fields", [False, True])
def test_admin_can_create_edit_and_assign_optional_user_dimensions(
    omit_optional_fields: bool,
) -> None:
    with TestClient(app) as client:
        headers = {"Authorization": "Fixture system-admin", "Idempotency-Key": "optional-user-001"}
        database = client.app.state.database
        original_locations = database.collections["locations"]
        original_roles = database.collections["organizational_roles"]
        database.collections["locations"] = []
        database.collections["organizational_roles"] = []
        payload = {
            "display_name": "Optional assignments",
            "email": "optional@example.test",
            "application_roles": ["employee"],
            "departments": ["store"],
        }
        if not omit_optional_fields:
            payload.update({"locations": [], "organizational_roles": []})
        created = client.post("/api/v1/admin/users", headers=headers, json=payload)
        assert created.status_code == 201, created.text
        user = created.json()["user"]
        assert user["locations"] == user["organizational_roles"] == []
        # Existing profiles may also predate optimistic version fields.
        stored = next(
            row for row in database.collections["employee_profiles"] if row["id"] == user["id"]
        )
        stored.pop("version")
        edited = client.patch(
            f"/api/v1/admin/users/{user['id']}",
            headers=headers,
            json={**payload, "display_name": "Updated optional assignments", "expected_version": 1},
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["locations"] == edited.json()["organizational_roles"] == []
        assert edited.json()["version"] == 2
        database.collections["locations"] = original_locations
        database.collections["organizational_roles"] = original_roles
        assigned = client.patch(
            f"/api/v1/admin/users/{user['id']}",
            headers=headers,
            json={
                **payload,
                "locations": ["peshawar-main"],
                "organizational_roles": ["store_keeper"],
                "expected_version": 2,
            },
        )
        assert assigned.status_code == 200, assigned.text
        cleared = client.patch(
            f"/api/v1/admin/users/{user['id']}",
            headers=headers,
            json={**payload, "locations": [], "organizational_roles": [], "expected_version": 3},
        )
        assert cleared.status_code == 200, cleared.text
        stale = client.patch(
            f"/api/v1/admin/users/{user['id']}",
            headers=headers,
            json={**payload, "expected_version": 1},
        )
        assert stale.status_code == 409


def test_legacy_assignments_are_replaced_with_exact_current_scope() -> None:
    with TestClient(app) as client:
        headers = {"Authorization": "Fixture system-admin", "Idempotency-Key": "legacy-user-001"}
        payload = {
            "display_name": "Legacy employee",
            "email": "legacy.employee@example.test",
            "application_roles": ["employee"],
            "departments": ["store"],
            "locations": [],
            "organizational_roles": [],
        }
        created = client.post("/api/v1/admin/users", headers=headers, json=payload)
        assert created.status_code == 201, created.text
        user_id = created.json()["user"]["id"]
        stored = next(
            row
            for row in client.app.state.database.collections["employee_profiles"]
            if row["id"] == user_id
        )
        stored.update(
            departments=["operations"],
            locations=["head-office"],
            organizational_roles=["employee"],
        )

        updated = client.patch(
            f"/api/v1/admin/users/{user_id}",
            headers=headers,
            json={**payload, "expected_version": 1},
        )
        assert updated.status_code == 200, updated.text
        for record in (updated.json(), stored):
            assert record["departments"] == ["store"]
            assert record["locations"] == []
            assert record["organizational_roles"] == []


def test_system_admin_can_clear_legacy_scopes_without_losing_application_role() -> None:
    with TestClient(app) as client:
        admin = next(
            row
            for row in client.app.state.database.collections["employee_profiles"]
            if "system_admin" in row["application_roles"]
        )
        admin.update(
            departments=["technology", "operations"],
            locations=["head-office"],
            organizational_roles=["admin"],
            management_departments=["management"],
            management_locations=["head-office"],
            management_roles=["admin"],
        )
        response = client.patch(
            f"/api/v1/admin/users/{admin['id']}",
            headers={"Authorization": "Fixture system-admin"},
            json={
                "display_name": admin["display_name"],
                "email": admin["email"],
                "application_roles": ["employee", "sop_admin", "system_admin"],
                "departments": [],
                "locations": [],
                "organizational_roles": [],
                "management_departments": [],
                "management_locations": [],
                "management_roles": [],
                "expected_version": admin.get("version", 1),
            },
        )
        assert response.status_code == 200, response.text
        for field in (
            "departments",
            "locations",
            "organizational_roles",
            "management_departments",
            "management_locations",
            "management_roles",
        ):
            assert response.json()[field] == admin[field] == []
        assert "system_admin" in response.json()["application_roles"]


def test_sop_admin_can_replace_legacy_management_scope_when_optional_catalogs_are_empty() -> None:
    with TestClient(app) as client:
        admin = next(
            row
            for row in client.app.state.database.collections["employee_profiles"]
            if "sop_admin" in row["application_roles"]
            and "system_admin" not in row["application_roles"]
        )
        admin.update(
            departments=["operations"],
            locations=["head-office"],
            organizational_roles=["manager"],
            management_departments=["operations"],
            management_locations=["head-office"],
            management_roles=["manager"],
        )
        client.app.state.database.collections["locations"] = []
        client.app.state.database.collections["organizational_roles"] = []
        response = client.patch(
            f"/api/v1/admin/users/{admin['id']}",
            headers={"Authorization": "Fixture system-admin"},
            json={
                "display_name": admin["display_name"],
                "email": admin["email"],
                "application_roles": ["employee", "sop_admin"],
                "departments": ["store"],
                "locations": [],
                "organizational_roles": [],
                "management_departments": ["store"],
                "management_locations": [],
                "management_roles": [],
                "expected_version": admin.get("version", 1),
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["management_departments"] == ["store"]
        assert response.json()["management_locations"] == []
        assert response.json()["management_roles"] == []


@pytest.mark.parametrize(
    "field,value",
    [("departments", []), ("locations", ["unknown"]), ("organizational_roles", ["unknown"])],
)
def test_optional_dimensions_do_not_allow_invalid_assignments(field: str, value: list[str]) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/admin/users",
            headers={
                "Authorization": "Fixture system-admin",
                "Idempotency-Key": "invalid-optional-001",
            },
            json={
                "display_name": "Invalid assignments",
                "email": "invalid@example.test",
                "application_roles": ["employee"],
                "departments": ["store"],
                "locations": [],
                "organizational_roles": [],
                field: value,
            },
        )
        assert response.status_code == 422
        if value:
            assert "Unknown" in response.json()["detail"]


@pytest.mark.parametrize(
    "field,key", [("locations", "peshawar-main"), ("organizational_roles", "store_keeper")]
)
def test_optional_dimensions_still_reject_new_inactive_assignments(field: str, key: str) -> None:
    with TestClient(app) as client:
        item = next(
            row for row in client.app.state.database.collections[field] if row["key"] == key
        )
        item["active"] = False
        response = client.post(
            "/api/v1/admin/users",
            headers={
                "Authorization": "Fixture system-admin",
                "Idempotency-Key": "inactive-optional-001",
            },
            json={
                "display_name": "Inactive assignment",
                "email": "inactive@example.test",
                "application_roles": ["employee"],
                "departments": ["store"],
                "locations": [],
                "organizational_roles": [],
                field: [key],
            },
        )
        assert response.status_code == 422
        assert "Inactive" in response.json()["detail"]
