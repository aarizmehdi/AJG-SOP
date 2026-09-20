import pytest
from fastapi.testclient import TestClient

from apps.api.app.main import app


@pytest.fixture
def test_client():
    with TestClient(app) as client:
        yield client


def test_import_workflow_requires_system_admin(test_client):
    """Verify that importing SOP source requires system_admin role."""
    headers = {"Authorization": "Fixture employee"}
    response = test_client.post(
        "/api/v1/admin/sources/import",
        headers=headers,
        data={"policy_id": "pol-1", "version_id": "ver-1"},
        files={
            "original_file": ("test.pdf", b"%PDF-1.4...", "application/pdf"),
            "structured_file": ("test.md", b"# Title\nContent", "text/markdown"),
        },
    )
    assert response.status_code == 403
    assert "System administrator role required" in response.json()["detail"]


def test_import_workflow_success(test_client):
    """Verify system-admin can import pre-verified PDF + Markdown source."""
    admin_headers = {"Authorization": "Fixture system-admin"}

    pol_res = test_client.post(
        "/api/v1/admin/policies",
        headers=admin_headers,
        json={
            "title": "Imported SOP Policy",
            "category": "Operations",
            "version_label": "v1.0",
            "access": {
                "departments": {"mode": "all"},
                "locations": {"mode": "all"},
                "roles": {"mode": "all"},
            },
        },
    )
    assert pol_res.status_code == 201
    created = pol_res.json()
    policy_id = created["policy"]["id"]
    version_id = created["version"]["id"]

    import_res = test_client.post(
        "/api/v1/admin/sources/import",
        headers=admin_headers,
        data={"policy_id": policy_id, "version_id": version_id},
        files={
            "original_file": ("original_sop.pdf", b"%PDF-1.4 Test PDF content", "application/pdf"),
            "structured_file": (
                "content.md",
                b"# Standard Operating Procedure\n\n## Section 1: Overview\nImported content.",
                "text/markdown",
            ),
        },
    )
    assert import_res.status_code == 201
    source_doc = import_res.json()
    assert source_doc["policy_id"] == policy_id
    assert source_doc["version_id"] == version_id
    assert "sources/" in source_doc["original_artifact_uri"]
