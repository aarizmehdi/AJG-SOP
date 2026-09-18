from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict

from packages.contracts.common import Language


class SpeechTranscription(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    detected_language: str
    raw_transcript: str
    normalized_transcript: str


class SpeechProviderUnavailable(RuntimeError):
    pass


class SpeechToTextProvider(ABC):
    @property
    @abstractmethod
    def available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def transcribe(
        self,
        audio: bytes,
        media_type: str,
        response_language: Language,
    ) -> SpeechTranscription:
        """Recognize speech and normalize it into the selected product language."""
        raise NotImplementedError


class UnavailableSpeechToTextProvider(SpeechToTextProvider):
    @property
    def available(self) -> bool:
        return False

    async def transcribe(
        self,
        audio: bytes,
        media_type: str,
        response_language: Language,
    ) -> SpeechTranscription:
        del audio, media_type, response_language
        raise SpeechProviderUnavailable("Speech transcription provider is not configured")
