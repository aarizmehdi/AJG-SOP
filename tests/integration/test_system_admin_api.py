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
        assert client.get("/api/v1/admin/users", headers=system_headers).status_code == 200
        assert client.get("/api/v1/admin/audit-events", headers=system_headers).status_code == 200


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
