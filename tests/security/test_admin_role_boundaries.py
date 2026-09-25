from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from starlette.requests import Request

from apps.api.app.api.admin_policies import CreatePolicyRequest, create_policy
from apps.api.app.api.admin_sources import ReviewUpdate, update_review, upload_source
from apps.api.app.auth.permissions import require_system_admin
from apps.api.app.models.organization import ApplicationRole, EmployeeProfile
from apps.api.app.services.audit_service import AuditService
from apps.api.app.services.foundation_store import FoundationStore
from packages.contracts.access import AccessDimension, AccessMode, AccessScope
from packages.contracts.canonical import CanonicalSection, CanonicalSOP, SourceLocator
from packages.contracts.policy import SOPPolicy, SOPVersion
from packages.contracts.source import SourceDocument, SourceFormat


def access() -> AccessScope:
    return AccessScope(
        departments=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"store"})),
        locations=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"peshawar-main"})),
        roles=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"store_keeper"})),
    )


def profile(role: ApplicationRole) -> EmployeeProfile:
    return EmployeeProfile(
        id=f"user-{role.value}",
        organization_id="ajt",
        identity_subject=f"fixture|{role.value}",
        display_name=role.value,
        email=f"{role.value}@example.test",
        application_roles=frozenset({role}),
        management_departments=frozenset({"store"}),
        management_locations=frozenset({"peshawar-main"}),
        management_roles=frozenset({"store_keeper"}),
    )


class PolicyServiceStub:
    def __init__(self) -> None:
        self.attached: tuple[str, str, str] | None = None
        self.invalidated: tuple[str, str] | None = None

    def create_policy(
        self,
        organization_id: str,
        actor_id: str,
        title: str,
        category: str,
        policy_number: str | None,
    ) -> SOPPolicy:
        del actor_id
        return SOPPolicy(
            id="policy",
            organization_id=organization_id,
            title=title,
            category=category,
            policy_number=policy_number,
        )

    def create_version(
        self,
        organization_id: str,
        actor_id: str,
        policy_id: str,
        version_label: str,
        scope: AccessScope,
        effective_date: object,
    ) -> SOPVersion:
        del actor_id, effective_date
        return SOPVersion(
            id="version",
            organization_id=organization_id,
            policy_id=policy_id,
            version_label=version_label,
            access=scope,
        )

    def attach_source(self, organization_id: str, version_id: str, source_id: str) -> None:
        self.attached = (organization_id, version_id, source_id)

    def invalidate_after_review(self, organization_id: str, version_id: str) -> None:
        self.invalidated = (organization_id, version_id)


class PipelineStub:
    def __init__(self, source: SourceDocument, canonical: CanonicalSOP | None = None) -> None:
        self.source = source
        self.canonical = canonical

    async def ingest(self, **kwargs: object) -> SourceDocument:
        del kwargs
        return self.source

    async def save_review(
        self, source_id: str, canonical_json: str, reviewer_id: str
    ) -> CanonicalSOP:
        del source_id, canonical_json, reviewer_id
        assert self.canonical is not None
        return self.canonical


@pytest.mark.asyncio
async def test_sop_admin_cannot_create_or_upload_but_system_admin_can() -> None:
    sop_admin = profile(ApplicationRole.SOP_ADMIN)
    system_admin = profile(ApplicationRole.SYSTEM_ADMIN)
    with pytest.raises(HTTPException) as denied:
        require_system_admin(sop_admin)
    assert denied.value.status_code == 403

    service = PolicyServiceStub()
    request = Request(
        {
            "type": "http",
            "app": SimpleNamespace(state=SimpleNamespace(policy_service=service)),
        }
    )
    payload = CreatePolicyRequest(
        title="Store SOP",
        category="Operations",
        version_label="1",
        access=access(),
    )
    with pytest.raises(HTTPException) as create_denied:
        await create_policy(request, payload, sop_admin)
    assert create_denied.value.status_code == 403
    created = await create_policy(request, payload, system_admin)
    assert created["policy"]["organization_id"] == "ajt"

    version = SOPVersion(
        id="version",
        organization_id="ajt",
        policy_id="policy",
        version_label="1",
        access=access(),
    )
    source = SourceDocument(
        id="source",
        organization_id="ajt",
        policy_id="policy",
        version_id="version",
        file_name="store.pdf",
        media_type="application/pdf",
        source_format=SourceFormat.PDF,
        sha256="hash",
        original_artifact_uri="fixture://source",
    )
    state = SimpleNamespace(
        foundation_store=FoundationStore(versions={"version": version}),
        ingestion_pipeline=PipelineStub(source),
        policy_service=service,
    )
    upload_request = Request({"type": "http", "app": SimpleNamespace(state=state)})
    file = UploadFile(filename="store.pdf", file=BytesIO(b"pdf"))
    with pytest.raises(HTTPException) as upload_denied:
        await upload_source(
            upload_request,
            sop_admin,
            "policy",
            "version",
            SourceFormat.PDF,
            file,
        )
    assert upload_denied.value.status_code == 403
    uploaded = await upload_source(
        upload_request,
        system_admin,
        "policy",
        "version",
        SourceFormat.PDF,
        file,
    )
    assert uploaded.organization_id == "ajt"
    assert service.attached == ("ajt", "version", "source")


@pytest.mark.asyncio
async def test_review_audit_uses_authenticated_profile_identity() -> None:
    reviewer = profile(ApplicationRole.SOP_ADMIN)
    version = SOPVersion(
        id="version",
        organization_id="ajt",
        policy_id="policy",
        version_label="1",
        access=access(),
    )
    source = SourceDocument(
        id="source",
        organization_id="ajt",
        policy_id="policy",
        version_id="version",
        file_name="store.pdf",
        media_type="application/pdf",
        source_format=SourceFormat.PDF,
        sha256="hash",
        original_artifact_uri="fixture://source",
    )
    canonical = CanonicalSOP(
        id="canonical",
        organization_id="ajt",
        policy_id="policy",
        version_id="version",
        source_document_ids=("source",),
        title="Store SOP",
        sections=[],
    )
    store = FoundationStore(
        versions={"version": version},
        sources={"source": source},
    )
    service = PolicyServiceStub()
    state = SimpleNamespace(
        foundation_store=store,
        ingestion_pipeline=PipelineStub(source, canonical),
        policy_service=service,
        audit_service=AuditService(store),
    )
    request = Request({"type": "http", "app": SimpleNamespace(state=state)})
    result = await update_review(request, "source", ReviewUpdate(canonical=canonical), reviewer)
    assert result.id == "canonical"
    event = store.audit_events[-1]
    assert event.actor_id == reviewer.id
    assert event.organization_id == reviewer.organization_id
    assert event.metadata == {"version_id": "version", "source_id": "source"}


@pytest.mark.asyncio
async def test_sop_admin_cannot_expand_section_scope_during_review() -> None:
    reviewer = profile(ApplicationRole.SOP_ADMIN)
    version = SOPVersion(
        id="version",
        organization_id="ajt",
        policy_id="policy",
        version_label="1",
        access=access(),
    )
    source = SourceDocument(
        id="source",
        organization_id="ajt",
        policy_id="policy",
        version_id="version",
        file_name="store.md",
        media_type="text/markdown",
        source_format=SourceFormat.MARKDOWN,
        sha256="hash",
        original_artifact_uri="fixture://source",
    )
    expanded_scope = AccessScope(
        departments=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"hr"})),
        locations=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"peshawar-main"})),
        roles=AccessDimension(mode=AccessMode.SELECTED, values=frozenset({"store_keeper"})),
    )
    canonical = CanonicalSOP(
        id="canonical",
        organization_id="ajt",
        policy_id="policy",
        version_id="version",
        source_document_ids=("source",),
        title="Store SOP",
        sections=[
            CanonicalSection(
                id="hr",
                stable_key="hr",
                heading="HR",
                heading_level=1,
                heading_path=("HR",),
                blocks=[],
                access=expanded_scope,
                source=SourceLocator(source_document_id="source"),
                content_hash="hash",
            )
        ],
    )
    store = FoundationStore(versions={"version": version}, sources={"source": source})
    state = SimpleNamespace(
        foundation_store=store,
        ingestion_pipeline=PipelineStub(source, canonical),
        policy_service=PolicyServiceStub(),
        audit_service=AuditService(store),
    )
    request = Request({"type": "http", "app": SimpleNamespace(state=state)})

    with pytest.raises(HTTPException, match="management scope") as denied:
        await update_review(request, "source", ReviewUpdate(canonical=canonical), reviewer)

    assert denied.value.status_code == 403
