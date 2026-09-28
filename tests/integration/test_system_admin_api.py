import asyncio

from fastapi.testclient import TestClient

from apps.api.app.main import app


def test_system_admin_api_role_and_tenant_boundaries() -> None:
    with TestClient(app) as client:
        system_headers = {"Authorization": "Fixture system-admin"}
        assert client.get("/api/v1/admin/users").status_code == 401
        assert (
            client.get(
                "/api/v1/admin/users", headers={"Authorization": "Fixture employee"}
            ).status_code
            == 403
        )
        assert (
            client.get(
                "/api/v1/admin/users", headers={"Authorization": "Fixture sop-admin"}
            ).status_code
            == 403
        )
        endpoint_responses = {
            endpoint: client.get(f"/api/v1/admin/{endpoint}", headers=system_headers)
            for endpoint in (
                "overview",
                "users",
                "departments",
                "locations",
                "organizational_roles",
                "audit-events",
                "organization",
                "policies",
            )
        }
        assert all(response.status_code == 200 for response in endpoint_responses.values())

        user_id = endpoint_responses["users"].json()["items"][0]["id"]
        policy_id = endpoint_responses["policies"].json()[0]["id"]
        access = client.get(
            f"/api/v1/admin/access/users/{user_id}/policies/{policy_id}",
            headers=system_headers,
        )
        assert access.status_code == 200
        assert isinstance(access.json()["authorized"], bool)

        organization = client.get("/api/v1/admin/organization", headers=system_headers)
        assert organization.status_code == 200
        assert organization.json()["name"] == "Aziz Jan Group"


def test_empty_organization_catalogs_are_valid_empty_states() -> None:
    with TestClient(app) as client:
        for collection in ("departments", "locations", "organizational_roles"):
            client.app.state.database.collections[collection] = []

        headers = {"Authorization": "Fixture system-admin"}
        for endpoint in ("departments", "locations", "organizational_roles"):
            response = client.get(f"/api/v1/admin/{endpoint}", headers=headers)
            assert response.status_code == 200
            assert response.json() == []

        organization = client.get("/api/v1/admin/organization", headers=headers)
        assert organization.status_code == 200
        assert organization.json()["catalog_counts"] == {
            "departments": 0,
            "locations": 0,
            "organizational_roles": 0,
        }


def test_organization_summary_tolerates_legacy_provider_metadata() -> None:
    with TestClient(app) as client:
        record = client.app.state.database.collections["organizations"][0]
        record["auth0_organization_id"] = None

        response = client.get(
            "/api/v1/admin/organization",
            headers={"Authorization": "Fixture system-admin"},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Aziz Jan Group"


def test_non_system_roles_cannot_mutate_users_catalogs_or_read_audit() -> None:
    payload = {
        "display_name": "Privilege Escalation Attempt",
        "email": "escalation@example.test",
        "preferred_language": "english",
        "application_roles": ["employee", "sop_admin", "system_admin"],
        "departments": ["store"],
        "locations": ["peshawar-main"],
        "organizational_roles": ["store_keeper"],
        "management_departments": [],
        "management_locations": [],
        "management_roles": [],
    }
    with TestClient(app) as client:
        for identity in ("employee", "sop-admin"):
            headers = {
                "Authorization": f"Fixture {identity}",
                "Idempotency-Key": f"blocked-{identity}-request",
            }
            assert (
                client.post("/api/v1/admin/users", headers=headers, json=payload).status_code == 403
            )
            assert (
                client.post(
                    "/api/v1/admin/departments",
                    headers=headers,
                    json={"key": "invented", "name": "Invented"},
                ).status_code
                == 403
            )
            assert client.get("/api/v1/admin/audit-events", headers=headers).status_code == 403

        assert (
            client.get(
                "/api/v1/admin/users",
                headers={"Authorization": "Fixture unknown-user"},
            ).status_code
            == 401
        )


def test_system_admin_can_create_employee_from_catalog_values() -> None:
    payload = {
        "display_name": "Controlled Test Employee",
        "email": "controlled.employee@example.test",
        "preferred_language": "english",
        "application_roles": ["employee"],
        "departments": ["store"],
        "locations": ["peshawar-main"],
        "organizational_roles": ["store_keeper"],
        "management_departments": [],
        "management_locations": [],
        "management_roles": [],
    }
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/admin/users",
            headers={
                "Authorization": "Fixture system-admin",
                "Idempotency-Key": "test-0001",
            },
            json=payload,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["user"]["organization_id"] == "ajt"
        assert body["user"]["application_roles"] == ["employee"]
        assert "activation_link" in body

        cross_tenant = client.post(
            "/api/v1/admin/users",
            headers={
                "Authorization": "Fixture system-admin",
                "Idempotency-Key": "test-0002",
            },
            json={**payload, "organization_id": "another-organization"},
        )
        assert cross_tenant.status_code == 422


def test_inactive_or_unknown_catalog_values_cannot_be_assigned() -> None:
    payload = {
        "display_name": "Manipulated User",
        "email": "manipulated@example.test",
        "preferred_language": "english",
        "application_roles": ["employee"],
        "departments": ["invented-department"],
        "locations": ["peshawar-main"],
        "organizational_roles": ["store_keeper"],
        "management_departments": [],
        "management_locations": [],
        "management_roles": [],
    }
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/admin/users",
            headers={
                "Authorization": "Fixture system-admin",
                "Idempotency-Key": "test-0003",
            },
            json=payload,
        )

        assert response.status_code == 422
        assert "Unknown department" in response.json()["detail"]


def test_disabled_membership_rejects_a_stale_verified_identity() -> None:
    payload = {
        "display_name": "Disabled Membership Test",
        "email": "disabled.membership@example.test",
        "preferred_language": "english",
        "application_roles": ["employee"],
        "departments": ["store"],
        "locations": ["peshawar-main"],
        "organizational_roles": ["store_keeper"],
        "management_departments": [],
        "management_locations": [],
        "management_roles": [],
    }
    with TestClient(app) as client:
        system_headers = {
            "Authorization": "Fixture system-admin",
            "Idempotency-Key": "test-0004",
        }
        created = client.post("/api/v1/admin/users", headers=system_headers, json=payload).json()[
            "user"
        ]
        assert (
            client.post(
                f"/api/v1/admin/users/{created['id']}/disable",
                headers={"Authorization": "Fixture system-admin"},
                json={"confirmation_email": ""},
            ).status_code
            == 200
        )

        asyncio.run(
            client.app.state.identity_admin_service.enable_identity(created["identity_subject"])
        )
        stale_session = client.get(
            "/api/v1/profile/me",
            headers={"Authorization": f"Fixture {created['identity_subject']}"},
        )
        assert stale_session.status_code == 403
        assert stale_session.json()["detail"] == "No active membership"
