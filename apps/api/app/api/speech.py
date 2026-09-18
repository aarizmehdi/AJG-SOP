from typing import Annotated, cast

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from apps.api.app.auth.dependencies import CurrentProfile
from packages.contracts.common import Language
from services.speech.base import (
    SpeechProviderUnavailable,
    SpeechToTextProvider,
    SpeechTranscription,
)

router = APIRouter(prefix="/speech", tags=["speech"])


def _provider(request: Request) -> SpeechToTextProvider:
    return cast(SpeechToTextProvider, request.app.state.speech_provider)


@router.get("/capabilities")
async def speech_capabilities(request: Request, profile: CurrentProfile) -> dict[str, object]:
    del profile
    return {
        "enabled": _provider(request).available,
        "languages": [Language.ENGLISH.value, Language.URDU.value, Language.ROMAN_URDU.value],
        "auto_detect_spoken_language": True,
    }


@router.post("/transcribe")
async def transcribe_speech(
    request: Request,
    profile: CurrentProfile,
    response_language: Language,
    audio: Annotated[UploadFile, File()],
) -> SpeechTranscription:
    del profile
    content = await audio.read()
    if not content:
        raise HTTPException(status_code=422, detail="Audio recording is empty")
    try:
        return await _provider(request).transcribe(
            content,
            audio.content_type or "application/octet-stream",
            response_language,
        )
    except SpeechProviderUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
