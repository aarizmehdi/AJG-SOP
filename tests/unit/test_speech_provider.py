from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from starlette.requests import Request

from apps.api.app.api.speech import speech_capabilities, transcribe_speech
from apps.api.app.models.organization import ApplicationRole, EmployeeProfile
from packages.contracts.common import Language
from services.speech.base import UnavailableSpeechToTextProvider


def employee() -> EmployeeProfile:
    return EmployeeProfile(
        id="employee-one",
        organization_id="ajt",
        identity_subject="fixture|employee",
        display_name="Employee",
        email="employee@example.test",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
    )


def request() -> Request:
    state = SimpleNamespace(speech_provider=UnavailableSpeechToTextProvider())
    return Request({"type": "http", "app": SimpleNamespace(state=state)})


@pytest.mark.asyncio
async def test_disabled_speech_provider_never_fakes_a_transcript() -> None:
    capabilities = await speech_capabilities(request(), employee())
    assert capabilities["enabled"] is False

    audio = UploadFile(
        filename="question.webm",
        file=BytesIO(b"recorded audio"),
        headers={"content-type": "audio/webm"},
    )
    with pytest.raises(HTTPException) as unavailable:
        await transcribe_speech(request(), employee(), Language.ROMAN_URDU, audio)
    assert unavailable.value.status_code == 503


@pytest.mark.asyncio
async def test_empty_voice_recording_is_rejected_before_provider_use() -> None:
    audio = UploadFile(filename="question.webm", file=BytesIO())
    with pytest.raises(HTTPException) as empty:
        await transcribe_speech(request(), employee(), Language.ENGLISH, audio)
    assert empty.value.status_code == 422
