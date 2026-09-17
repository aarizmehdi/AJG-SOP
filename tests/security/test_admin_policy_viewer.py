from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from apps.api.app.api.admin_policies import (
    duplicate_sections,
    list_policies,
    policy_viewer,
    prepare_publication,
    version_diff,
)
from apps.api.app.api.admin_sources import get_original, get_review
from apps.api.app.models.organization import ApplicationRole, EmployeeProfile
from apps.api.app.services.foundation_store import FoundationStore
from apps.api.app.services.storage_service import LocalArtifactStore
from packages.contracts.access import AccessDimension, AccessMode, AccessScope
from packages.contracts.canonical import CanonicalSection, CanonicalSOP, SourceLocator
from packages.contracts.policy import SOPPolicy, SOPVersion
from packages.contracts.source import SourceDocument, SourceFormat


def scope(department: str) -> AccessScope:
    return AccessScope(
        departments=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({department})),
        locations=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"lahore"})),
        roles=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"staff"})),
    )


def section(name: str, department: str, page: int) -> CanonicalSection:
    locator = SourceLocator(source_document_id="source", page_start=page)
    return CanonicalSection(
        id=name,
        stable_key=name,
        heading=name,
        heading_level=1,
        heading_path=(name,),
        blocks=[],
        access=scope(department),
        source=locator,
        content_hash=name,
    )


@pytest.mark.asyncio
async def test_admin_viewer_filters_sections_versions_and_private_original(tmp_path: Path) -> None:
    artifacts = LocalArtifactStore(tmp_path)
    uri = await artifacts.put("ajt", "source/original.pdf", b"private")
    store = FoundationStore(
        policies={
            "policy": SOPPolicy(
                id="policy",
                organization_id="ajt",
                title="Store SOP",
                category="store",
                active_version_id="version",
            ),
            "other": SOPPolicy(
                id="other", organization_id="other-org", title="Other SOP", category="other"
            ),
        },
        versions={
            "version": SOPVersion(
                id="version",
                organization_id="ajt",
                policy_id="policy",
                version_label="1",
                access=scope("store"),
                source_document_ids=["source"],
            ),
            "outside": SOPVersion(
                id="outside",
                organization_id="ajt",
                policy_id="policy",
                version_label="2",
                access=scope("hr"),
            ),
        },
        sources={
            "source": SourceDocument(
                id="source",
                organization_id="ajt",
                policy_id="policy",
                version_id="version",
                file_name="store.pdf",
                media_type="application/pdf",
                source_format=SourceFormat.PDF,
                sha256="hash",
                original_artifact_uri=uri,
            ),
        },
        canonicals={
            "source": CanonicalSOP(
                id="canonical",
                organization_id="ajt",
                policy_id="policy",
                version_id="version",
                source_document_ids=("source",),
                title="Store SOP",
                sections=[section("Store", "store", 3), section("HR", "hr", 8)],
            ),
        },
    )
    app = SimpleNamespace(state=SimpleNamespace(foundation_store=store, artifact_store=artifacts))
    request = Request({"type": "http", "app": app})
    admin = EmployeeProfile(
        id="admin",
        organization_id="ajt",
        identity_subject="fixture|admin",
        display_name="Admin",
        email="admin@example.test",
        application_roles=frozenset({ApplicationRole.SOP_ADMIN}),
        management_departments=frozenset({"store"}),
        management_locations=frozenset({"lahore"}),
        management_roles=frozenset({"staff"}),
    )

    listed = await list_policies(request, admin)
    assert [policy["title"] for policy in listed] == ["Store SOP"]
    assert listed[0]["section_count"] == 1
    assert listed[0]["page_count"] == 3
    viewer = await policy_viewer(request, "policy", admin)
    assert [version["id"] for version in viewer["versions"]] == ["version"]
    assert viewer["versions"][0]["source_names"] == ["store.pdf"]
    assert [item["heading"] for item in viewer["canonicals"][0]["sections"]] == ["Store"]
    assert viewer["sources"][0]["original_allowed"] is False
    with pytest.raises(HTTPException) as denied:
        await get_original(request, "source", admin)
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException) as denied_review:
        await get_review(request, "source", admin)
    assert denied_review.value.status_code == 403
    with pytest.raises(HTTPException) as denied_diff:
        await version_diff(request, "version", admin, against="version")
    assert denied_diff.value.status_code == 403
    with pytest.raises(HTTPException) as denied_duplicates:
        await duplicate_sections(request, "version", admin)
    assert denied_duplicates.value.status_code == 403
    with pytest.raises(HTTPException) as denied_publication:
        await prepare_publication(request, "version", admin)
    assert denied_publication.value.status_code == 403
    with pytest.raises(HTTPException) as denied_version:
        await policy_viewer(request, "policy", admin, version_id="outside")
    assert denied_version.value.status_code == 404
    with pytest.raises(HTTPException) as denied_tenant:
        await policy_viewer(request, "other", admin)
    assert denied_tenant.value.status_code == 404
    store.canonicals.pop("source")
    unreviewed = await policy_viewer(request, "policy", admin)
    assert unreviewed["sources"][0]["original_allowed"] is True
    assert (await get_original(request, "source", admin)).body == b"private"
