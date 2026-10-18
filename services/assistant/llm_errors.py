"""Content-free provider errors; availability is distinct from invalid model output."""


class LLMUnavailableError(RuntimeError):
    pass


class LLMAvailabilityError(LLMUnavailableError):
    """Only network/timeouts, HTTP 429 and HTTP 5xx permit transport/model retry."""

    def __init__(self, reason: str, retry_after: float | None = None) -> None:
        super().__init__(f"LLM availability failure: {reason}")
        self.reason = reason
        self.retry_after = retry_after


class LLMRejectedError(LLMUnavailableError):
    """A non-retryable credentials, policy, moderation or routing rejection."""


class LLMResponseError(RuntimeError):
    """Provider content failed validation; only the existing assistant repair may retry."""
