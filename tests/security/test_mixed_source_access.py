from pathlib import Path

from apps.api.app.models.organization import ApplicationRole, EmployeeProfile
from apps.api.app.services.foundation_store import FoundationStore
from apps.api.app.services.policy_reader_service import PolicyReaderService
from apps.api.app.services.storage_service import LocalArtifactStore
from packages.contracts.access import AccessDimension, AccessMode, AccessScope
from packages.contracts.canonical import (
    BlockKind,
    CanonicalBlock,
    CanonicalSection,
    CanonicalSOP,
    SourceLocator,
)
from packages.contracts.policy import PolicyStatus, SOPPolicy, SOPVersion, VersionStatus
from packages.contracts.source import SourceDocument, SourceFormat
from services.retrieval.authorization_filter import AuthorizationFilter


def scope(department: str) -> AccessScope:
    return AccessScope(
        departments=AccessDimension(
            mode=AccessMode.SELECTED, values=frozenset({department})
        ),
        locations=AccessDimension(mode=AccessMode.ALL),
        roles=AccessDimension(mode=AccessMode.ALL),
    )


def section(section_id: str, department: str) -> CanonicalSection:
    locator = SourceLocator(source_document_id="source", page_start=1, page_end=1)
    return CanonicalSection(
        id=section_id,
        stable_key=section_id,
        heading=section_id,
        heading_level=1,
        heading_path=(section_id,),
        blocks=[
            CanonicalBlock(
                id=f"block-{section_id}",
                kind=BlockKind.PARAGRAPH,
                text="Policy content",
                source=locator,
            )
        ],
        access=scope(department),
        source=locator,
        content_hash=section_id,
    )


async def test_mixed_access_original_is_not_exposed(tmp_path: Path) -> None:
    artifact_store = LocalArtifactStore(tmp_path)
    uri = await artifact_store.put("ajt", "sources/source/original/policy.pdf", b"private")
    store = FoundationStore(
        policies={
            "policy": SOPPolicy(
                id="policy",
                organization_id="ajt",
                title="Policy",
                category="Operations",
                status=PolicyStatus.ACTIVE,
                active_version_id="version",
            )
        },
        versions={
            "version": SOPVersion(
                id="version",
                organization_id="ajt",
                policy_id="policy",
                version_label="1",
                status=VersionStatus.PUBLISHED,
                access=scope("store"),
                source_document_ids=["source"],
            )
        },
        sources={
            "source": SourceDocument(
                id="source",
                organization_id="ajt",
                policy_id="policy",
                version_id="version",
                file_name="policy.pdf",
                media_type="application/pdf",
                source_format=SourceFormat.PDF,
                sha256="hash",
                original_artifact_uri=uri,
            )
        },
        canonicals={
            "source": CanonicalSOP(
                id="canonical",
                organization_id="ajt",
                policy_id="policy",
                version_id="version",
                source_document_ids=("source",),
                title="Policy",
                sections=[section("store-section", "store"), section("hr-section", "hr")],
                approved=True,
            )
        },
    )
    profile = EmployeeProfile(
        id="employee",
        organization_id="ajt",
        identity_subject="fixture|employee",
        display_name="Employee",
        email="employee@example.test",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
        departments=frozenset({"store"}),
    )
    reader = PolicyReaderService(store, AuthorizationFilter(store), artifact_store)

    document = reader.read_policy(profile, "policy")
    original = await reader.read_original(profile, "policy", "source")

    assert document is not None
    assert [item.section_id for item in document.sections] == ["store-section"]
    assert not document.original_download_allowed
    assert original is None
