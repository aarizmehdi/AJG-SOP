import hashlib
import json
from time import perf_counter
from uuid import uuid4

from apps.api.app.services.foundation_store import FoundationStore
from apps.api.app.services.metrics import MetricsRegistry
from apps.api.app.services.storage_service import ArtifactStore
from packages.contracts.canonical import CanonicalSOP, ReviewRevision, SourceLocator
from packages.contracts.policy import IngestionEvent, IngestionJob, IngestionState
from packages.contracts.source import SourceDocument, SourceFormat, SourceStatus
from services.ingestion.extractors.base import DocumentParser, ParserUnavailableError
from services.ingestion.structure.canonical_document import Canonicalizer
from services.ingestion.structure.markdown import canonical_to_markdown


class DuplicateSourceError(ValueError):
    pass


class IngestionPipeline:
    def __init__(
        self,
        parser: DocumentParser,
        canonicalizer: Canonicalizer,
        artifacts: ArtifactStore,
        store: FoundationStore,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self.parser = parser
        self.canonicalizer = canonicalizer
        self.artifacts = artifacts
        self.store = store
        self.metrics = metrics

    async def ingest(
        self,
        organization_id: str,
        policy_id: str,
        version_id: str,
        file_name: str,
        media_type: str,
        source_format: SourceFormat,
        content: bytes,
    ) -> SourceDocument:
        digest = hashlib.sha256(content).hexdigest()
        if any(
            source.organization_id == organization_id and source.sha256 == digest
            for source in self.store.sources.values()
        ):
            raise DuplicateSourceError("An identical source document already exists")
        source_id = f"source-{uuid4().hex[:12]}"
        original_uri = await self.artifacts.put(
            organization_id, f"sources/{source_id}/original/{file_name}", content
        )
        source = SourceDocument(
            id=source_id,
            organization_id=organization_id,
            policy_id=policy_id,
            version_id=version_id,
            file_name=file_name,
            media_type=media_type,
            source_format=source_format,
            sha256=digest,
            original_artifact_uri=original_uri,
            status=SourceStatus.PROCESSING,
            parser_provider=self.parser.__class__.__name__,
        )
        self.store.sources[source.id] = source
        self.store.mark_modified("source_documents", source.id, source)
        job = IngestionJob(
            id=f"job-{uuid4().hex[:12]}",
            organization_id=organization_id,
            source_document_id=source.id,
            version_id=version_id,
            state=IngestionState.UPLOADED,
            events=[
                IngestionEvent(
                    organization_id=organization_id,
                    state=IngestionState.UPLOADED,
                    detail="File uploaded",
                )
            ],
        )
        self.store.jobs[job.id] = job
        self.store.mark_modified("ingestion_jobs", job.id, job)
        return await self._process(source, job, content)

    async def retry(self, organization_id: str, source_id: str) -> SourceDocument:
        source = self.store.sources.get(source_id)
        job = next(
            (item for item in self.store.jobs.values() if item.source_document_id == source_id),
            None,
        )
        if not source or source.organization_id != organization_id or not job:
            raise KeyError(source_id)
        if job.state is not IngestionState.FAILED:
            raise ValueError("Only failed ingestion jobs can be retried")
        content = await self.artifacts.get(organization_id, source.original_artifact_uri)
        job.retry_count += 1
        job.error_code = None
        source = source.model_copy(update={"status": SourceStatus.PROCESSING, "error_code": None})
        self.store.sources[source.id] = source
        return await self._process(source, job, content)

    async def _process(
        self, source: SourceDocument, job: IngestionJob, content: bytes
    ) -> SourceDocument:
        organization_id = source.organization_id
        source_id = source.id
        started = perf_counter()
        try:
            self._transition(job, IngestionState.EXTRACTING, "Reading document")
            raw = await self.parser.parse(source, content)
            if raw.provider_payload is not None:
                provider_uri = await self.artifacts.put(
                    organization_id,
                    f"sources/{source_id}/raw/provider.json",
                    json.dumps(raw.provider_payload, ensure_ascii=False, indent=2).encode(),
                )
                raw = raw.model_copy(
                    update={"provider_artifact_uri": provider_uri, "provider_payload": None}
                )
            raw_uri = await self.artifacts.put(
                organization_id,
                f"sources/{source_id}/raw/result.json",
                raw.model_dump_json(indent=2).encode(),
            )
            self._transition(job, IngestionState.STRUCTURING, "Building sections")
            version = self.store.versions.get(source.version_id)
            if not version or version.organization_id != source.organization_id:
                raise PermissionError("Source version ownership could not be verified")
            canonical = self.canonicalizer.canonicalize(source, raw, version.access)
            canonical_uri = await self.artifacts.put(
                organization_id,
                f"sources/{source_id}/canonical/canonical.json",
                canonical.model_dump_json(indent=2).encode(),
            )
            await self.artifacts.put(
                organization_id,
                f"sources/{source_id}/canonical/canonical.md",
                canonical_to_markdown(canonical).encode(),
            )
            source = source.model_copy(
                update={
                    "status": SourceStatus.REVIEW_REQUIRED,
                    "parser_provider": raw.provider,
                    "parser_version": raw.provider_version,
                    "raw_artifact_uri": raw_uri,
                    "canonical_artifact_uri": canonical_uri,
                }
            )
            self.store.raw_results[source.id] = raw
            self.store.canonicals[source.id] = canonical
            self.store.mark_modified("raw_parser_results", source.id, raw)
            self.store.mark_modified("canonical_sops", source.id, canonical)
            self._transition(job, IngestionState.REVIEW_REQUIRED, "Waiting for human review")
        except ParserUnavailableError:
            source = source.model_copy(
                update={"status": SourceStatus.FAILED, "error_code": "parser_unavailable"}
            )
            self._transition(
                job,
                IngestionState.FAILED,
                "A configured parser is required for this source format",
                "parser_unavailable",
            )
            if self.metrics:
                self.metrics.observe("ingestion", (perf_counter() - started) * 1000, failed=True)
        except Exception:
            source = source.model_copy(
                update={"status": SourceStatus.FAILED, "error_code": "extraction_failed"}
            )
            self._transition(
                job,
                IngestionState.FAILED,
                "Document extraction failed and can be retried",
                "extraction_failed",
            )
            if self.metrics:
                self.metrics.observe("ingestion", (perf_counter() - started) * 1000, failed=True)
        else:
            if self.metrics:
                self.metrics.observe("ingestion", (perf_counter() - started) * 1000)
        self.store.sources[source.id] = source
        self.store.mark_modified("source_documents", source.id, source)
        return source

    @staticmethod
    def _transition(
        job: IngestionJob,
        state: IngestionState,
        detail: str,
        error_code: str | None = None,
    ) -> None:
        job.state = state
        job.error_code = error_code
        job.events.append(
            IngestionEvent(organization_id=job.organization_id, state=state, detail=detail)
        )

    async def save_review(
        self, source_id: str, canonical_json: str, reviewer_id: str
    ) -> CanonicalSOP:
        source = self.store.sources[source_id]
        canonical = CanonicalSOP.model_validate(json.loads(canonical_json))
        previous = self.store.canonicals[source_id]
        if (
            canonical.organization_id != source.organization_id
            or canonical.policy_id != source.policy_id
            or canonical.version_id != source.version_id
            or canonical.source_document_ids != previous.source_document_ids
        ):
            raise PermissionError("Canonical ownership fields cannot be changed during review")
        raw = self.store.raw_results.get(source_id)
        if raw is not None and hasattr(raw, "blocks"):
            valid_pages = {block.page for block in raw.blocks if block.page is not None}
            for section in canonical.sections:
                self._validate_locator(section.source, source_id, valid_pages)
                for block in section.blocks:
                    self._validate_locator(block.source, source_id, valid_pages)
                    for item in block.list_items:
                        self._validate_locator(item.source, source_id, valid_pages)
                    if block.table:
                        self._validate_locator(block.table.source, source_id, valid_pages)
                        for cell in block.table.cells:
                            self._validate_locator(cell.source, source_id, valid_pages)
        heading_stack: list[tuple[int, str, str]] = []
        for section in canonical.sections:
            while heading_stack and heading_stack[-1][0] >= section.heading_level:
                heading_stack.pop()
            section.parent_section_id = heading_stack[-1][2] if heading_stack else None
            section.heading_path = tuple(item[1] for item in heading_stack) + (section.heading,)
            section.chapter = section.heading_path[0] if len(section.heading_path) > 1 else None
            heading_stack.append((section.heading_level, section.heading, section.id))
            sources = {block.source.source_document_id for block in section.blocks} | {
                section.source.source_document_id
            }
            if sources != {source_id}:
                raise PermissionError("Review content must retain its original source mapping")
            content = "\n".join(
                block.text
                or "\n".join(item.text for item in block.list_items)
                or ("\n".join(cell.text for cell in block.table.cells) if block.table else "")
                for block in section.blocks
            )
            section.content_hash = hashlib.sha256(content.encode()).hexdigest()
        canonical.approved = False
        canonical.approved_at = None
        canonical.review_revisions = [
            *previous.review_revisions,
            ReviewRevision(
                revision=len(previous.review_revisions) + 1,
                reviewer_id=reviewer_id,
                note="Canonical extraction correction saved",
            ),
        ]
        uri = await self.artifacts.put(
            source.organization_id,
            f"sources/{source_id}/reviewed/reviewed.json",
            canonical.model_dump_json(indent=2).encode(),
        )
        self.store.canonicals[source_id] = canonical
        self.store.mark_modified("canonical_sops", source_id, canonical)
        self.store.sources[source_id] = source.model_copy(
            update={"reviewed_artifact_uri": uri, "status": SourceStatus.REVIEW_REQUIRED}
        )
        self.store.mark_modified("source_documents", source_id, self.store.sources[source_id])
        return canonical

    @staticmethod
    def _validate_locator(locator: SourceLocator, source_id: str, valid_pages: set[int]) -> None:
        if locator.source_document_id != source_id:
            raise PermissionError("Review source mappings cannot cross source documents")
        located_pages = {
            page for page in (locator.page_start, locator.page_end) if page is not None
        }
        if valid_pages and not located_pages.issubset(valid_pages):
            raise ValueError("Review source page is outside the extracted original")
