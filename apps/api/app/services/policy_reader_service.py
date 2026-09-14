from apps.api.app.models.organization import EmployeeProfile
from apps.api.app.services.foundation_store import FoundationStore
from apps.api.app.services.storage_service import ArtifactStore
from packages.contracts.canonical import BlockKind, CanonicalSection
from packages.contracts.policy import PolicyStatus, SOPPolicy, SOPVersion
from packages.contracts.retrieval import PolicyReaderDocument, PolicyReaderSection
from packages.contracts.source import SourceDocument
from services.retrieval.authorization_filter import AuthorizationFilter


class PolicyReaderService:
    def __init__(
        self,
        store: FoundationStore,
        authorization: AuthorizationFilter,
        artifacts: ArtifactStore,
    ) -> None:
        self.store = store
        self.authorization = authorization
        self.artifacts = artifacts

    def read_policy(
        self, profile: EmployeeProfile, policy_id: str
    ) -> PolicyReaderDocument | None:
        resolved = self._active(profile, policy_id)
        if not resolved:
            return None
        policy, version = resolved
        employee_scope = self.authorization.employee_scope(profile)
        sections = [
            section
            for source_id in version.source_document_ids
            if source_id in self.store.canonicals
            for section in self.store.canonicals[source_id].sections
            if section.access.allows(employee_scope)
        ]
        if not sections:
            return None
        return PolicyReaderDocument(
            policy_id=policy.id,
            title=policy.title,
            category=policy.category,
            version_label=version.version_label,
            sections=[
                self._reader_section(profile.organization_id, policy.id, version.id, item)
                for item in sections
            ],
            original_download_allowed=all(
                self._source_fully_authorized(profile, source_id)
                for source_id in version.source_document_ids
            ),
        )

    async def read_original(
        self, profile: EmployeeProfile, policy_id: str, source_id: str
    ) -> tuple[SourceDocument, bytes] | None:
        resolved = self._active(profile, policy_id)
        if not resolved:
            return None
        _, version = resolved
        source = self.store.sources.get(source_id)
        if (
            not source
            or source.organization_id != profile.organization_id
            or source.id not in version.source_document_ids
            or not self._source_fully_authorized(profile, source.id)
        ):
            return None
        content = await self.artifacts.get(profile.organization_id, source.original_artifact_uri)
        return source, content

    def _source_fully_authorized(self, profile: EmployeeProfile, source_id: str) -> bool:
        canonical = self.store.canonicals.get(source_id)
        if not canonical or canonical.organization_id != profile.organization_id:
            return False
        scope = self.authorization.employee_scope(profile)
        return bool(canonical.sections) and all(
            section.access.allows(scope) for section in canonical.sections
        )

    def _active(
        self, profile: EmployeeProfile, policy_id: str
    ) -> tuple[SOPPolicy, SOPVersion] | None:
        policy = self.store.policies.get(policy_id)
        if (
            not policy
            or policy.organization_id != profile.organization_id
            or policy.status is not PolicyStatus.ACTIVE
            or not policy.active_version_id
        ):
            return None
        version = self.store.versions.get(policy.active_version_id)
        if not version or version.organization_id != profile.organization_id:
            return None
        return policy, version

    @classmethod
    def _reader_section(
        cls,
        organization_id: str,
        policy_id: str,
        version_id: str,
        section: CanonicalSection,
    ) -> PolicyReaderSection:
        return PolicyReaderSection(
            organization_id=organization_id,
            policy_id=policy_id,
            version_id=version_id,
            section_id=section.id,
            heading=section.heading,
            heading_path=section.heading_path,
            policy_number=section.policy_number,
            content=cls._section_text(section),
            source=section.source,
        )

    @staticmethod
    def _section_text(section: CanonicalSection) -> str:
        parts: list[str] = []
        for block in section.blocks:
            if block.text:
                parts.append(block.text)
            elif block.list_items:
                parts.extend(item.text for item in block.list_items)
            elif block.kind is BlockKind.TABLE and block.table:
                parts.extend(cell.text for cell in block.table.cells)
        return "\n".join(parts)
