from typing import Annotated, cast

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from apps.api.app.auth.dependencies import CurrentProfile
from apps.api.app.auth.permissions import (
    can_manage_scope,
    require_admin,
    require_management_scope,
    require_system_admin,
)
from apps.api.app.services.audit_service import AuditService
from apps.api.app.services.foundation_store import FoundationStore
from apps.api.app.services.policy_service import PolicyService
from apps.api.app.services.storage_service import ArtifactStore
from packages.contracts.canonical import CanonicalSOP
from packages.contracts.policy import IngestionJob, VersionStatus
from packages.contracts.source import SourceDocument, SourceFormat
from services.ingestion.pipeline import DuplicateSourceError, IngestionPipeline

router = APIRouter(prefix="/admin/sources", tags=["admin-sources"])


def _require_source_content_scope(
    store: FoundationStore, source_id: str, version_id: str, profile: CurrentProfile
) -> None:
    canonical = store.canonicals.get(source_id)
    if canonical and (
        canonical.organization_id != profile.organization_id
        or canonical.version_id != version_id
        or any(not can_manage_scope(profile, section.access) for section in canonical.sections)
    ):
        raise HTTPException(status_code=403, detail="Source exceeds your management scope")


class PasteSourceRequest(BaseModel):
    policy_id: str = Field(min_length=1)
    version_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source_format: SourceFormat


class ReviewUpdate(BaseModel):
    canonical: CanonicalSOP


@router.get("/capabilities")
async def capabilities(request: Request, profile: CurrentProfile) -> list[dict[str, object]]:
    require_system_admin(profile)
    pipeline = cast(IngestionPipeline, request.app.state.ingestion_pipeline)
    return [
        item.model_dump(mode="json")
        for item in pipeline.parser.capabilities(profile.organization_id)
    ]


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_source(
    request: Request,
    profile: CurrentProfile,
    policy_id: Annotated[str, Form()],
    version_id: Annotated[str, Form()],
    source_format: Annotated[SourceFormat, Form()],
    file: Annotated[UploadFile, File()],
) -> SourceDocument:
    require_system_admin(profile)
    store = cast(FoundationStore, request.app.state.foundation_store)
    version = store.versions.get(version_id)
    if (
        not version
        or version.organization_id != profile.organization_id
        or version.policy_id != policy_id
    ):
        raise HTTPException(status_code=404, detail="Policy version not found")
    if version.status in {VersionStatus.PUBLISHED, VersionStatus.SUPERSEDED}:
        raise HTTPException(status_code=409, detail="Published versions are immutable")
    require_management_scope(profile, version.access)
    pipeline = cast(IngestionPipeline, request.app.state.ingestion_pipeline)
    try:
        source = await pipeline.ingest(
            organization_id=profile.organization_id,
            policy_id=policy_id,
            version_id=version_id,
            file_name=file.filename or "source",
            media_type=file.content_type or "application/octet-stream",
            source_format=source_format,
            content=await file.read(),
        )
        cast(PolicyService, request.app.state.policy_service).attach_source(
            profile.organization_id, version_id, source.id
        )
        return source
    except DuplicateSourceError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/paste", status_code=status.HTTP_201_CREATED)
async def paste_source(
    request: Request, payload: PasteSourceRequest, profile: CurrentProfile
) -> SourceDocument:
    require_system_admin(profile)
    if payload.source_format not in {SourceFormat.MARKDOWN, SourceFormat.STRUCTURED_TEXT}:
        raise HTTPException(
            status_code=422,
            detail="Pasted sources must be Markdown or structured text",
        )
    pipeline = cast(IngestionPipeline, request.app.state.ingestion_pipeline)
    store = cast(FoundationStore, request.app.state.foundation_store)
    version = store.versions.get(payload.version_id)
    if (
        not version
        or version.organization_id != profile.organization_id
        or version.policy_id != payload.policy_id
    ):
        raise HTTPException(status_code=404, detail="Policy version not found")
    if version.status in {VersionStatus.PUBLISHED, VersionStatus.SUPERSEDED}:
        raise HTTPException(status_code=409, detail="Published versions are immutable")
    require_management_scope(profile, version.access)
    extension = "md" if payload.source_format is SourceFormat.MARKDOWN else "txt"
    try:
        source = await pipeline.ingest(
            organization_id=profile.organization_id,
            policy_id=payload.policy_id,
            version_id=payload.version_id,
            file_name=f"{payload.title}.{extension}",
            media_type="text/markdown"
            if payload.source_format is SourceFormat.MARKDOWN
            else "text/plain",
            source_format=payload.source_format,
            content=payload.content.encode(),
        )
    except DuplicateSourceError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    cast(PolicyService, request.app.state.policy_service).attach_source(
        profile.organization_id, payload.version_id, source.id
    )
    return source


@router.get("/{source_id}/review")
async def get_review(
    request: Request, source_id: str, profile: CurrentProfile
) -> dict[str, object]:
    require_admin(profile)
    store = cast(FoundationStore, request.app.state.foundation_store)
    source = store.sources.get(source_id)
    canonical = store.canonicals.get(source_id)
    raw = store.raw_results.get(source_id)
    if not source or source.organization_id != profile.organization_id:
        raise HTTPException(status_code=404, detail="Source not found")
    version = store.versions.get(source.version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Policy version not found")
    require_management_scope(profile, version.access)
    _require_source_content_scope(store, source_id, version.id, profile)
    return {
        "source": source.model_dump(mode="json"),
        "canonical": canonical.model_dump(mode="json") if canonical else None,
        "raw": raw.model_dump(mode="json") if hasattr(raw, "model_dump") else None,
    }


@router.get("/{source_id}/original")
async def get_original(request: Request, source_id: str, profile: CurrentProfile) -> Response:
    require_admin(profile)
    store = cast(FoundationStore, request.app.state.foundation_store)
    source = store.sources.get(source_id)
    if not source or source.organization_id != profile.organization_id:
        raise HTTPException(status_code=404, detail="Source not found")
    version = store.versions.get(source.version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Policy version not found")
    require_management_scope(profile, version.access)
    _require_source_content_scope(store, source_id, version.id, profile)
    artifacts = cast(ArtifactStore, request.app.state.artifact_store)
    content = await artifacts.get(profile.organization_id, source.original_artifact_uri)
    return Response(content=content, media_type=source.media_type)


@router.put("/{source_id}/review")
async def update_review(
    request: Request, source_id: str, payload: ReviewUpdate, profile: CurrentProfile
) -> CanonicalSOP:
    require_admin(profile)
    store = cast(FoundationStore, request.app.state.foundation_store)
    source = store.sources.get(source_id)
    if not source or source.organization_id != profile.organization_id:
        raise HTTPException(status_code=404, detail="Source not found")
    version = store.versions.get(source.version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Policy version not found")
    require_management_scope(profile, version.access)
    _require_source_content_scope(store, source_id, version.id, profile)
    if version.status in {VersionStatus.PUBLISHED, VersionStatus.SUPERSEDED}:
        raise HTTPException(status_code=409, detail="Published versions are immutable")
    pipeline = cast(IngestionPipeline, request.app.state.ingestion_pipeline)
    canonical = await pipeline.save_review(
        source_id, payload.canonical.model_dump_json(), profile.id
    )
    cast(PolicyService, request.app.state.policy_service).invalidate_after_review(
        profile.organization_id, version.id
    )
    cast(AuditService, request.app.state.audit_service).record(
        profile.organization_id,
        profile.id,
        "structure.review_saved",
        "source_document",
        source_id,
        {"version_id": version.id, "source_id": source_id},
    )
    return canonical


@router.get("/{source_id}/job")
async def get_job(request: Request, source_id: str, profile: CurrentProfile) -> IngestionJob:
    require_admin(profile)
    store = cast(FoundationStore, request.app.state.foundation_store)
    source = store.sources.get(source_id)
    if not source or source.organization_id != profile.organization_id:
        raise HTTPException(status_code=404, detail="Source not found")
    version = store.versions.get(source.version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Policy version not found")
    require_management_scope(profile, version.access)
    job = next((item for item in store.jobs.values() if item.source_document_id == source_id), None)
    if not job:
        raise HTTPException(status_code=404, detail="Ingestion job not found")
    return job


@router.post("/{source_id}/retry")
async def retry_source(request: Request, source_id: str, profile: CurrentProfile) -> SourceDocument:
    require_system_admin(profile)
    store = cast(FoundationStore, request.app.state.foundation_store)
    source = store.sources.get(source_id)
    if not source or source.organization_id != profile.organization_id:
        raise HTTPException(status_code=404, detail="Source not found")
    version = store.versions.get(source.version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Policy version not found")
    require_management_scope(profile, version.access)
    _require_source_content_scope(store, source_id, version.id, profile)
    if version.status in {VersionStatus.PUBLISHED, VersionStatus.SUPERSEDED}:
        raise HTTPException(status_code=409, detail="Published versions are immutable")
    try:
        return await cast(IngestionPipeline, request.app.state.ingestion_pipeline).retry(
            profile.organization_id, source_id
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_source(
    request: Request,
    profile: CurrentProfile,
    policy_id: Annotated[str, Form()],
    version_id: Annotated[str, Form()],
    original_file: Annotated[UploadFile, File()],
    structured_file: Annotated[UploadFile, File()],
) -> SourceDocument:
    """Import a pre-verified original PDF along with its corresponding structured Markdown/JSON file."""
    require_system_admin(profile)
    store = cast(FoundationStore, request.app.state.foundation_store)
    version = store.versions.get(version_id)
    if (
        not version
        or version.organization_id != profile.organization_id
        or version.policy_id != policy_id
    ):
        raise HTTPException(status_code=404, detail="Policy version not found")
    if version.status in {VersionStatus.PUBLISHED, VersionStatus.SUPERSEDED}:
        raise HTTPException(status_code=409, detail="Published versions are immutable")
    require_management_scope(profile, version.access)

    # Validate file sizes (200MB max)
    pdf_content = await original_file.read()
    structured_content = await structured_file.read()
    max_bytes = 200 * 1024 * 1024
    if len(pdf_content) > max_bytes or len(structured_content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail="File size exceeds maximum allowed limit of 200MB",
        )

    # Validate file formats
    pdf_name = original_file.filename or "original.pdf"
    if not pdf_name.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=422,
            detail="Original file must be a PDF document (.pdf)",
        )

    struct_name = structured_file.filename or "content.md"
    is_markdown = struct_name.lower().endswith(".md") or struct_name.lower().endswith(".markdown")
    is_json = struct_name.lower().endswith(".json")
    if not (is_markdown or is_json):
        raise HTTPException(
            status_code=422,
            detail="Structured file must be Markdown (.md) or JSON (.json)",
        )

    source_format = SourceFormat.MARKDOWN if is_markdown else SourceFormat.STRUCTURED_TEXT
    pipeline = cast(IngestionPipeline, request.app.state.ingestion_pipeline)
    try:
        source = await pipeline.ingest(
            organization_id=profile.organization_id,
            policy_id=policy_id,
            version_id=version_id,
            file_name=struct_name,
            media_type="text/markdown" if is_markdown else "application/json",
            source_format=source_format,
            content=structured_content,
        )
        # Store original PDF artifact as well
        artifacts = cast(ArtifactStore, request.app.state.artifact_store)
        pdf_uri = await artifacts.put(
            profile.organization_id, f"sources/{source.id}/{pdf_name}", pdf_content
        )
        # Update source document with original PDF artifact URI
        updated_source = source.model_copy(update={"original_artifact_uri": pdf_uri})
        store.sources[source.id] = updated_source
        store.mark_modified("source_documents", source.id, updated_source)

        cast(PolicyService, request.app.state.policy_service).attach_source(
            profile.organization_id, version_id, source.id
        )
        return updated_source
    except DuplicateSourceError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
