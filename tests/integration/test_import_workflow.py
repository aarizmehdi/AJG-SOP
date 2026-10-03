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
                b"""---
title: Imported Standard Operating Procedure
policy_number: SOP-IMPORT-01
effective_date: 2026-09-25
---
# Imported Standard Operating Procedure
Imported introduction.
## 1. Overview
1. Follow the verified procedure.
| Role | Responsibility |
| --- | --- |
| Manager | Approve |
""",
                "text/markdown",
            ),
        },
    )
    assert import_res.status_code == 201
    source_doc = import_res.json()
    assert source_doc["policy_id"] == policy_id
    assert source_doc["version_id"] == version_id
    assert source_doc["file_name"] == "original_sop.pdf"
    assert source_doc["media_type"] == "application/pdf"
    assert source_doc["source_format"] == "pdf"
    assert "sources/" in source_doc["original_artifact_uri"]
    assert source_doc["structured_file_name"] == "content.md"
    assert source_doc["structured_media_type"] == "text/markdown"
    assert source_doc["structured_source_format"] == "markdown"
    assert "sources/" in source_doc["structured_artifact_uri"]
    assert source_doc["structured_artifact_uri"] != source_doc["original_artifact_uri"]

    preview = test_client.get(
        f"/api/v1/admin/sources/{source_doc['id']}/original/preview",
        headers=admin_headers,
    )
    assert preview.status_code == 200
    assert preview.json()["kind"] == "pdf"
    assert preview.headers["cache-control"] == "private, no-store"
    assert preview.json()["file_name"] == "original_sop.pdf"
    assert preview.json()["media_type"] == "application/pdf"
    assert "original_artifact_uri" not in preview.json()
    assert test_client.get(preview.json()["url"]).content == b"%PDF-1.4 Test PDF content"
    assert (
        test_client.get(
            f"/api/v1/admin/sources/{source_doc['id']}/original/preview",
            headers={"Authorization": "Fixture employee"},
        ).status_code
        == 403
    )
    assert (
        test_client.get(
            f"/api/v1/policies/{policy_id}/sources/{source_doc['id']}",
            headers={"Authorization": "Fixture employee"},
        ).status_code
        == 404
    )

    original_res = test_client.get(
        f"/api/v1/admin/sources/{source_doc['id']}/original", headers=admin_headers
    )
    assert original_res.status_code == 200
    assert original_res.headers["content-type"] == "application/pdf"
    assert original_res.content == b"%PDF-1.4 Test PDF content"

    review_res = test_client.get(
        f"/api/v1/admin/sources/{source_doc['id']}/review", headers=admin_headers
    )
    assert review_res.status_code == 200
    canonical = review_res.json()["canonical"]
    assert canonical["title"] == "Imported Standard Operating Procedure"
    assert canonical["policy_number"] == "SOP-IMPORT-01"
    assert canonical["effective_date"] == "2026-09-25"
    table = next(
        block["table"]
        for section in canonical["sections"]
        for block in section["blocks"]
        if block["kind"] == "table"
    )
    assert [cell["text"] for cell in table["cells"]] == [
        "Role",
        "Responsibility",
        "Manager",
        "Approve",
    ]

    viewer_res = test_client.get(
        f"/api/v1/admin/policies/{policy_id}/viewer", headers=admin_headers
    )
    assert viewer_res.status_code == 200
    assert viewer_res.json()["policy"]["policy_number"] == "SOP-IMPORT-01"
    assert viewer_res.json()["version"]["effective_date"] == "2026-09-25"


def test_legacy_markdown_only_source_remains_readable(test_client):
    admin_headers = {"Authorization": "Fixture system-admin"}
    created = test_client.post(
        "/api/v1/admin/policies",
        headers=admin_headers,
        json={
            "title": "Legacy Markdown SOP",
            "category": "Operations",
            "version_label": "1.0",
            "access": {
                "departments": {"mode": "all"},
                "locations": {"mode": "all"},
                "roles": {"mode": "all"},
            },
        },
    ).json()
    markdown = b"# Legacy Markdown SOP\n\n## 1. Procedure\nKeep this wording."
    uploaded = test_client.post(
        "/api/v1/admin/sources/upload",
        headers=admin_headers,
        data={
            "policy_id": created["policy"]["id"],
            "version_id": created["version"]["id"],
            "source_format": "markdown",
        },
        files={"file": ("legacy.md", markdown, "text/markdown")},
    )
    assert uploaded.status_code == 201
    source = uploaded.json()
    assert source["file_name"] == "legacy.md"
    assert source["media_type"] == "text/markdown"
    assert source["source_format"] == "markdown"
    assert source["structured_artifact_uri"] is None

    original = test_client.get(
        f"/api/v1/admin/sources/{source['id']}/original", headers=admin_headers
    )
    assert original.status_code == 200
    assert original.headers["content-type"].startswith("text/markdown")
    assert original.content == markdown
    preview = test_client.get(
        f"/api/v1/admin/sources/{source['id']}/original/preview", headers=admin_headers
    )
    assert preview.status_code == 200
    assert preview.json()["kind"] == "missing_pdf"

    before = test_client.get(
        f"/api/v1/admin/sources/{source['id']}/review", headers=admin_headers
    ).json()["canonical"]["id"]
    attached = test_client.post(
        f"/api/v1/admin/sources/{source['id']}/attach-original",
        headers=admin_headers,
        files={"file": ("original.pdf", b"%PDF-1.4 original", "application/pdf")},
    )
    assert attached.status_code == 200
    paired = attached.json()
    assert paired["file_name"] == "original.pdf"
    assert paired["media_type"] == "application/pdf"
    assert paired["source_format"] == "pdf"
    assert paired["structured_artifact_uri"] == source["original_artifact_uri"]
    assert paired["structured_file_name"] == "legacy.md"
    assert paired["structured_media_type"] == "text/markdown"
    assert paired["original_artifact_uri"] != paired["structured_artifact_uri"]
    after = test_client.get(
        f"/api/v1/admin/sources/{source['id']}/review", headers=admin_headers
    ).json()
    assert after["canonical"]["id"] == before
    assert after["version"]["status"] == "extraction_review"


def test_verified_pair_import_retry_reuses_existing_markdown_draft(test_client):
    headers = {"Authorization": "Fixture system-admin"}
    draft = test_client.post(
        "/api/v1/admin/policies",
        headers=headers,
        json={
            "title": "Interrupted pair",
            "category": "Operations",
            "version_label": "1.0",
            "access": {
                "departments": {"mode": "all"},
                "locations": {"mode": "all"},
                "roles": {"mode": "all"},
            },
        },
    ).json()
    markdown = b"# Interrupted pair\n## Procedure\nKeep original wording."
    uploaded = test_client.post(
        "/api/v1/admin/sources/upload",
        headers=headers,
        data={
            "policy_id": draft["policy"]["id"],
            "version_id": draft["version"]["id"],
            "source_format": "markdown",
        },
        files={"file": ("source.md", markdown, "text/markdown")},
    )
    assert uploaded.status_code == 201
    source_id = uploaded.json()["id"]
    canonical_id = test_client.get(
        f"/api/v1/admin/sources/{source_id}/review", headers=headers
    ).json()["canonical"]["id"]

    resumed = test_client.post(
        "/api/v1/admin/sources/import",
        headers=headers,
        data={"policy_id": draft["policy"]["id"], "version_id": draft["version"]["id"]},
        files={
            "original_file": ("authoritative.pdf", b"%PDF-1.4 original", "application/pdf"),
            "structured_file": ("source.md", markdown, "text/markdown"),
        },
    )
    assert resumed.status_code == 201
    assert resumed.json()["id"] == source_id
    assert resumed.json()["structured_artifact_uri"] == uploaded.json()["original_artifact_uri"]
    assert resumed.json()["file_name"] == "authoritative.pdf"
    assert (
        test_client.get(f"/api/v1/admin/sources/{source_id}/review", headers=headers).json()[
            "canonical"
        ]["id"]
        == canonical_id
    )


def test_failed_index_state_is_flushed_on_conflict(test_client, monkeypatch):
    headers = {"Authorization": "Fixture system-admin"}
    draft = test_client.post(
        "/api/v1/admin/policies",
        headers=headers,
        json={
            "title": "Index recovery",
            "category": "Operations",
            "version_label": "1.0",
            "access": {
                "departments": {"mode": "all"},
                "locations": {"mode": "all"},
                "roles": {"mode": "all"},
            },
        },
    ).json()
    source = test_client.post(
        "/api/v1/admin/sources/upload",
        headers=headers,
        data={
            "policy_id": draft["policy"]["id"],
            "version_id": draft["version"]["id"],
            "source_format": "markdown",
        },
        files={
            "file": ("source.md", b"# Recovery\n## Rule\nUse approved content.", "text/markdown")
        },
    ).json()
    approved = test_client.post(
        f"/api/v1/admin/sources/{source['id']}/approve",
        headers=headers,
        json={"confirmed": True},
    )
    assert approved.status_code == 200

    flushed_statuses: list[str] = []

    async def record_flush(store):
        version = store.get_mutations()["policy_versions"].upserted[draft["version"]["id"]]
        flushed_statuses.append(version.status.value)

    monkeypatch.setattr(test_client.app.state.foundation_persistence, "flush", record_flush)
    test_client.app.state.retrieval_index.fail_next_stage = True
    response = test_client.post(
        f"/api/v1/admin/versions/{draft['version']['id']}/prepare-publication",
        headers=headers,
    )
    assert response.status_code == 409
    assert flushed_statuses == ["failed"]


def test_multi_sop_import_does_not_promote_first_number_to_collection(test_client):
    headers = {"Authorization": "Fixture system-admin"}
    draft = test_client.post(
        "/api/v1/admin/policies",
        headers=headers,
        json={
            "title": "Store, Excise & Gate SOP collection",
            "category": "Operations",
            "version_label": "1.0",
            "access": {
                "departments": {"mode": "all"},
                "locations": {"mode": "all"},
                "roles": {"mode": "all"},
            },
        },
    ).json()
    policy_id = draft["policy"]["id"]
    imported = test_client.post(
        "/api/v1/admin/sources/import",
        headers=headers,
        data={"policy_id": policy_id, "version_id": draft["version"]["id"]},
        files={
            "original_file": ("collection.pdf", b"%PDF-1.4 original", "application/pdf"),
            "structured_file": (
                "collection.md",
                b"# Collection\n## **SOP # 25** Dispatch\nFollow dispatch rules.\n"
                b"## 2. SOP # 26 Receipt\nFollow receipt rules.",
                "text/markdown",
            ),
        },
    )
    assert imported.status_code == 201
    viewer = test_client.get(f"/api/v1/admin/policies/{policy_id}/viewer", headers=headers)
    assert viewer.status_code == 200
    assert viewer.json()["policy"]["policy_number"] is None
    sections = viewer.json()["canonicals"][0]["sections"]
    assert [section["policy_number"] for section in sections] == ["SOP # 25", "SOP # 26"]
