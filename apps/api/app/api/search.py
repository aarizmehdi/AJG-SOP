from typing import cast

from fastapi import APIRouter, HTTPException, Request, Response, status

from apps.api.app.auth.dependencies import CurrentProfile
from apps.api.app.services.policy_reader_service import PolicyReaderService
from packages.contracts.retrieval import (
    PolicyReaderDocument,
    SearchRequest,
    SearchResponse,
)
from services.retrieval.retriever import RetrievalService

router = APIRouter(tags=["employee-knowledge"])


@router.post("/search")
async def search(
    request: Request, payload: SearchRequest, profile: CurrentProfile
) -> SearchResponse:
    retriever = cast(RetrievalService, request.app.state.retrieval_service)
    evidence = await retriever.retrieve(profile, payload.query, payload.limit)
    return SearchResponse(results=evidence, query=payload.query, language=payload.language)


@router.get("/policies/{policy_id}")
async def read_policy(
    request: Request, policy_id: str, profile: CurrentProfile
) -> PolicyReaderDocument:
    reader = cast(PolicyReaderService, request.app.state.policy_reader_service)
    policy = reader.read_policy(profile, policy_id)
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return policy


@router.get("/policies/{policy_id}/sources/{source_id}")
async def read_original_source(
    request: Request, policy_id: str, source_id: str, profile: CurrentProfile
) -> Response:
    reader = cast(PolicyReaderService, request.app.state.policy_reader_service)
    result = await reader.read_original(profile, policy_id, source_id)
    if not result:
        # Deliberately avoid disclosing whether an unauthorized source exists.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    source, content = result
    safe_name = source.file_name.replace('"', "")
    return Response(
        content=content,
        media_type=source.media_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )
