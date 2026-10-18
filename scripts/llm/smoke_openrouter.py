"""Opt-in live check of both models, using synthetic evidence and no application records.

Requires OPENROUTER_API_KEY in the process environment. Never imports/starts FastAPI,
opens Mongo/R2/Pinecone, or prints model content or credentials. This is billable.
"""

import asyncio
import json

import httpx

from apps.api.app.config import Settings
from apps.api.app.services.llm_factory import build_llm_provider
from apps.api.app.services.metrics import MetricsRegistry
from packages.contracts.assistant import GeneratedAnswer
from packages.contracts.canonical import SourceLocator
from packages.contracts.common import Language
from packages.contracts.retrieval import AssistantEvidence
from services.assistant.answer_prompts import answer_messages
from services.assistant.citations import CitationValidator
from services.assistant.grounding import GroundingVerifier
from services.assistant.llm_errors import LLMResponseError, LLMUnavailableError
from services.assistant.openrouter import OpenRouterLLMProvider


async def main() -> int:
    config = Settings(_env_file=None, app_mode="fixture", llm_provider="openrouter")
    if not config.openrouter_api_key:
        print("OPENROUTER_API_KEY is required; no request made.")
        return 2
    metrics = MetricsRegistry()
    evidence = AssistantEvidence(
        organization_id="ajg-synthetic-check",
        chunk_id="synthetic-chunk",
        policy_id="synthetic-policy",
        version_id="synthetic-version",
        section_id="synthetic-section",
        policy_title="Synthetic Visitor Example",
        heading_path=("Visitor badge",),
        source=SourceLocator(source_document_id="synthetic-document", page_start=1),
        excerpt="Visitor badges must be returned by 5 PM.",
        full_text="Visitor badges must be returned by 5 PM.",
        fused_score=1,
    )
    passed = True
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(connect=5, read=config.llm_read_timeout_seconds, write=10, pool=2),
        limits=httpx.Limits(max_connections=2, max_keepalive_connections=2),
        trust_env=False,
        follow_redirects=False,
    ) as client:
        provider = build_llm_provider(config, client, metrics)
        assert isinstance(provider, OpenRouterLLMProvider)
        for model in (config.openrouter_model, config.openrouter_fallback_model):
            try:
                # Isolate each exact model: this check never substitutes the other model.
                result = await provider.transport.complete(
                    messages=answer_messages(
                        "When must the visitor badge be returned?",
                        [evidence],
                        Language.ENGLISH,
                        None,
                    ),
                    response_model=GeneratedAnswer,
                    model=model,
                )
                citations_ok = CitationValidator().validate(result.citations, [evidence])
                grounding_ok = GroundingVerifier().verify(result, [evidence])
                ok = result.answerable and citations_ok and grounding_ok
                passed = passed and ok
                print(
                    json.dumps(
                        {
                            "requested_model": model,
                            "schema_valid": True,
                            "citations_valid": citations_ok,
                            "grounding_valid": grounding_ok,
                            "passed": ok,
                        }
                    )
                )
            except (LLMUnavailableError, LLMResponseError) as error:
                passed = False
                print(
                    json.dumps(
                        {
                            "requested_model": model,
                            "passed": False,
                            "error_type": type(error).__name__,
                            "reason": str(error),
                        }
                    )
                )
    print(json.dumps({"metrics": metrics.snapshot()}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
