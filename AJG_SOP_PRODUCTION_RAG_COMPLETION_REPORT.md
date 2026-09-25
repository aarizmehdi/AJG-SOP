# AJG SOP Production RAG Completion Report

Date: 2026-09-25  
Production organization: `ajt`

## Delivery identity

- Starting remote `main`: `0ecbfed7a252919d242469df107df3b0ef08160f`
- RAG implementation commit: `deb532435f25d913a304a72ed918186141d9cfe7`
- RAG merge commit: `a459605bf7b3b26569e903f91e65429d12afdac1`
- Production compatibility hotfix: `e719bcf95bdb0f4dba599d951b957f2503f14af5`
- Final tested application commit: `8cd425b92e744695e41ccd6e78e8b7fa7f0711ab`
- Implementation PR: [#5 Complete production Markdown RAG path](https://github.com/aarizmehdi/AJG-SOP/pull/5)
- Compatibility PR: [#6 Fix structured audit metadata startup compatibility](https://github.com/aarizmehdi/AJG-SOP/pull/6)

## Deployed versions

- Vercel project: `ajg-sop-web`
- Vercel production deployment: `dpl_2xT28yLKDPmkeSzZXrrAo3hHyBNe`
- Vercel production commit: `8cd425b92e744695e41ccd6e78e8b7fa7f0711ab`
- Vercel evidence: production build log cloned `main` at `8cd425b`; route `/admin/policies` returned HTTP 200.
- Railway service: `AJG-SOP`
- Railway tested restart deployment: `0da7caf6-5a1e-42dc-8b44-5506bc73b1b6`
- Railway source deployment: `e488c1c4-63ed-4207-a91d-ce1997420135`
- Railway image digest: `sha256:b159112d9d553287980c293a876b833fecaeb73eb104a27d080b8935852adc62`
- Railway health: `{"status":"ok","mode":"live"}`

## Implemented architecture

The production path is:

`private source -> raw parser result -> canonical SOP -> reviewed canonical SOP -> section chunks -> E5 passage embeddings -> staged Pinecone vectors -> ID/metadata verification -> Pinecone activation -> MongoDB publication -> authorized lexical and semantic retrieval -> fusion -> reranking -> DeepSeek -> citation and grounding verification`

MongoDB remains the canonical record. Pinecone remains derived, rebuildable retrieval data. The employee-facing retrieval service creates the authorized chunk set before either candidate retriever runs, filters Pinecone by tenant, publication status, and eligible chunk IDs, and revalidates evidence after reranking.

## Markdown parser fixes

- Added deterministic YAML-style front matter for `title`, `policy_number`/`sop_number`, and `effective_date`/`issue_date`.
- Kept missing dates and policy numbers null; the parser does not invent either field.
- Retained compatibility with `SOP #76`, `SOP-76`, and `Policy #93` labels.
- Fixed numeric section handling for both `1. Eligibility` and nested `1.1` headings.
- Preserved heading levels and parent heading paths.
- Preserved ordered lists, bullet lists, indentation levels, markers, and source line anchors.
- Converted GitHub-style Markdown tables into canonical table and table-cell records, including headers, rows, columns, text, and cell source anchors.
- Rendered complete canonical tables back to readable Markdown.
- Propagated extracted policy number and effective date to canonical policy/version records when the administrator did not supply them.
- Added an admin `.md` file picker while retaining pasted Markdown and structured text.

The accepted contract is documented in `docs/architecture/MARKDOWN_INGESTION_CONTRACT.md`.

## E5 and Pinecone verification

- Existing index: `aziz-jan-sop`
- Index architecture: managed Pinecone integrated inference; no index was created, replaced, or reconfigured.
- Metric: cosine
- Embedding provider: Pinecone-hosted E5 behind the application `EmbeddingProvider` boundary
- Verified model: `multilingual-e5-large`
- Verified dimension: 1024 for the model, document embedding, query embedding, and existing index
- Document semantics: `input_type=passage`
- Query semantics: `input_type=query`
- Truncation: `END`
- Production namespace: `aziz-jan-trust--ajt`
- Vector count before the synthetic policy: 0
- Vector count after publication: 4
- Expected vector IDs fetched before publication: 4 of 4 with `publication_status=staged`
- Expected vector IDs fetched after publication and after restart: 4 of 4 with `publication_status=published`

Publication activates and verifies Pinecone metadata before changing the MongoDB active version. An activation failure marks the new version failed while leaving the currently published version active.

## DeepSeek verification

- Provider: official DeepSeek API through the existing `LLMProvider` abstraction
- Base URL: `https://api.deepseek.com`
- Model: `deepseek-flash`
- Model availability was verified through the authenticated provider `/models` endpoint.
- The production key is stored only in Railway as `DEEPSEEK_API_KEY`; no key value is present in this report or the repository.
- Production generated a non-streamed structured answer, then passed local citation validation and grounding verification before release.

## Automated verification

Baseline before the milestone:

- Backend: 37 tests passed
- Frontend: 10 tests passed
- Backend Ruff and mypy passed
- Frontend typecheck, lint, format check, and production build passed

Final implementation validation:

- Backend: 52 tests passed with 78% total coverage
- Ruff: passed
- mypy: passed for 72 source files
- Frontend: 8 test files and 10 tests passed
- Frontend TypeScript typecheck: passed
- Frontend ESLint: passed
- Frontend Prettier check: passed
- Frontend production build: passed; 2,068 modules transformed
- npm audit: 0 vulnerabilities
- Gitleaks: scanned 30 commits and 1.63 MB; no leaks found
- PR #5 CI: `api`, `web`, `docker`, and `secrets` passed
- PR #6 CI: `api`, `web`, `docker`, and `secrets` passed
- Compatibility regression: 9 persistence and role-provisioning tests passed locally before PR #6

Local Docker was unavailable, so the successful GitHub `docker` job is the container-build evidence.

## Production endpoints exercised

- `GET /health`
- `GET /api/v1/profile/me`
- `GET /api/v1/admin/policies`
- `POST /api/v1/admin/policies`
- `POST /api/v1/admin/sources/import`
- `GET /api/v1/admin/sources/{source_id}/review`
- `PUT /api/v1/admin/sources/{source_id}/review`
- `POST /api/v1/admin/sources/{source_id}/approve`
- `GET /api/v1/admin/sources/{source_id}/original`
- `POST /api/v1/admin/versions/{version_id}/prepare-publication`
- `POST /api/v1/admin/versions/{version_id}/publish`
- `GET /api/v1/admin/policies/{policy_id}/viewer`
- `POST /api/v1/search`
- `GET /api/v1/policies/{policy_id}`
- `GET /api/v1/policies/{policy_id}/sources/{source_id}`
- `POST /api/v1/assistant/answer`
- `GET /api/v1/admin/operations/metrics`
- `GET /api/v1/admin/operations/retrieval-telemetry`

## Synthetic production acceptance result

The production-only synthetic policy is `policy-c8e532a633dd`, version `version-0eeb13d3c127`, source `source-0dc0d58846cb`. It contains front matter, H1/H2/H3 headings, paragraphs, ordered and nested items, bullets and nested bullets, a three-column table, and employee/manager section scopes.

- Canonical title: `Synthetic Warehouse Incident SOP`
- Canonical policy number: `SOP #RAG-2026-001`
- Canonical effective date: `2026-09-25`
- Canonical sections: 4
- Table header cells: `Severity`, `Notify`, `Deadline`
- Private original SHA-256: `cfa3181c1ee36e8bce5e39f84959f4558ea7ba32c0e4539a8ab3c8ce8c716ec6`
- The same R2 object hash was returned before and after Railway restart.

Authorized Employee query:

`Which form code records an inventory incident?`

- Search returned three authorized sections and included `AJG-41`.
- DeepSeek answer: `Form code AJG-41 records an inventory incident.`
- `verified=true`
- Citation count: 1
- The cited section was in the Employee's authorized scope.

Restricted test:

`What is ORCHID-729?`

- Employee search returned no restricted section and exposed no `ORCHID-729` text.
- Employee assistant request returned HTTP 503, releasing no unverified or unauthorized answer.
- The scoped SOP Admin search returned the manager-only section, proving the scope distinction.

No-evidence behavior was tested before publication with `What is the lunar travel allowance?`; the API returned `answerable=false`, `verified=true`, and no citations.

After Railway restart, the Employee reader returned three authorized sections, the allowed search still found `AJG-41`, all four Pinecone vectors remained published, and R2 returned the identical original.

## Role and access evidence

- All three Firebase UIDs were resolved through verified Firebase ID tokens and MongoDB employee profiles in organization `ajt`.
- Employee calling the admin policy endpoint: HTTP 403.
- SOP Admin calling the System Admin metrics endpoint: HTTP 403.
- System Admin calling the metrics endpoint: HTTP 200.
- Employee policy reader omitted the manager-only section.
- Employee original-source request for the mixed-access document: HTTP 404.
- SOP Admin with the complete management scope could inspect all four sections and the original.
- Employee semantic results were rechecked against eligible section IDs; the manager-only chunk never entered employee evidence.

## Production configuration

Railway service `AJG-SOP` now has these server-side provider settings:

- `EMBEDDING_PROVIDER=pinecone_e5`
- `EMBEDDING_MODEL=multilingual-e5-large`
- `PINECONE_NAMESPACE_PREFIX=aziz-jan-trust`
- `LLM_PROVIDER=deepseek`
- `DEEPSEEK_BASE_URL=https://api.deepseek.com`
- `DEEPSEEK_MODEL=deepseek-flash`
- protected `DEEPSEEK_API_KEY`

Pinecone and DeepSeek credentials are not exposed through any `VITE_*` variable.

## Remaining limitations

- OCR/parser selection and extraction accuracy still require the real SOP benchmark and human validation.
- Chunk sizing and overlap remain provisional; the current deterministic implementation creates one chunk per canonical section.
- `multilingual-e5-large` is verified against production infrastructure, but real English/Urdu/Roman Urdu retrieval quality still requires an evaluation corpus.
- The reranker remains the deterministic fixture implementation.
- Reciprocal-rank fusion weights remain provisional.
- The answerability gate is still an evidence-presence gate; production threshold calibration awaits real SOP evaluation.
- The synthetic PDF proves private R2 round-trip integrity, not representative PDF extraction quality. The verified Markdown supplied the canonical content.
- No confidential or real AJG/AJT SOP was ingested or published.
- Railway still reports that its legacy Config-as-Code format must be migrated before 2026-12-01; this did not affect the deployment.

## Rollback procedure

1. For a future bad release, redeploy Railway deployment `0da7caf6-5a1e-42dc-8b44-5506bc73b1b6` or image digest `sha256:b159112d9d553287980c293a876b833fecaeb73eb104a27d080b8935852adc62` and promote Vercel deployment `dpl_2xT28yLKDPmkeSzZXrrAo3hHyBNe`.
2. If the RAG implementation itself must be reverted, revert PR #5 while retaining the structured-audit compatibility fix from PR #6, deploy that commit, and keep MongoDB records intact.
3. Deactivate the isolated synthetic policy if it should no longer be searchable.
4. Delete only its four known vector IDs from namespace `aziz-jan-trust--ajt` if derived test data must be removed. Do not delete or reconfigure the index.
5. R2 originals and MongoDB canonical records are independent of Pinecone and can rebuild the retrieval index.

Do not redeploy the pre-hotfix image as-is: persisted role-provisioning audit metadata requires PR #6's JSON-compatible contract.

## Real-SOP readiness decision

The system is ready for the **first controlled, human-verified one-policy-per-Markdown ingestion** with its original PDF retained privately. It is not production/pilot validated for autonomous extraction or organization-wide launch. The first real SOP must go through human canonical review, controlled publication, multilingual retrieval benchmarking, and authorization validation before broader use.
