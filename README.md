# Aziz Jan Trust SOP Knowledge System

Phase 1 foundation for secure SOP discovery and evidence-grounded explanations. The original
document and human-reviewed canonical SOP are authoritative; retrieval indexes and language-model
answers are derived artifacts.

## Local development

1. Copy `.env.example` to `.env.local` and select `APP_MODE=fixture` for the no-cloud local mode.
2. Install the web app with `npm install`.
3. Install Python 3.12 dependencies with `uv sync --python 3.12`.
4. Run the API with `uv run uvicorn apps.api.app.main:app --reload`.
5. Run the web app with `npm run dev`.

Fixture login accepts the identities shown on the login page. Live mode requires Auth0, MongoDB,
private S3-compatible storage, Pinecone, and configured model providers.

The Phase 1 LLM adapter is DeepSeek (`deepseek-v4-flash`) behind the provider-neutral
`LLMProvider` interface. Keep its key in ignored `.env.local` or a deployment secret manager. Search
and canonical policy reading do not depend on the LLM.

Voice input is implemented behind `VITE_VOICE_INPUT_ENABLED=false` and a provider-neutral backend
contract. It remains disabled until a real speech provider is selected and validated; fixture mode
does not fake transcription.

Architecture, authorization, provider configuration, operations, design behavior, ADRs, and the
real-SOP benchmark are documented under [`docs/`](docs/).

## Verification

```text
npm run typecheck && npm run lint && npm run format:check && npm run test && npm run build
uv run ruff check .
uv run mypy apps services packages
uv run pytest
uv run python -m scripts.evaluation.run_fixture
```

This foundation is not production- or pilot-ready until real SOP extraction, multilingual retrieval,
authorization, and grounding have been benchmarked and approved by a human reviewer.
