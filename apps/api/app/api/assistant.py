"""Assistant JSON and verified-only event-stream endpoints."""

import asyncio
import json
from collections.abc import AsyncIterator
from time import perf_counter
from typing import cast

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from apps.api.app.auth.dependencies import CurrentProfile
from apps.api.app.services.assistant_service import AssistantService, VerificationError
from packages.contracts.assistant import AssistantRequest, VerifiedAnswer
from packages.contracts.retrieval import AssistantEvidence
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
            profile, payload.question, payload.language, payload.history
        )
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
    """Progress is immediate; answer deltas begin only after full verification."""

    async def events() -> AsyncIterator[str]:
        queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
        service = _service(request)
        started = perf_counter()

        async def work() -> None:
            try:
                result, context = await service.answer_with_context(
                    profile,
                    payload.question,
                    payload.language,
                    payload.history,
                    lambda stage: queue.put_nowait(("status", {"stage": stage})),
                )
                await queue.put(("result", (result, context)))
            except (LLMUnavailableError, VerificationError):
                await queue.put(("error", {"code": "answer_unavailable"}))
            except Exception:
                await queue.put(("error", {"code": "answer_unavailable"}))

        task = asyncio.create_task(work())
        try:
            while True:
                if await request.is_disconnected():
                    task.cancel()
                    break
                try:
                    name, data = await asyncio.wait_for(queue.get(), timeout=0.5)
                except TimeoutError:
                    continue
                if name == "status":
                    if data == {"stage": "retrieving"}:
                        service._metric("assistant_first_status", started)
                    yield _event(name, data)
                    continue
                if name == "error":
                    yield _event(name, data)
                    break
                result, context = cast(tuple[VerifiedAnswer, list[AssistantEvidence]], data)
                try:
                    await service.assert_release_authorized(profile, context)
                    yield _event(
                        "answer_start",
                        {
                            "kind": result.kind,
                            "answerable": result.answerable,
                            "language": result.language,
                            "verified": result.verified,
                        },
                    )
                    for offset in range(0, len(result.answer), 160):
                        await service.assert_release_authorized(profile, context)
                        if offset == 0:
                            service._metric("assistant_first_verified_delta", started)
                        yield _event("answer_delta", {"text": result.answer[offset : offset + 160]})
                        await asyncio.sleep(0)
                    yield _event(
                        "sources",
                        {"citations": [item.model_dump(mode="json") for item in result.citations]},
                    )
                    yield _event("done", {"verified": True})
                    service._metric("assistant_response", started)
                except VerificationError:
                    yield _event("error", {"code": "answer_unavailable"})
                break
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


def _event(name: str, payload: object) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
