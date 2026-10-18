"""Pooled JSON transport reusable by generation and future planner/verifier adapters.

No prompts, responses, request IDs or HTTP error bodies are retained in telemetry.
Each operation makes at most two attempts, under one wall-clock deadline. Model
fallback is explicit here, never delegated to OpenRouter's broader fallback rules.
"""

import asyncio
import math
import random
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import perf_counter
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, Field, ValidationError

from apps.api.app.services.metrics import MetricsRegistry
from services.assistant.llm_errors import (
    LLMAvailabilityError,
    LLMRejectedError,
    LLMResponseError,
    LLMUnavailableError,
)

Result = TypeVar("Result", bound=BaseModel)


class CompletionMessage(BaseModel):
    content: str | None = None
    refusal: str | None = None


class CompletionChoice(BaseModel):
    message: CompletionMessage
    finish_reason: str | None = None
    error: dict[str, Any] | None = None


class CompletionEnvelope(BaseModel):
    choices: list[CompletionChoice] = Field(min_length=1, max_length=1)


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Make optional/defaulted Pydantic properties explicit in the wire schema."""
    schema = model.model_json_schema()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("default", None)
            if "properties" in node:
                node["required"] = list(node["properties"])
                node["additionalProperties"] = False
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)
    return schema


class ChatCompletionTransport:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        provider_id: str,
        api_key: str,
        base_url: str,
        metrics: MetricsRegistry,
        request_timeout_seconds: float = 45,
        structured_schema: bool = True,
        options: Mapping[str, object] | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError(f"Missing {provider_id.upper()}_API_KEY")
        url = httpx.URL(base_url)
        if url.scheme != "https" or not url.host or url.userinfo or url.query or url.fragment:
            raise ValueError("LLM base URL must be HTTPS without credentials, query or fragment")
        if not math.isfinite(request_timeout_seconds) or request_timeout_seconds <= 0:
            raise ValueError("LLM request deadline must be finite and positive")
        self.client = client
        self.provider_id = provider_id
        self._key = api_key
        self._url = base_url.rstrip("/") + "/chat/completions"
        self.metrics = metrics
        self.deadline = request_timeout_seconds
        self.structured_schema = structured_schema
        self.options = dict(options or {})

    async def complete(
        self,
        *,
        messages: Sequence[Mapping[str, str]],
        response_model: type[Result],
        model: str,
        fallback_model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1200,
    ) -> Result:
        started = perf_counter()
        failed = True
        try:
            async with asyncio.timeout(self.deadline):
                for attempt in range(2):
                    selected = fallback_model if attempt and fallback_model else model
                    if attempt:
                        self.metrics.increment(f"llm_{self.provider_id}.retries")
                        if fallback_model:
                            self.metrics.increment(f"llm_{self.provider_id}.fallbacks")
                    try:
                        result = await self._attempt(
                            messages, response_model, selected, temperature, max_tokens
                        )
                        failed = False
                        return result
                    except LLMAvailabilityError as error:
                        if attempt or (error.retry_after is not None and error.retry_after > 2):
                            raise
                        delay = (
                            error.retry_after
                            if error.retry_after is not None
                            else 0.25 + random.uniform(0, 0.1)
                        )
                        await asyncio.sleep(delay)
        except TimeoutError:
            self.metrics.increment(f"llm_{self.provider_id}.deadline_exceeded")
            raise LLMAvailabilityError("deadline_exceeded") from None
        finally:
            self.metrics.observe(
                f"llm_{self.provider_id}.operation",
                (perf_counter() - started) * 1000,
                failed=failed,
            )
        raise AssertionError("Unreachable retry state")

    async def _attempt(
        self,
        messages: Sequence[Mapping[str, str]],
        response_model: type[Result],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> Result:
        prefix = f"llm_{self.provider_id}.{model.replace('/', '_')}"
        response_format: dict[str, object] = {"type": "json_object"}
        if self.structured_schema:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "strict": True,
                    "schema": strict_json_schema(response_model),
                },
            }
        payload = {
            **self.options,
            "model": model,
            "messages": list(messages),
            "response_format": response_format,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        started = perf_counter()
        failed = True
        try:
            try:
                response = await self.client.post(
                    self._url, headers={"Authorization": f"Bearer {self._key}"}, json=payload
                )
            except httpx.TimeoutException:
                raise LLMAvailabilityError("timeout") from None
            except (httpx.NetworkError, httpx.RemoteProtocolError):
                raise LLMAvailabilityError("network") from None
            except httpx.RequestError:
                raise LLMRejectedError("LLM transport configuration failure") from None
            try:
                body = response.json()
            except ValueError:
                body = None
            status = response.status_code
            if isinstance(body, dict):
                self._usage(prefix, body.get("usage"))
            if not 200 <= status < 300 and status != 429 and not 500 <= status <= 599:
                raise LLMRejectedError(f"LLM request rejected: http_{status}")
            if isinstance(body, dict):
                choices = body.get("choices")
                if isinstance(choices, list):
                    for item in choices:
                        if isinstance(item, dict):
                            message = item.get("message")
                            if item.get("finish_reason") == "content_filter" or (
                                isinstance(message, dict) and message.get("refusal")
                            ):
                                raise LLMRejectedError("LLM moderation refusal")
                            # A per-choice rejection must outrank an ambiguous 5xx,
                            # just like a top-level rejection. Inspect all refusals
                            # before classifying any availability error.
                            error = item.get("error")
                            if error and not self._availability_error(error):
                                raise LLMRejectedError("LLM provider rejected the request")
                self._error(body.get("error"), self._retry_after(response))
            if status == 429 or 500 <= status <= 599:
                raise LLMAvailabilityError(f"http_{status}", self._retry_after(response))
            try:
                envelope = CompletionEnvelope.model_validate(body, strict=True)
            except ValidationError:
                raise LLMResponseError("Invalid LLM completion envelope") from None
            choice = envelope.choices[0]
            self._error(choice.error)
            if choice.message.refusal or choice.finish_reason == "content_filter":
                raise LLMRejectedError("LLM moderation refusal")
            finishes = {"stop"} if self.structured_schema else {None, "stop"}
            if choice.finish_reason not in finishes or not choice.message.content:
                raise LLMResponseError("Incomplete LLM answer")
            try:
                result = response_model.model_validate_json(choice.message.content, strict=True)
            except (ValidationError, ValueError):
                raise LLMResponseError("LLM content failed schema validation") from None
            failed = False
            return result
        except LLMAvailabilityError as error:
            self.metrics.increment(f"{prefix}.failure_{error.reason}")
            raise
        except LLMResponseError:
            self.metrics.increment(f"{prefix}.failure_schema")
            raise
        except LLMUnavailableError:
            self.metrics.increment(f"{prefix}.failure_rejected")
            raise
        finally:
            self.metrics.observe(
                f"{prefix}.request", (perf_counter() - started) * 1000, failed=failed
            )

    @staticmethod
    def _availability_error(error: object) -> bool:
        if not isinstance(error, dict):
            return False
        code = error.get("code")
        return type(code) is int and (code == 429 or 500 <= code <= 599)

    @staticmethod
    def _error(error: object, retry_after: float | None = None) -> None:
        if not error:
            return
        if isinstance(error, dict) and ChatCompletionTransport._availability_error(error):
            raise LLMAvailabilityError(f"http_{error['code']}", retry_after)
        raise LLMRejectedError("LLM provider rejected the request")

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        value = response.headers.get("retry-after")
        if not value:
            return None
        try:
            seconds = float(value)
        except ValueError:
            try:
                seconds = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                return None
        return max(0, seconds) if math.isfinite(seconds) else None

    def _usage(self, prefix: str, usage: object) -> None:
        if not isinstance(usage, dict):
            return
        values = {
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
        }
        details = usage.get("prompt_tokens_details")
        if isinstance(details, dict):
            values["cached_tokens"] = details.get("cached_tokens")
            values["cache_write_tokens"] = details.get("cache_write_tokens")
        for name, value in values.items():
            if type(value) is int and value >= 0:
                self.metrics.increment(f"{prefix}.{name}", value)
                self.metrics.increment(f"{prefix}.{name}_samples")
        cost = usage.get("cost")
        if (
            isinstance(cost, (int, float))
            and not isinstance(cost, bool)
            and math.isfinite(cost)
            and cost >= 0
        ):
            self.metrics.increment(f"{prefix}.reported_cost_usd", cost)
            self.metrics.increment(f"{prefix}.cost_samples")
