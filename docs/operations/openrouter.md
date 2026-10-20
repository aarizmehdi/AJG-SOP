# OpenRouter provider and pooled LLM transport

The provider rollout below records PR #22 from baseline `929deeead5cb40ceea77ff9c8f71c4ef4fee1fd3`.
PR #19 now integrates answerability and semantic verification with this same transport; see
[Assistant operations](assistant-v2.md). Retrieval, chunking, indexing and publication remain
unchanged. PR #18 remains separate and is not incorporated here.

## Configuration and activation

The active Railway production configuration (verified 2026-10-18) is:

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
PR #22 merged as `499c286475ca8addfb71a5227ad445c8b4acf597` after all six checks passed.
Railway automatically deployed that commit first with the retained direct DeepSeek selection
(`c793663f-ff4d-45a6-851a-4e91b2a7642b`). After health passed, selecting OpenRouter triggered
deployment `8356c6cb-2c5c-45d6-9840-f585dbe8e61f`, SUCCESS at the same commit.
Existing `DEEPSEEK_*` credentials/configuration were preserved. The allowlist was staged with
`--skip-deploys` before activation. No provider credentials are committed or copied to Vercel.
Vercel production `dpl_9RSDonMWvS7yGDySkGrLzBgqa9px` also deployed the merge commit,
READY on `main`; its existing live API/Firebase configuration needed no change.
Subsequent documentation-only deployments retain these application/configuration semantics.

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
but is never routed to the fallback because it failed validation. With PR #19, the maximum is
one answerability call plus two generation/verification pairs, each with at most two availability
attempts: ten HTTP calls in the longest repair/fallback path. Each logical call has its own 45s
deadline; this is not a 45s deadline for the complete assistant turn. Normal supported answers
use one gate, one generation and one semantic verification. Deterministic overviews/empty retrieval
use no model calls. There is no paid planner or additional retry layer.

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

Account inspection caveat: although Aariz reported enabling non-frontier account ZDR, the signed-in
account containing the production key showed **All other models = off** on its Privacy page at
rollout inspection. Paid/free training, free prompt publication and the 1% data-discount switches
were off. No account-wide switches or key budgets were changed. Do not mistake the reported
account preference for independently confirmed enforcement: this adapter explicitly requires ZDR
and denies data collection on every call, independently of that account default. Workspace input/
output logging opt-ins and contractual guarantees were not independently audited in this rollout.

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

PR #19's composition root injects one transport into generation, `AnswerabilityResult` evaluation
and `SemanticVerificationResult` checks. All three therefore share pooling, privacy, selected
models, schema validation, availability-only fallback and model-specific usage metrics. Factories
without a shared transport return unavailable gate/verifier components rather than constructing
an independent OpenRouter client. Legacy raw-credential gate/verifier compatibility accepts only
the direct HTTPS DeepSeek host, and is not used by the live application composition root.
Query planning/reference resolution is deterministic for both adapters and does not incur model
calls. `answer_mode` reaches OpenRouter generation; planner/verifier logic remains outside the
generic transport. Existing error imports in `answer_generator` remain re-exported.
PR #18's unconditional `DEEPSEEK_API_KEY` guard must become selected-provider-aware if integrated.

Controlled rollback uses `LLM_PROVIDER=deepseek`, existing `DEEPSEEK_API_KEY`,
`DEEPSEEK_BASE_URL=https://api.deepseek.com` and the existing `DEEPSEEK_MODEL=deepseek-flash`.
This is an explicit operational action, never automatic fallback from OpenRouter. Its privacy
terms must be reviewed separately. Keep OpenRouter secrets for a return to OpenRouter.
Never use fixture mode as production rollback. Search/policy reading remain independent of LLM
availability. This provider migration needs no Pinecone changes, publication change or re-index.

From an authenticated Railway CLI linked to this repository:

```powershell
railway variable set LLM_PROVIDER=deepseek --service AJG-SOP --environment production
railway deployment list --service AJG-SOP --environment production --limit 3 --json
```

The variable change redeploys the compatible application. Wait for SUCCESS, then verify `/health`
returns `{"status":"ok","mode":"live"}`, unauthenticated admin overview returns 401, and an
authorized employee can search/read. Test generation separately: the pre-migration direct provider
configuration existed in production but was not newly benchmarked for answer quality here. To
return, revalidate both OpenRouter models and privacy/allowlist, set `LLM_PROVIDER=openrouter` with
the same command and repeat deployment/authenticated answer checks. Never redeploy an unmerged
local checkout or switch data/embedding/index settings to repair an LLM outage. If a code rollback
is required, use Railway's prior deployment controls with a configuration compatible with that
revision; revisions before #22 cannot run `LLM_PROVIDER=openrouter`.

## Production verification — 18 October 2026

- `/health`: 200, live; anonymous overview, policy list and assistant: 401.
- Existing enabled Firebase identities were verified by UID and exchanged for real ID tokens;
  no users, roles, claims or memberships were created/changed. Employee and SOP Admin received
  403 on System Admin overview/users/metrics; System Admin received 200.
- Employee saw both published SOP collections, search returned eight authorized results and the
  canonical reader returned 35 sections for the inspected collection. A browser session independently
  exercised the actual Vercel UI, search, document headings/lists/tables, assistant and citation link
  navigation to the exact canonical section.
- An account whose scope excludes these collections received reader 404, zero search results and
  an assistant `no_answer` with zero citations. An employee's original-document admin endpoint
  returned 403. No access scopes were temporarily expanded for testing.
- A precise policy question returned HTTP 200 / `policy_answer` / `verified=true` with two citations.
  An independent read-only Mongo check confirmed cited chunks were published, active, authorized
  and matched citation metadata; the existing deterministic grounding verifier passed.
- Real event streams emitted retrieving/reading/generating/verifying progress before `answer_start`
  and any `answer_delta`, then sources and `done(verified=true)`. One run used the existing single
  repair, reverified and only then released answer text. No unverified draft text was released.
- System Admin process metrics after nine live application model calls showed zero HTTP/provider/
  schema failures, 49,276 input tokens, 2,973 output tokens, 36,096 reported cached-input tokens and
  USD 0.002731568 reported cost; average model-request latency 1,817ms, maximum 3,131ms. These are
  a small process snapshot, not percentiles, a billing ledger or a quality benchmark. Abstentions
  and grounding repairs can still occur when transport requests succeed.
- Railway logs showed clean startup and successful assistant HTTP requests with no observed
  `request_failed`, `mutation_flush_failed` or `shutdown_flush_failed` markers in the inspected
  deployment log window. Inspection/reporting extracted only counts/statuses, not SOP/answer text.
- Both exact models passed isolated real API schema/citation/grounding checks under the production
  allowlist/privacy options. A separate synthetic controlled-outage probe injected **one local
  primary 503**, then used the real HTTP pool/OpenRouter fallback: DeepInfra served the exact
  fallback ID with HTTP 200 in 3,142ms, USD 0.00006309. There were exactly two attempts and one
  fallback. The outage was not induced in the shared production application. Actual total-provider
  outage handling and no-answer-text release are covered by mocked integration tests; no deliberate
  production outage or private SOP disclosure was used to exercise those failures.
- Mongo content collection counts and SHA-256 fingerprints matched the read-only pre-rollout
  baseline: two policies, versions, sources, canonicals, parser results and ingestion jobs each;
  71 retrieval chunks. Pinecone still had the same 71 vector IDs/count. No canonical rewrite,
  publication, deletion, R2 mutation, re-index or vector write occurred. No R2 content was needed.
- PR #18 remained open/unmerged at `e142dd0cd735a9a3eddbf52298573d5ebf170bbb` and PR #19 at
  `2c99e10bbfd2e1658a48f9a3bb0071e298c08a23`; neither branch was modified.

Limits observed: a broad procedure question safely abstained, while the precise signatory question
was answered with sources. This migration does not claim retrieval/grounding acceptance or change
those components; PR #18/#19 remain separate. Legacy identity data includes an employee profile
whose Firebase identity no longer exists, and a System Admin profile email differs from Firebase;
current UID-bound authentication still passed and those records were left unchanged. Railway SSH
was unavailable because this machine has no registered/local SSH key; no new SSH access was created.
Provider live probes ran externally with the production account's secret and routing configuration.
Railway warns its current Config-as-Code format stops working after 2026-12-01; migration of that
deployment format remains separate work. This is a verified provider rollout, not blanket product
or SOP-quality readiness.

## Local verification on this branch

Environment for application tests: `APP_MODE=fixture`, `LLM_PROVIDER=fixture`,
`APP_NAME=Aziz Jan Group SOP Knowledge System`. No live secrets are used by those tests.

| Command | Result |
| --- | --- |
| `.venv/Scripts/python.exe -m ruff check .` | Passed |
| `.venv/Scripts/python.exe -m mypy apps services packages` | Passed, 99 source files |
| `.venv/Scripts/python.exe -m pytest --cov=apps --cov=services --cov=packages -p no:cacheprovider --basetemp .data/<fresh-directory>` | 224 passed, 1 skipped after rollout review fix; total coverage 84% |
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
