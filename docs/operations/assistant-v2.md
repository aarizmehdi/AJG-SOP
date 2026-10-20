# AJG SOP Assistant v2 operations

The Assistant uses the existing published-policy retrieval service. Search excerpts remain short; generation expands only the selected, currently authorized chunks to at most 5,000 characters each and 16,000 characters total. The context budget reserves space for every authorized result, so earlier long chunks cannot silently exclude a later exact-match section. Short sections leave more space for subsequent results. Retrieval authorization, lexical/semantic fusion, publication state, and source-file rules remain unchanged.

`LLM_PROVIDER=openrouter` selects the OpenRouter adapter with the approved primary and availability-only fallback. Configure `OPENROUTER_API_KEY` as a backend Railway secret. See [OpenRouter operations](openrouter.md) for model IDs, shared pooling, bounded retries, privacy, metrics, activation and rollback. `LLM_PROVIDER=deepseek` explicitly selects the retained direct DeepSeek adapter. Fixture tests use `LLM_PROVIDER=fixture`, which is prohibited in live mode. If the model provider is unavailable, employee search and policy reading remain usable.

The authenticated `POST /api/v1/assistant/answer/events` accepts `question`, `language`, and up to 16 bounded `history` turns. It sends event-stream `status` events during real work, then `answer_start`, verified `answer_delta`, `sources`, and `done`. A technical failure yields `error` without unverified model text. The JSON `/answer` endpoint remains available for clients that cannot stream. Smalltalk, clarification, out-of-scope and no-answer responses are deterministic where possible.

PR #19 adds a deterministic reference planner, a structured answerability gate and semantic claim verification. Planning does not call a model. Client history is only a search/reference hint: it is never appended to authorized evidence or sent as policy truth to generation or verification. The frontend sends at most four completed user/assistant pairs, bounded to 12,000 characters; history is held only in page memory. Both retrieval and generation use the resolved question for an ordinal or attribute follow-up. Empty authorized retrieval/context stops before any paid gate/generation/verifier request.

For a broad SOP request, authorized published headings come from the canonical policy reader. An overview displays at most eight headings, interleaving policies for mixed results and indicating omitted headings. `section_options` in JSON and the SSE `sources` event provide exact policy/version/section/source navigation metadata. These are **not chunk citations**. A heading gets a citation only when the retrieved policy, version, section, heading path and source metadata match. Unmatched headings remain canonical navigation, with links to the complete reader and an Ask action that fills the composer. Overview clarification responses can therefore contain valid citations as well as uncited navigation. No unrelated fallback chunk is used. Publication, membership and section access are rechecked before release and before streamed answer segments/navigation are emitted.

An exact policy title in an overview request selects that policy from the employee's authorized catalog, even when retrieval ranks a different collection first. Its canonical navigation does not acquire citations from that other collection. A scoped specific question such as “According to SOP X, who must sign?” must reach answerability and generation; mentioning SOP alone does not trigger an overview.

Live answerability, generation and semantic verification share the lifespan-owned `ChatCompletionTransport`, configured models, allowlist, strict JSON Schema and privacy settings. Cloud gate/verifier factories without that transport fail closed. Malformed result types or unexpected fields do not authorize an answer. Only cited authorized chunks reach semantic verification; all supported claims must pass, as well as deterministic citation/date/number checks. Existing one-repair maximum is preserved. An LLM verifier remains fallible; passing it is not independent proof of every claim.

Deterministic SOP-reference checks compare complete identifiers, including slash/dot/hyphen suffixes, while ignoring case and prefix typography such as `Sop#` versus `SOP #`. Different identifiers remain rejected even if their individual numbers appear elsewhere in the cited text.

Metrics expose retrieval, LLM, grounding verification, total assistant work, response kind, repair count, first status, first verified delta, and completed stream latency. They contain no question or answer text. Retrieval traces contain query length and chunk IDs, not raw queries. Existing historical Mongo `chat_sessions` and `chat_messages` are left untouched; Assistant v2 neither loads nor writes them.

Acceptance scope is English corpus and English queries using multilingual E5/Pinecone. Existing product-language controls remain; no multilingual acceptance or BGE-M3 work is included. Benchmark real AJG SOP examples for answerability, citation precision, grounding, long-section context, ambiguous follow-ups, latency and false rejections. Fixture verification does not establish live-model quality. `smoke_test.py` invokes an internal service with a synthetic profile; it does **not** perform Firebase login or an authenticated HTTP API test. A passing production check must separately exercise real Firebase ID tokens, employee scope, deployed APIs and the browser. Review provider errors and verification failures without logging employee conversation text.

## Retrieval integration and future publication

`RETRIEVAL_RERANKER=none` preserves RRF order through an explicit reranker stage. The token-overlap `fixture` and opt-in `lexical_heuristic` adapters remain available for controlled comparisons. Semantic and lexical candidate generation, fusion, reranking and authorization revalidation remain separate. A hosted-E5 comparison on the same 124 English cases (103 retrieval-scored) favored preserved order over the overlap heuristic: Recall@5 96.26% vs 94.85%, MRR 0.8631 vs 0.7992, nDCG@5 0.8853 vs 0.8299. These are in-memory rankings with real hosted embeddings, not measurements of a rebuilt production index or held-out acceptance results. Equal fusion weights are unchanged.

Exact lexical identifiers retain complete slash/dot/hyphen suffixes and qualified prefixes, including `SOP # 89`, `Sop# 2024/Gat/002`, `SOP-014` and `AJTM/STORE/SOP-1`. Distinct namespaces/suffixes do not acquire shared short aliases. Semantic filters partition large eligible-ID sets into bounded requests; every request retains tenant, published state, exact eligible chunk IDs and their active version IDs. Results are merged by score and post-filtered. No tenant/policy-only fallback broadens access. Runtime retrieval traces retain IDs/ranks/scores rather than chunk bodies.

Future live publication requires the exact E5 tokenizer. Docker installs the pinned public tokenizer with a SHA-256 check and sets `E5_TOKENIZER_PATH`; no SOP data goes to Hugging Face, and no tokenizer download occurs during a request. `tokenizers` is a lightweight tokenizer dependency, not a new embedding model/framework. Missing/invalid live tokenizer configuration fails startup instead of silently using fixture estimation. Fixture mode may use the explicit estimator, whose counts are not evidence of E5 accuracy. The complete `passage:` payload, including special tokens, targets 480 tokens with a conservative 507-token hard guard. The current hosted model reports a 507-input-token limit and maximum batch size 96; batches are capped at 64. `truncate=NONE` rejects oversize inputs instead of dropping their tail. Only bounded transient availability retries are allowed; invalid inputs are not retried. See the [Pinecone inference documentation](https://sdk.pinecone.io/python/how-to/inference/embeddings.html).

Tables repeat captions and column headers where they fit. Oversize row keys/headers use explicit row/column continuation coordinates; cell text is preserved, including single-word character splitting when necessary. Canonical source/access/section metadata remains attached. Long heading prefixes may be abbreviated for embeddings, while full headings remain in metadata and the reader. Nested-list context is repeated for split items. Hash headings take precedence; legacy files without a hash section hierarchy infer only a small allowlist of standalone bold document/section labels and emit human-review warnings. Ordinary bold clauses/notes are not promoted. Markdown parser version 3 records this compatibility behavior.

### Reproduce comparisons without touching production content

Use an ignored private corpus directory. Never commit SOP bodies, credentials, raw provider payloads or private diff reports. The comparison driver records source commits, archive/dataset/corpus hashes, runtime file hashes and whether the checkout is dirty. Use a clean committed tree for release evidence.

```powershell
uv run python scripts/install_e5_tokenizer.py --output .data/e5-tokenizer.json
$env:E5_TOKENIZER_PATH = (Resolve-Path .data/e5-tokenizer.json).Path
uv run python -m scripts.evaluation.compare_retrieval --baseline adf70c251d7ce22e0b8c3f00ceb1da9d72577ebd --corpus-dir .data/private-corpus --output-dir .data/retrieval-fixture-comparison
# Hosted comparison additionally requires an authorized backend-only PINECONE_API_KEY.
uv run python -m scripts.evaluation.compare_retrieval --baseline adf70c251d7ce22e0b8c3f00ceb1da9d72577ebd --corpus-dir .data/private-corpus --output-dir .data/retrieval-hosted-comparison --hosted
```

The hosted baseline uses an explicit **transport-only benchmark shim** for batching and bounded transient retries; its chunker, lexical ranking and historical END truncation remain unchanged. The unmodified main benchmark separately fails when its 193 inputs exceed the hosted 96-input request limit; no quality metric is invented for that failed configuration. Hosted comparisons use stateless inference and read-only index metadata, never upserts or production vector queries. CI's hash-embedding matrix is a regression/security gate, not hosted semantic quality. Its historical multilingual rows are not multilingual acceptance. Use English-only comparisons for this release.

Release comparison provenance: baseline `adf70c251d7ce22e0b8c3f00ceb1da9d72577ebd`, integrated runtime `06373db403fc9e0e7eaeee9ae12bd7b8e1ac3eb7`, clean checkout; English dataset SHA-256 `fd4b8daebb539ccfca8c6b2f2d480844859927cfeed15b2035eed2c7470b5423`, private corpus fingerprint `0be66f5b45e1a114`. Later reporting/whitespace corrections do not change the measured ranking/chunking code. Results include 124 cases, 103 retrieval-scored; the same cases were used during development, so this is not held-out acceptance.

| Evidence / configuration | Recall@1 | Recall@5 | MRR | nDCG@5 |
| --- | --- | --- | --- | --- |
| Fixture hash, main with overlap reranker | 0.2039 | 0.4922 | 0.3330 | 0.3625 |
| Fixture hash, integrated with preserved fusion | 0.3447 | 0.6214 | 0.4497 | 0.4899 |
| Hosted E5, main with overlap reranker (transport shim) | 0.3592 | 0.6937 | 0.5107 | 0.5501 |
| Hosted E5, main with preserved fusion (transport shim) | 0.2743 | 0.6500 | 0.4380 | 0.4824 |
| Hosted E5, integrated with preserved fusion | 0.7767 | 0.9626 | 0.8631 | 0.8853 |

Hosted category Recall@5, main overlap -> integrated preserved fusion: tables 0.1429 -> 1.0000 (14 cases), exact SOP references 0.6786 -> 0.9643 (28), nested lists 0.8000 -> 1.0000 (5), late evidence 0.9500 -> 1.0000 (20), broad questions 0.4875 -> 0.5375 (4). Broad nDCG@5 remains lower (0.5310 -> 0.4385): five chunk slots still do not represent every relevant section in a collection. Named-document overviews use the preserved canonical navigation path instead. No fusion-weight tuning or section-level deduplication was added. Unauthorized retrieval and technical failures were zero in these completed comparisons. Fixture hash semantic-only Recall@5 decreased (0.3422 -> 0.3131), reinforcing why fixture semantic scores cannot establish hosted E5 quality.

### Separate approved migration required for existing SOPs

Deploying retrieval code does **not** rebuild existing chunks/vectors or change canonical policies. Current published documents benefit from lexical matching/rank corrections immediately, but cannot receive newly split, fully embedded passages without a separate approved publication/index migration.

A read-only preview over the current unchanged production canonicals yields 36 -> 52 and 35 -> 61 chunks (71 -> 113 total), with zero canonical/source edits. Exact added/removed/changed chunk-ID lists are retained only in the local private preview. This is not authorization to apply those changes and is not a prediction for different authoritative source files. The local Markdown variants contain wording differences, so human approval is required before choosing replacement content.

Before any future migration:

1. Confirm authoritative PDFs/Markdown and human-reviewed canonical wording/structure. Recompute source/canonical diffs and exact chunk/vector differences for those approved inputs.
2. Capture Mongo, private R2 object and vector backups/fingerprints; retain the published active version.
3. Stage a **new policy version/source IDs** with new version-scoped chunk/vector IDs, existing organization/access metadata and unchanged E5/index dimension. Never overwrite published same-ID vectors during an in-place partial rebuild.
4. Validate token budgets, source/citation mapping, table/list/late-section recall, cross-tenant and department/location/role restrictions in staging. Failed staging must leave the published version active.
5. After explicit human approval, use the existing publication integrity boundary to activate only a completely indexed, verified version. Keep old version artifacts/vectors available for rollback, with eligibility tied to the active published version.
6. Verify production search/assistant/access and compare fingerprints. Roll back to the prior active version on failure. Cleanup or permanent deletion is a separately approved operation.

No step of that migration is executed by the retrieval integration release.
