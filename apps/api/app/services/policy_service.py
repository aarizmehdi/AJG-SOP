from datetime import date
from uuid import uuid4

from apps.api.app.services.audit_service import AuditService
from apps.api.app.services.foundation_store import FoundationStore
from packages.contracts.access import AccessScope
from packages.contracts.canonical import BlockKind, CanonicalSection, RetrievalChunk
from packages.contracts.common import utc_now
from packages.contracts.policy import (
    DuplicateSectionGroup,
    DuplicateSectionOccurrence,
    IngestionEvent,
    IngestionJob,
    IngestionState,
    PolicyStatus,
    SectionChange,
    SectionChangeKind,
    SOPPolicy,
    SOPVersion,
    VersionStatus,
)
from packages.contracts.source import SourceStatus
from services.ingestion.chunking.semantic_chunker import Chunker
from services.ingestion.embeddings.base import EmbeddingProvider
from services.ingestion.indexing.pinecone_index import DerivedRetrievalIndex


class PublicationError(RuntimeError):
    pass


class PolicyService:
    def __init__(
        self,
        store: FoundationStore,
        chunker: Chunker,
        embeddings: EmbeddingProvider,
        index: DerivedRetrievalIndex,
        audit: AuditService,
    ) -> None:
        self.store = store
        self.chunker = chunker
        self.embeddings = embeddings
        self.index = index
        self.audit = audit

    def create_policy(
        self,
        organization_id: str,
        actor_id: str,
        title: str,
        category: str,
        policy_number: str | None,
    ) -> SOPPolicy:
        policy = SOPPolicy(
            id=f"policy-{uuid4().hex[:12]}",
            organization_id=organization_id,
            title=title,
            category=category,
            policy_number=policy_number,
        )
        self.store.policies[policy.id] = policy
        self.store.mark_modified("policies", policy.id, policy)
        self.audit.record(organization_id, actor_id, "policy.created", "policy", policy.id)
        return policy

    def create_version(
        self,
        organization_id: str,
        actor_id: str,
        policy_id: str,
        version_label: str,
        access: AccessScope,
        effective_date: date | None = None,
    ) -> SOPVersion:
        policy = self._policy(organization_id, policy_id)
        version = SOPVersion(
            id=f"version-{uuid4().hex[:12]}",
            organization_id=organization_id,
            policy_id=policy.id,
            version_label=version_label,
            effective_date=effective_date,
            access=access,
        )
        self.store.versions[version.id] = version
        self.store.mark_modified("policy_versions", version.id, version)
        self.audit.record(
            organization_id, actor_id, "version.created", "policy_version", version.id
        )
        return version

    def set_access(
        self,
        organization_id: str,
        actor_id: str,
        version_id: str,
        access: AccessScope,
    ) -> SOPVersion:
        version = self._version(organization_id, version_id)
        if version.status in {VersionStatus.PUBLISHED, VersionStatus.SUPERSEDED}:
            raise PublicationError("Published version access is immutable; create a new version")
        version.access = access
        version.index_revision = None
        version.status = VersionStatus.EXTRACTION_REVIEW
        self.store.chunks.pop(version.id, None)
        for source_id in version.source_document_ids:
            canonical = self.store.canonicals.get(source_id)
            if canonical:
                for section in canonical.sections:
                    section.access = access
        self.store.mark_modified("policy_versions", version.id, version)
        self.audit.record(
            organization_id, actor_id, "version.access_updated", "policy_version", version.id
        )
        return version

    def duplicate_sections(
        self, organization_id: str, version_id: str
    ) -> list[DuplicateSectionGroup]:
        sections = self._sections(organization_id, version_id)
        grouped: dict[str, list[CanonicalSection]] = {}
        for section in sections.values():
            grouped.setdefault(section.content_hash, []).append(section)
        return [
            DuplicateSectionGroup(
                organization_id=organization_id,
                content_hash=content_hash,
                occurrences=[
                    DuplicateSectionOccurrence(
                        source_document_id=section.source.source_document_id,
                        section_id=section.id,
                        heading=section.heading,
                    )
                    for section in matches
                ],
            )
            for content_hash, matches in grouped.items()
            if len(matches) > 1
        ]

    def invalidate_after_review(self, organization_id: str, version_id: str) -> SOPVersion:
        version = self._version(organization_id, version_id)
        if version.status in {VersionStatus.PUBLISHED, VersionStatus.SUPERSEDED}:
            raise PublicationError("Published versions are immutable; create a new version")
        version.index_revision = None
        version.status = VersionStatus.EXTRACTION_REVIEW
        self.store.chunks.pop(version.id, None)
        return version

    def attach_source(self, organization_id: str, version_id: str, source_id: str) -> None:
        version = self._version(organization_id, version_id)
        if version.status in {VersionStatus.PUBLISHED, VersionStatus.SUPERSEDED}:
            raise PublicationError("Published versions are immutable; create a new version")
        source = self.store.sources[source_id]
        if source.organization_id != organization_id or source.version_id != version_id:
            raise PermissionError("Source and version ownership do not match")
        if source_id not in version.source_document_ids:
            version.source_document_ids.append(source_id)
        version.status = VersionStatus.EXTRACTION_REVIEW

    def approve_structure(self, organization_id: str, actor_id: str, source_id: str) -> SOPVersion:
        source = self.store.sources[source_id]
        if source.organization_id != organization_id:
            raise KeyError(source_id)
        canonical = self.store.canonicals.get(source_id)
        if not canonical:
            raise PublicationError("Canonical structure is unavailable")
        version = self._version(organization_id, source.version_id)
        if version.status in {VersionStatus.PUBLISHED, VersionStatus.SUPERSEDED}:
            raise PublicationError("Published versions are immutable; create a new version")
        canonical.approved = True
        canonical.approved_at = utc_now()
        source.status = SourceStatus.APPROVED
        self.attach_source(organization_id, version.id, source.id)
        if canonical.id not in version.canonical_document_ids:
            version.canonical_document_ids.append(canonical.id)
        version.status = VersionStatus.READY_FOR_INDEXING
        job = next(
            (item for item in self.store.jobs.values() if item.source_document_id == source_id),
            None,
        )
        if job:
            job.state = IngestionState.STRUCTURE_APPROVED
            job.events.append(
                IngestionEvent(
                    organization_id=organization_id,
                    state=IngestionState.STRUCTURE_APPROVED,
                    detail="Canonical structure approved",
                )
            )
        self.audit.record(
            organization_id,
            actor_id,
            "structure.approved",
            "source_document",
            source_id,
            {"version_id": version.id, "source_id": source_id},
        )
        self.store.mark_modified("policy_versions", version.id, version)
        return version

    async def prepare_for_publication(
        self, organization_id: str, actor_id: str, version_id: str
    ) -> SOPVersion:
        version = self._version(organization_id, version_id)
        canonicals = [
            self.store.canonicals[source_id]
            for source_id in version.source_document_ids
            if source_id in self.store.canonicals
        ]
        if not canonicals or not all(document.approved for document in canonicals):
            raise PublicationError("Every canonical source requires human approval")
        version.status = VersionStatus.INDEXING
        jobs = [
            job
            for job in self.store.jobs.values()
            if job.version_id == version.id and job.organization_id == organization_id
        ]
        self._jobs_transition(jobs, IngestionState.CHUNKING, "Creating section-aware chunks")
        chunks: list[RetrievalChunk] = []
        for document in canonicals:
            chunks.extend(self.chunker.chunk(document, "staged"))
        self._jobs_transition(jobs, IngestionState.EMBEDDING, "Creating provisional embeddings")
        vectors = await self.embeddings.embed([chunk.text for chunk in chunks])
        try:
            self._jobs_transition(jobs, IngestionState.INDEXING, "Staging derived retrieval index")
            revision = await self.index.stage(organization_id, version_id, chunks, vectors)
            self._jobs_transition(jobs, IngestionState.VERIFYING, "Verifying staged index")
            verified = await self.index.verify(
                organization_id, version_id, {chunk.id for chunk in chunks}
            )
        except Exception as error:
            version.status = VersionStatus.FAILED
            self._jobs_transition(
                jobs, IngestionState.FAILED, "Index staging failed; published version unchanged"
            )
            raise PublicationError(
                "Index staging failed; current version remains active"
            ) from error
        if not verified:
            version.status = VersionStatus.FAILED
            self._jobs_transition(
                jobs,
                IngestionState.FAILED,
                "Index verification failed; published version unchanged",
            )
            raise PublicationError("Index verification failed; current version remains active")
        version.index_revision = revision
        version.status = VersionStatus.READY_TO_PUBLISH
        self.store.chunks[version.id] = list(chunks)
        for chunk in chunks:
            self.store.mark_modified("retrieval_chunks", chunk.id, chunk)
        self.store.mark_modified("policy_versions", version.id, version)
        self._jobs_transition(jobs, IngestionState.READY_FOR_REVIEW, "Index verified")
        self.audit.record(
            organization_id, actor_id, "version.index_verified", "policy_version", version.id
        )
        return version

    def publish(self, organization_id: str, actor_id: str, version_id: str) -> SOPVersion:
        version = self._version(organization_id, version_id)
        if version.status is not VersionStatus.READY_TO_PUBLISH or not version.index_revision:
            raise PublicationError("Version must pass index verification before publication")
        policy = self._policy(organization_id, version.policy_id)
        previous_id = policy.active_version_id
        previous = self.store.versions.get(previous_id) if previous_id else None
        if previous and previous.organization_id == organization_id:
            previous.status = VersionStatus.SUPERSEDED
            self.store.mark_modified("policy_versions", previous.id, previous)
        version.status = VersionStatus.PUBLISHED
        version.published_at = utc_now()
        policy.active_version_id = version.id
        policy.status = PolicyStatus.ACTIVE
        policy.updated_at = utc_now()
        for chunk in self.store.chunks.get(version.id, []):
            if isinstance(chunk, RetrievalChunk):
                chunk.publication_status = "published"
                self.store.mark_modified("retrieval_chunks", chunk.id, chunk)
        self.store.mark_modified("policy_versions", version.id, version)
        self.store.mark_modified("policies", policy.id, policy)
        self._jobs_transition(
            [
                job
                for job in self.store.jobs.values()
                if job.version_id == version.id and job.organization_id == organization_id
            ],
            IngestionState.PUBLISHED,
            "Version published",
        )
        self.audit.record(
            organization_id,
            actor_id,
            "version.published",
            "policy_version",
            version.id,
            {"previous_version_id": previous_id or ""},
        )
        return version

    def rollback(
        self, organization_id: str, actor_id: str, policy_id: str, version_id: str
    ) -> SOPVersion:
        policy = self._policy(organization_id, policy_id)
        target = self._version(organization_id, version_id)
        if target.policy_id != policy.id or not target.index_revision:
            raise PublicationError("Rollback target has no verified index")
        current = self.store.versions.get(policy.active_version_id or "")
        if current:
            current.status = VersionStatus.SUPERSEDED
            self.store.mark_modified("policy_versions", current.id, current)
        target.status = VersionStatus.PUBLISHED
        policy.active_version_id = target.id
        policy.status = PolicyStatus.ACTIVE
        policy.updated_at = utc_now()
        self.store.mark_modified("policy_versions", target.id, target)
        self.store.mark_modified("policies", policy.id, policy)
        self.audit.record(
            organization_id,
            actor_id,
            "policy.rolled_back",
            "policy",
            policy.id,
            {"target_version_id": target.id},
        )
        return target

    def deactivate(self, organization_id: str, actor_id: str, policy_id: str) -> SOPPolicy:
        policy = self._policy(organization_id, policy_id)
        policy.status = PolicyStatus.INACTIVE
        policy.updated_at = utc_now()
        self.store.mark_modified("policies", policy.id, policy)
        self.audit.record(organization_id, actor_id, "policy.deactivated", "policy", policy.id)
        return policy

    def diff(
        self, organization_id: str, old_version_id: str, new_version_id: str
    ) -> list[SectionChange]:
        old = self._sections(organization_id, old_version_id)
        new = self._sections(organization_id, new_version_id)
        changes: list[SectionChange] = []
        for key in sorted(old.keys() | new.keys()):
            old_section = old.get(key)
            new_section = new.get(key)
            if old_section is None and new_section is not None:
                kind = SectionChangeKind.ADDED
            elif new_section is None and old_section is not None:
                kind = SectionChangeKind.REMOVED
            elif (
                old_section
                and new_section
                and (
                    old_section.content_hash != new_section.content_hash
                    or old_section.access != new_section.access
                )
            ):
                kind = SectionChangeKind.CHANGED
            else:
                continue
            chosen = new_section or old_section
            if chosen is None:
                continue
            changes.append(
                SectionChange(
                    organization_id=organization_id,
                    kind=kind,
                    stable_key=key,
                    heading=chosen.heading,
                    old_content=self._section_text(old_section),
                    new_content=self._section_text(new_section),
                    access_changed=bool(
                        old_section and new_section and old_section.access != new_section.access
                    ),
                )
            )
        return changes

    def _sections(self, organization_id: str, version_id: str) -> dict[str, CanonicalSection]:
        version = self._version(organization_id, version_id)
        return {
            section.stable_key: section
            for source_id in version.source_document_ids
            for section in (
                self.store.canonicals[source_id].sections
                if source_id in self.store.canonicals
                else []
            )
        }

    @staticmethod
    def _section_text(section: CanonicalSection | None) -> str | None:
        if section is None:
            return None
        values: list[str] = []
        for block in section.blocks:
            if block.text:
                values.append(block.text)
            elif block.list_items:
                values.extend(item.text for item in block.list_items)
            elif block.kind is BlockKind.TABLE and block.table:
                values.extend(cell.text for cell in block.table.cells)
        return "\n".join(values)

    def _policy(self, organization_id: str, policy_id: str) -> SOPPolicy:
        policy = self.store.policies.get(policy_id)
        if not policy or policy.organization_id != organization_id:
            raise KeyError(policy_id)
        return policy

    def _version(self, organization_id: str, version_id: str) -> SOPVersion:
        version = self.store.versions.get(version_id)
        if not version or version.organization_id != organization_id:
            raise KeyError(version_id)
        return version

    @staticmethod
    def _jobs_transition(jobs: list[IngestionJob], state: IngestionState, detail: str) -> None:
        for job in jobs:
            job.state = state
            job.error_code = "index_failed" if state is IngestionState.FAILED else None
            job.events.append(
                IngestionEvent(
                    organization_id=job.organization_id,
                    state=state,
                    detail=detail,
                )
            )
