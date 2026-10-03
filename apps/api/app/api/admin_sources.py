import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Annotated, cast
from urllib.parse import urlencode

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse, Response
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
from apps.api.app.services.storage_service import ArtifactStore, LocalArtifactStore, StorageError
from packages.contracts.canonical import CanonicalSOP
from packages.contracts.policy import IngestionJob, VersionStatus
from packages.contracts.source import SourceDocument, SourceFormat, SourceStatus
from services.ingestion.pipeline import DuplicateSourceError, IngestionPipeline

router = APIRouter(prefix="/admin/sources", tags=["admin-sources"])
_preview_secret = secrets.token_bytes(32)


def _safe_upload_name(name: str | None, fallback: str) -> str:
    return (name or fallback).replace("\\", "/").rsplit("/", 1)[-1] or fallback


def _preview_ticket(organization_id: str, source_id: str) -> str:
    payload = json.dumps([organization_id, source_id, int(time.time()) + 120]).encode()
    signature = hmac.digest(_preview_secret, payload, "sha256")
    return base64.urlsafe_b64encode(payload + signature).decode().rstrip("=")


def _verify_preview_ticket(ticket: str, organization_id: str, source_id: str) -> bool:
    try:
        decoded = base64.urlsafe_b64decode(ticket + "=" * (-len(ticket) % 4))
        payload, signature = decoded[:-32], decoded[-32:]
        expected = hmac.digest(_preview_secret, payload, "sha256")
        org, source, expires = json.loads(payload)
        return (
            hmac.compare_digest(signature, expected)
            and org == organization_id
            and source == source_id
            and expires >= int(time.time())
        )
    except (ValueError, TypeError, IndexError):
        return False


def _authorized_source(request: Request, source_id: str, profile: CurrentProfile) -> SourceDocument:
    require_admin(profile)
    store = cast(FoundationStore, request.app.state.foundation_store)
    source = store.sources.get(source_id)
    if not source or source.organization_id != profile.organization_id:
        raise HTTPException(status_code=404, detail="Source not found")
    version = store.versions.get(source.version_id)
    if not version or version.organization_id != profile.organization_id:
        raise HTTPException(status_code=404, detail="Policy version not found")
    require_management_scope(profile, version.access)
    _require_source_content_scope(store, source_id, version.id, profile)
    return source


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
        "version": version.model_dump(mode="json"),
        "canonical": canonical.model_dump(mode="json") if canonical else None,
        "raw": raw.model_dump(mode="json") if hasattr(raw, "model_dump") else None,
    }


@router.get("/{source_id}/original")
async def get_original(request: Request, source_id: str, profile: CurrentProfile) -> Response:
    source = _authorized_source(request, source_id, profile)
    artifacts = cast(ArtifactStore, request.app.state.artifact_store)
    try:
        signature = await artifacts.signature(profile.organization_id, source.original_artifact_uri)
    except StorageError as error:
        raise HTTPException(status_code=404, detail="Original artifact unavailable") from error
    media_type = "application/pdf" if signature.startswith(b"%PDF-") else source.media_type
    url = artifacts.presigned_get(
        profile.organization_id, source.original_artifact_uri, media_type=media_type
    )
    if url:
        return RedirectResponse(url, status_code=307, headers={"Cache-Control": "no-store"})
    if isinstance(artifacts, LocalArtifactStore):
        path = artifacts.local_path(profile.organization_id, source.original_artifact_uri)
        return FileResponse(path, media_type=media_type, filename=path.name)
    raise HTTPException(status_code=503, detail="Original preview unavailable")


@router.get("/{source_id}/original/preview")
async def original_preview(
    request: Request, source_id: str, profile: CurrentProfile, response: Response
) -> dict[str, object]:
    response.headers["Cache-Control"] = "private, no-store"
    source = _authorized_source(request, source_id, profile)
    artifacts = cast(ArtifactStore, request.app.state.artifact_store)
    try:
        signature = await artifacts.signature(profile.organization_id, source.original_artifact_uri)
    except StorageError as error:
        raise HTTPException(status_code=404, detail="Original artifact unavailable") from error
    is_pdf = signature.startswith(b"%PDF-")
    is_image = signature.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff"))
    if not is_pdf and not is_image:
        return {"kind": "missing_pdf" if source.source_format is SourceFormat.MARKDOWN else "other"}
    media_type = (
        "application/pdf"
        if is_pdf
        else ("image/png" if signature.startswith(b"\x89PNG") else "image/jpeg")
    )
    url = artifacts.presigned_get(
        profile.organization_id, source.original_artifact_uri, media_type=media_type
    )
    if url is None:
        base = str(request.url_for("local_original_stream", source_id=source_id))
        url = (
            base
            + "?"
            + urlencode(
                {
                    "organization_id": profile.organization_id,
                    "ticket": _preview_ticket(profile.organization_id, source_id),
                }
            )
        )
    return {
        "kind": "pdf" if is_pdf else "image",
        "url": url,
        "file_name": source.file_name
        if source.source_format is not SourceFormat.MARKDOWN
        else (source.original_artifact_uri.rsplit("/", 1)[-1]),
        "media_type": media_type,
        "legacy_repair_required": is_pdf and source.source_format is SourceFormat.MARKDOWN,
        "expires_in_seconds": 120,
    }


@router.get("/{source_id}/original/stream")
async def local_original_stream(
    request: Request, source_id: str, organization_id: str, ticket: str
) -> FileResponse:
    if not _verify_preview_ticket(ticket, organization_id, source_id):
        raise HTTPException(status_code=404, detail="Preview unavailable")
    artifacts = cast(ArtifactStore, request.app.state.artifact_store)
    if not isinstance(artifacts, LocalArtifactStore):
        raise HTTPException(status_code=404, detail="Preview unavailable")
    store = cast(FoundationStore, request.app.state.foundation_store)
    source = store.sources.get(source_id)
    if not source or source.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Preview unavailable")
    path = artifacts.local_path(organization_id, source.original_artifact_uri)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Preview unavailable")
    signature = await artifacts.signature(organization_id, source.original_artifact_uri)
    media_type = (
        "application/pdf"
        if signature.startswith(b"%PDF-")
        else ("image/png" if signature.startswith(b"\x89PNG") else "image/jpeg")
    )
    return FileResponse(
        path,
        media_type=media_type,
        content_disposition_type="inline",
        filename=path.name,
        headers={"Cache-Control": "private, no-store"},
    )


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
    if any(not can_manage_scope(profile, section.access) for section in payload.canonical.sections):
        raise HTTPException(status_code=403, detail="Reviewed content exceeds management scope")
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
    """Import a pre-verified original PDF along with its corresponding structured file
    (Markdown or JSON)."""
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
    pdf_name = _safe_upload_name(original_file.filename, "original.pdf")
    if not pdf_name.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=422,
            detail="Original file must be a PDF document (.pdf)",
        )
    if not pdf_content.startswith(b"%PDF-"):
        raise HTTPException(status_code=422, detail="Original file is not a valid PDF")

    struct_name = _safe_upload_name(structured_file.filename, "content.md")
    is_markdown = struct_name.lower().endswith(".md") or struct_name.lower().endswith(".markdown")
    is_json = struct_name.lower().endswith(".json")
    if not (is_markdown or is_json):
        raise HTTPException(
            status_code=422,
            detail="Structured file must be Markdown (.md) or JSON (.json)",
        )

    source_format = SourceFormat.MARKDOWN if is_markdown else SourceFormat.STRUCTURED_TEXT
    digest = hashlib.sha256(structured_content).hexdigest()
    prior = next(
        (
            item
            for item in store.sources.values()
            if item.organization_id == profile.organization_id
            and item.policy_id == policy_id
            and item.version_id == version_id
            and item.sha256 == digest
            and (item.structured_file_name or item.file_name) == struct_name
        ),
        None,
    )
    if prior:
        if prior.structured_artifact_uri:
            if prior.file_name == pdf_name and prior.media_type == "application/pdf":
                return prior
            raise HTTPException(
                status_code=409, detail="This structured source already has an original PDF"
            )
        if prior.source_format is not SourceFormat.MARKDOWN:
            raise HTTPException(status_code=409, detail="Existing source requires manual review")
        await original_file.seek(0)
        return await attach_original_pdf(request, prior.id, profile, original_file)

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
            profile.organization_id,
            f"sources/{source.id}/{pdf_name}",
            pdf_content,
            media_type="application/pdf",
        )
        # Preserve both independently: the PDF is authoritative while the
        # human-reviewed structured artifact remains the parser input.
        updated_source = source.model_copy(
            update={
                "file_name": pdf_name,
                "media_type": "application/pdf",
                "source_format": SourceFormat.PDF,
                "original_artifact_uri": pdf_uri,
                "structured_artifact_uri": source.original_artifact_uri,
                "structured_file_name": struct_name,
                "structured_media_type": ("text/markdown" if is_markdown else "application/json"),
                "structured_source_format": source_format,
            }
        )
        store.sources[source.id] = updated_source
        store.mark_modified("source_documents", source.id, updated_source)

        cast(PolicyService, request.app.state.policy_service).attach_source(
            profile.organization_id, version_id, source.id
        )
        return updated_source
    except DuplicateSourceError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/{source_id}/attach-original", status_code=status.HTTP_200_OK)
async def attach_original_pdf(
    request: Request,
    source_id: str,
    profile: CurrentProfile,
    file: Annotated[UploadFile, File()],
) -> SourceDocument:
    """Complete a draft Markdown source without replacing its reviewed canonical SOP."""
    source = _authorized_source(request, source_id, profile)
    store = cast(FoundationStore, request.app.state.foundation_store)
    version = store.versions[source.version_id]
    if version.status in {VersionStatus.PUBLISHED, VersionStatus.SUPERSEDED}:
        raise HTTPException(status_code=409, detail="Published versions are immutable")
    if source.source_format is not SourceFormat.MARKDOWN or source.structured_artifact_uri:
        raise HTTPException(status_code=409, detail="This source is not a Markdown-only draft")
    artifacts = cast(ArtifactStore, request.app.state.artifact_store)
    signature = await artifacts.signature(profile.organization_id, source.original_artifact_uri)
    if signature.startswith(b"%PDF-"):
        raise HTTPException(status_code=409, detail="Existing PDF needs legacy metadata repair")
    if b"\0" in signature:
        raise HTTPException(status_code=409, detail="Structured Markdown artifact is invalid")
    filename = _safe_upload_name(file.filename, "original.pdf")
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Choose an original PDF file")
    content = await file.read()
    if len(content) > 200 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PDF exceeds the 200 MB upload limit")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=422, detail="Uploaded file is not a PDF")
    uri = await artifacts.put(
        profile.organization_id,
        f"sources/{source.id}/original-pdf/{filename}",
        content,
        media_type="application/pdf",
    )
    updated = source.model_copy(
        update={
            "file_name": filename,
            "media_type": "application/pdf",
            "source_format": SourceFormat.PDF,
            "original_artifact_uri": uri,
            "structured_artifact_uri": source.original_artifact_uri,
            "structured_file_name": source.file_name,
            "structured_media_type": source.media_type,
            "structured_source_format": source.source_format,
            "status": SourceStatus.REVIEW_REQUIRED,
        }
    )
    canonical = store.canonicals.get(source.id)
    if canonical and canonical.approved:
        canonical.approved = False
        canonical.approved_at = None
        store.mark_modified("canonical_sops", source.id, canonical)
    cast(PolicyService, request.app.state.policy_service).invalidate_after_review(
        profile.organization_id, version.id
    )
    store.sources[source.id] = updated
    store.mark_modified("source_documents", source.id, updated)
    cast(AuditService, request.app.state.audit_service).record(
        profile.organization_id,
        profile.id,
        "source.original_pdf_attached",
        "source_document",
        source.id,
        {"version_id": version.id, "file_name": filename},
    )
    return updated
