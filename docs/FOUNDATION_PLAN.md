# Aziz Jan Trust SOP Knowledge System — Revised Foundation Plan

## 1. Delivery target and boundaries

Build the complete pre-SOP foundation: employee authentication, authorized search, grounded assistant, canonical policy reader, and administrator upload, extraction review, versioning, retrieval testing, and publication.

- Create a new `aziz-jan-sop-knowledge` repository inside the current workspace.
- Use React, strict TypeScript, Vite, FastAPI, Pydantic, MongoDB Atlas, private S3-compatible storage, and Pinecone.
- Provide a runnable local fixture mode alongside production service adapters. Clearly distinguish fixture testing from live integration verification.
- Support source-document architecture for **PDF, scanned PDF, images, DOCX, XLSX, Markdown, and pasted structured text now**.
- Keep parser selection, extraction accuracy, embedding models, reranking configuration, and retrieval thresholds provisional until actual SOP evaluation.
- Preserve the supplied logo and implement the PRD’s responsive blue/navy visual direction, accessibility, and English/Urdu/Roman Urdu language flows.

No implementation begins until this revised plan is approved. Cloud provisioning, deployment, and remote publication remain outside the initial local delivery.

## 2. Source documents, canonical representation, and review

### Complete source architecture

Every supported format receives an upload/import option, validated source model, private original storage, ingestion tracking, and parser-provider routing. Pasted text becomes an immutable source artifact with provenance.

Source records include organization, policy/version ownership, format, checksum, storage reference, processing status, and extraction provenance. Preserve multiple source documents per policy version.

Implement a provider-neutral `DocumentParser` boundary, fixture implementations, and Azure Document Intelligence/Docling adapter boundaries. Unconfigured capabilities must report their status honestly; provisional parsers must never imply verified accuracy.

### First-class canonical boundary

Enforce this pipeline:

**Original source → raw parser output → canonical SOP → human-reviewed canonical SOP → retrieval chunks**

- Provider-specific schemas stay inside extraction adapters and raw artifacts.
- Adapters normalize output into application-owned contracts.
- Review, versioning, chunking, retrieval, and frontend code depend only on those contracts.
- Preserve every stage with immutable artifact references, schema versions, and processing provenance.
- Generate readable Markdown from canonical data; structured canonical data remains authoritative.

The canonical model explicitly preserves:

- Chapters, heading levels, sections, subsections, hierarchy, and policy numbers.
- Paragraphs, ordered/unordered lists, nesting, and item relationships.
- Tables, headers, rows, cells, merged-cell relationships, and source associations.
- Source document identity, pages, bounding coordinates, and text spans where available.
- Format-specific locations such as spreadsheet sheets/cells and document block anchors; never fabricate page coordinates.
- Organization ownership, access metadata, stable section identity, and reviewed revision history.

### Side-by-side extraction review

Place the **original document/page on the left** and **editable canonical content on the right**.

- Use page/image previews, spreadsheet sheet views, or source-text views as appropriate.
- Link canonical sections and table cells to available source locations.
- Allow controlled correction of OCR text, heading hierarchy, section splits, lists, tables, and source mappings.
- Record corrections and approvals without modifying the original.
- Invalidate approval and downstream derived artifacts when reviewed content changes.

## 3. Identity, authorization, and retrieval isolation

Use official supported Auth0 SDKs for login and token lifecycle management; do not manually implement OAuth/PKCE. The backend validates authentication and resolves authorization from authoritative application data.

Make `organization_id` mandatory across organization-owned database records, canonical sections, chunks, jobs, conversations, audit events, and retrieval metadata. Derive organization context from validated membership rather than trusting client input.

### Access rules

Preserve the approved model:

- **OR within a dimension:** any selected department, location, or organizational role may match.
- **AND across dimensions:** all three dimension conditions must pass.
- Admin forms expose explicit **All departments / Selected departments**, equivalent location controls, and equivalent role controls.
- “Selected” requires at least one selection. Missing or empty scope never grants unrestricted access.
- Section scope inherits or narrows policy scope.
- SOP administrators manage only assigned areas; system administrators manage identities, roles, and organizational scopes.

### Shared hybrid retrieval

Search and assistant use the same pipeline:

**Authorized semantic candidates + authorized lexical/exact candidates → fusion → reranking → canonical evidence**

Keep semantic search, lexical/exact search, fusion, and reranking as separate interfaces and stages. Exact policy numbers and organizational terms must remain retrievable.

- Apply organization, access, and eligible-version constraints before both candidate searches.
- Use server-selected Pinecone organization namespaces plus mandatory metadata constraints.
- Revalidate canonical evidence before returning it or supplying it to generation.
- Isolate draft retrieval previews from employee published searches.
- Scope caches, histories, citations, downloads, and audit inspection to current authorization.
- Treat Pinecone as reproducible derived data; MongoDB retains canonical content.

Employees normally read authorized canonical sections. Full source downloads or previews require authorization to all content exposed by that source. Mixed-access originals must not be exposed through direct URLs or viewer assets.

## 4. Publication, assistant behavior, and application interfaces

### Ingestion and version integrity

Implement the PRD’s explicit ingestion lifecycle with durable jobs, retryable stages, idempotent processing, and truthful progress events.

- Detect identical files by SHA-256 within the appropriate organization boundary.
- Detect identical canonical sections without automatically deleting similar content.
- Require human structure approval before indexing and explicit publication after verification.
- Show **Added / Removed / Changed** sections, including old-versus-new content and access-scope changes.
- Preserve immutable published versions and support history, deactivation, and rollback.
- Build and verify new version indexes before switching the authoritative active-version reference.
- **Failed or incomplete indexing leaves the current published version active.**

### Verified assistant responses

Run answerability, grounded generation, citation validation, and grounding verification before releasing answer content.

- Progress events may describe retrieval, generation, and verification.
- **Do not stream unverified answer text to employees.**
- Validate citation identifiers, source locations, authorization, and membership in the supplied evidence set.
- Withhold failed verification results and return a controlled localized response.
- Distinguish insufficient evidence from temporary service failures.
- Preserve selected output language and prohibit unsupported organizational advice.
- Keep search and canonical policy reading usable without an LLM.

### Interfaces and UX

Provide versioned `/api/v1` endpoints and generated frontend contracts for profile/language, search, assistant sessions, policy reading, administration, ingestion, and publication.

Define application-owned contracts for parsers, canonical documents, source locators, permissions, chunks, embedding providers, candidate retrievers, fusion, rerankers, and verified assistant responses.

Implement employee and admin routes with deliberate loading, empty, error, unauthorized, and success states. Keep retrieval internals out of employee-facing views.

## 5. Implementation sequence and acceptance

Implement in this order:

1. Repository, CI, contracts, design system, identity, and organization boundaries.
2. All-format source modeling/upload, parser abstractions, canonical pipeline, and side-by-side review.
3. Version lifecycle, access administration, indexing, publication, and rollback.
4. Separate semantic/lexical retrieval, fusion, reranking, search, and policy reading.
5. Verified assistant, evaluation harness, end-to-end validation, and operational documentation.

Acceptance tests must prove:

- Every listed format can enter the source pipeline with preserved originals and explicit parser availability.
- Canonical hierarchy, lists, tables, coordinates, and access metadata survive processing and review.
- No provider-specific extraction schema escapes its adapter boundary.
- OR-within/AND-across access behavior, explicit unrestricted controls, and organization isolation work.
- Unauthorized content never enters retrieval candidates, model context, employee history, or source responses.
- Both lexical and semantic retrieval contribute through fusion and reranking.
- No answer text appears before successful citation and grounding verification.
- Version differences are readable; retries, failed indexing, and rollback preserve publication integrity.
- English, Urdu RTL, Roman Urdu, mobile employee flows, and keyboard navigation work.
- Frontend/backend checks, production builds, dependency auditing, and secret scanning pass.

Document live integrations that remain unverified. Real SOP arrival triggers document reconnaissance, parser and retrieval benchmarks, human review, and agreed quality thresholds before pilot readiness.
