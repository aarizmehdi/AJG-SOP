import asyncio
import json
from collections.abc import AsyncIterator
from typing import cast

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from apps.api.app.auth.dependencies import CurrentProfile
from apps.api.app.services.assistant_service import AssistantService, VerificationError
from packages.contracts.assistant import AssistantRequest, VerifiedAnswer
from services.assistant.answer_generator import LLMUnavailableError

router = APIRouter(prefix="/assistant", tags=["assistant"])


def _service(request: Request) -> AssistantService:
    return cast(AssistantService, request.app.state.assistant_service)


@router.post("/answer")
async def answer(
    request: Request, payload: AssistantRequest, profile: CurrentProfile
) -> VerifiedAnswer:
    try:
        return await _service(request).answer(
            profile, payload.question, payload.language, payload.session_id
        )
    except PermissionError as error:
        raise HTTPException(status_code=404, detail="Conversation not found") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except LLMUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The SOP Assistant is temporarily unavailable. Search remains available.",
        ) from error
    except VerificationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The answer could not be verified and was not released.",
        ) from error


@router.post("/answer/events")
async def answer_events(
    request: Request, payload: AssistantRequest, profile: CurrentProfile
) -> StreamingResponse:
    """Streams truthful status events; answer content appears only in the final verified event."""

    async def events() -> AsyncIterator[str]:
        yield _event("status", {"stage": "retrieving", "message": "Searching authorized SOPs"})
        await asyncio.sleep(0)
        try:
            result = await _service(request).answer(
                profile, payload.question, payload.language, payload.session_id
            )
            yield _event("status", {"stage": "verified", "message": "Answer verified"})
            yield _event("answer", result.model_dump(mode="json"))
        except (LLMUnavailableError, VerificationError):
            yield _event(
                "error",
                {
                    "code": "answer_unavailable",
                    "message": "No answer was released because verification did not complete.",
                },
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


def _event(name: str, payload: object) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
