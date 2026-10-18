# OpenRouter provider and pooled LLM transport

Scope: backend provider integration from `main` commit
`929deeead5cb40ceea77ff9c8f71c4ef4fee1fd3`. Retrieval, chunking, indexing,
publication, conversation memory, answerability, citations and grounding logic are unchanged.
PR #18 and PR #19 are separate, unapproved work and are not incorporated here.

## Configuration and activation

The production target (after code review, merge and an approved deployment) is:

```dotenv
LLM_PROVIDER=openrouter
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=deepseek/deepseek-v4.1-flash-1017
OPENROUTER_FALLBACK_MODEL=deepseek/deepseek-v4-flash
OPENROUTER_API_KEY=<backend secret>
OPENROUTER_TEMPERATURE=0.2
OPENROUTER_ALLOWED_PROVIDERS=["relace","deepinfra"]
LLM_REQUEST_TIMEOUT_SECONDS=45
LLM_READ_TIMEOUT_SECONDS=20
LLM_MAX_CONNECTIONS=20
```

`OPENROUTER_ALLOWED_PROVIDERS` is an optional JSON array of approved OpenRouter provider slugs.
It narrows the eligible pool; it never overrides privacy restrictions. URLs must be HTTPS without
credentials/query/fragment, and redirects are disabled. Keys never belong in `VITE_*` variables.
Live settings reject fixture LLM selection and missing/blank credentials for the selected provider.
Local fixture mode must explicitly select `LLM_PROVIDER=fixture`; absent cloud credentials yield
an unavailable provider, never an automatic fixture answer.

Railway service: `AJG-SOP`, project `agile-integrity`, environment `production`.
On 2026-10-18 the OpenRouter key, base URL, primary/fallback models and temperature were staged
with `railway variable set ... --skip-deploys`. No activation, deployment or credential removal
was requested. `LLM_PROVIDER` remains `deepseek`; existing `DEEPSEEK_*` values are preserved.
The existing deployment remains the baseline commit above. Do not activate this configuration
until the compatible code is reviewed, merged and deployed with Aariz's approval.

## Request, pooling and failure boundaries

One `httpx.AsyncClient` per FastAPI lifespan/process is shared by LLM requests. Its pool defaults
to 20 connections, 10 keep-alive connections and 30-second keep-alive expiry. Phase timeouts are
connect 5s, read 20s, write 10s, pool 2s; each logical generation has a separate 45s wall-clock
deadline across all attempts and backoff. The outer lifespan closes the pool on normal shutdown,
startup errors and shutdown errors. No model request constructs its own client. Environment proxy
variables are not inherited by this client; trusted infrastructure egress must be configured
explicitly if required later.

`ChatCompletionTransport.complete(messages=..., response_model=..., model=...)` is generic over a
Pydantic response model. OpenRouter requests JSON Schema output with `strict: true`; defaulted
properties become explicit required properties in the wire schema. The returned content is also
validated locally with Pydantic strict types and the existing extra-field restrictions. Reasoning
uses OpenRouter's `reasoning: {enabled: false, exclude: true}`, not DeepSeek's `thinking` field.
Provider content is non-streaming. Existing whole-answer citation/grounding/access validation and
verified-only employee event streaming still determine release. Schema validity is not grounding.

The explicit availability-only policy is **at most two HTTP attempts per logical generation**:

1. Request the primary model.
2. Only after a network error, HTTPX timeout, HTTP 429, or HTTP 5xx, request the configured
   fallback once. No recursive fallback or third attempt occurs. Direct DeepSeek rollback instead
   retries the same model once, because it has no automatic model/provider fallback.

Backoff defaults to 250-350ms. A valid `Retry-After` up to 2s is honored, including HTTP dates;
a longer value stops the operation rather than retrying earlier than requested. Cancellation
propagates, and deadline expiry stops remaining work. An upstream timeout can already have incurred
cost, so retries can increase charges.

No transport/model fallback occurs for HTTP 400/401/402/403/404/408/422, moderation refusals,
`content_filter`, malformed/incomplete JSON, schema errors, invalid citations, failed grounding,
abstention or authorization failures. Provider errors are surfaced as sanitized typed failures;
upstream error bodies are not exposed. The assistant's existing single repair remains unchanged.
A malformed/ungrounded answer may therefore cause one new generation starting at the primary,
but is never routed to the fallback because it failed validation. Worst case: two generations,
two availability attempts each, four HTTP calls; there is no additional retry layer.

## Confidential-data routing and caching

Every OpenRouter request, including the fallback model, enforces:

```json
{"provider":{"zdr":true,"data_collection":"deny","require_parameters":true,
             "allow_fallbacks":false}}
```

OpenRouter's broader upstream fallback is disabled so it cannot fail over on rejections outside
our explicit policy. No `models` list, model router, plugins, tools, web search or response-cache
feature is enabled. An empty compatible provider pool fails closed; do not remove ZDR or loosen
parameter/privacy constraints to make a request succeed. Availability depends on account access,
credits, regional restrictions and the live intersection of privacy and parameter support.

OpenRouter documents opt-in prompt logging and opt-in data use. The organization owner must keep
both off in the OpenRouter account, disable training/retaining providers and review contractual
requirements before sending confidential SOPs. Request routing alone cannot attest to account
settings, agreements, provider policy compliance or data residency. No regional guarantee is made.

The system prompt has a stable prefix; repair feedback stays in the request-specific user payload.
No employee question, SOP evidence, answer, or conversation is cached by this application.
OpenRouter documents automatic DeepSeek prompt caching and endpoint-specific cache pricing.
It also explicitly allows transient **in-memory provider prompt caching under ZDR**. Therefore ZDR
must not be described as disabling every upstream cache. No explicit cache breakpoints, cache
identifiers, response caching or synthetic cache-hit claims are added. Discounts depend on the
selected endpoint and actual repeated-prefix hits, not merely the model family name.

Official sources inspected 2026-10-18:

- [API and usage/cost schema](https://openrouter.ai/docs/api_reference/overview)
- [Structured outputs and endpoint support](https://openrouter.ai/docs/guides/features/structured-outputs)
- [Routing, parameter support, data collection and ZDR](https://openrouter.ai/docs/guides/routing/provider-selection)
- [Zero-retention policies and in-memory caching](https://openrouter.ai/docs/guides/features/zdr)
- [OpenRouter data collection and opt-in logging](https://openrouter.ai/docs/guides/privacy/data-collection)
- [Prompt caching](https://openrouter.ai/docs/guides/best-practices/prompt-caching)
- [Reasoning controls](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens)
- [Errors and Retry-After](https://openrouter.ai/docs/api_reference/errors-and-debugging)

## Catalogue and live validation evidence

Public GETs to `/api/v1/models`, `/api/v1/models/{author}/{slug}/endpoints` and
`/api/v1/endpoints/zdr` confirmed both exact IDs on 2026-10-18. At inspection, 10 primary and
7 fallback endpoint rows had status 0, ZDR classification, `response_format` and
`structured_outputs`. This is a catalogue snapshot, not a promise of account-level availability.

| Exact model | Catalogue input / output / cached input USD per 1M tokens |
| --- | --- |
| `deepseek/deepseek-v4.1-flash-1017` | 0.15 / 0.60 / 0.003; time-based price overrides advertised |
| `deepseek/deepseek-v4-flash` | 0.091 / 0.182 / 0.0182 |

These are advertised catalogue rates, not guaranteed selected-endpoint prices or a cost estimator.
Endpoint pricing/discounts varied in the same API inspection. No rate is hard-coded in billing.

The opt-in `python -m scripts.llm.smoke_openrouter` uses only synthetic visitor-badge evidence,
starts no application services, and prints no model content. Each model is checked in isolation
with the real configured privacy restrictions, schema, citations and existing deterministic
grounding checks; it never substitutes the other model during this check. It returns nonzero
if either model fails, even when the other succeeds. Supply the key through the process's secret
environment, never a command argument, committed file or browser variable.

Initial real API result on 2026-10-18: primary passed schema/citation/deterministic-grounding
checks in one request (2,828ms, 343 input tokens, 151 output tokens, 0 cached tokens,
provider-reported cost USD 0.00010775). The fallback returned HTTP 429 on both bounded attempts;
follow-up diagnostics identified OpenInference as the failing upstream. The authenticated key
endpoint confirmed paid access with remaining credit; no credit limit was changed. Restricting
the eligible provider pool to `relace` and `deepinfra` resolved the synthetic fallback failure
without weakening `zdr`, `data_collection`, parameter support or upstream fallback restrictions.
Both exact models then passed schema, citation and deterministic-grounding checks in one request
each: primary 2,014ms / USD 0.00010775; fallback 6,759ms / USD 0.00006354. No SOPs or employee
records were used in these isolated checks. A catalogue-supported endpoint may still return 429;
the allowlist is operational configuration and must be revalidated when availability changes.
One synthetic request is not an accuracy benchmark, production latency percentile, or measured
pooling speedup. No cache savings were observed. Mock tests establish the fallback control flow.

## Metrics

Existing System Admin metrics expose process-local aggregates named
`llm_openrouter.<configured-model-with-slash-replaced>.*`:

- `request`: HTTP attempt count, failures, average/maximum latency in milliseconds.
- `failure_*`: sanitized timeout/network/status/schema/rejection category counts.
- `input_tokens`, `output_tokens`, `cached_tokens`, `cache_write_tokens`: totals when supplied,
  with `*_samples` counts to distinguish missing usage from actual zero usage.
- `reported_cost_usd` and `cost_samples`: only finite, nonnegative numeric `usage.cost` supplied
  by OpenRouter; no invented estimates when absent, no hard-coded price multiplication.
- `llm_openrouter.operation`: logical call count, failures and end-to-end latency including waits;
  `.retries`, `.fallbacks`, `.deadline_exceeded` count actual retry transitions/deadline expiry.

Usage is counted even when returned content subsequently fails validation, since the work may be
billable. Missing usage on failed/timed-out requests means observed totals may undercount actual
charges. Metrics contain no keys, prompts, evidence, answers, source IDs, employee IDs or upstream
error bodies. They reset on restart and are process-wide, not a durable billing ledger or
per-tenant chargeback system. Export/durable aggregation is outside this task.

## Integration and rollback

PR #19 adds `plan_query()` to `LLMProvider` and an `answer_mode` argument to generation, as well as
changing DeepSeek construction, answer prompts, lifecycle wiring and async grounding. Its interface
cannot be merged mechanically with this OpenRouter adapter: the approved integration must extend
the adapter for the new method/argument or instantiation/calls will fail. It must be integrated
manually after both PRs are reviewed: inject the lifespan-owned
client/transport into its planner and verifier, supply their own response models to `complete`,
retain this bounded failure/privacy policy, and do not reintroduce per-request AsyncClients.
This transport does not implement query planning or semantic grounding. Its model-specific metrics
must also be used for those extra calls. Existing error imports in `answer_generator` remain
re-exported, but the DeepSeek constructor now requires a transport instead of raw credentials.
PR #18's unconditional `DEEPSEEK_API_KEY` guard must become selected-provider-aware if integrated.

Controlled rollback uses `LLM_PROVIDER=deepseek`, existing `DEEPSEEK_API_KEY`,
`DEEPSEEK_BASE_URL=https://api.deepseek.com` and the existing `DEEPSEEK_MODEL`. This is a separately
approved configuration/deployment action, never automatic fallback from OpenRouter. Its privacy
terms must be reviewed separately. Keep OpenRouter secrets for an approved return to OpenRouter.
Never use fixture mode as production rollback. Search/policy reading remain independent of LLM
availability. This provider migration needs no Pinecone changes, publication change or re-index.

## Local verification on this branch

Environment for application tests: `APP_MODE=fixture`, `LLM_PROVIDER=fixture`,
`APP_NAME=Aziz Jan Group SOP Knowledge System`. No live secrets are used by those tests.

| Command | Result |
| --- | --- |
| `.venv/Scripts/python.exe -m ruff check .` | Passed |
| `.venv/Scripts/python.exe -m mypy apps services packages` | Passed, 99 source files |
| `.venv/Scripts/python.exe -m pytest --cov=apps --cov=services --cov=packages -p no:cacheprovider --basetemp .data/<fresh-directory>` | 221 passed, 1 skipped; total coverage 84% |
| `npm run typecheck` / `npm run lint` / `npm run format:check` | Passed |
| `npm run test` | Passed, 20 files / 51 tests |
| `npm run build` | Passed; existing bundle-size warning |
| `npm audit --audit-level=high` | Passed, 0 vulnerabilities |
| `python -m scripts.evaluation.run_fixture` | Passed; harness-shape check only, deliberately empty ranked results |
| Evaluation CLI with four existing synthetic English cases, synthetic access overlay and current-default fixture matrix | Gate passed, unauthorized retrieval/context 0; not a real SOP or E5 benchmark |

The single skipped test requires the unavailable private SOP corpus. The 141-case private-corpus
benchmark and real E5 accuracy were not run locally. Existing Starlette TestClient/AnyIO dependency
deprecation warnings remain; no dependency upgrades are part of this change. Initial sandboxed
pytest attempts failed on Windows temporary-directory ACLs; the complete suite passed with normal
filesystem permissions. Vite tests initially hit sandbox `spawn EPERM` and passed with normal
subprocess permissions. Docker is not installed locally; its existing CI job remains the check.
The new factory/transport/OpenRouter adapter together have 96% statement coverage in the full run.
