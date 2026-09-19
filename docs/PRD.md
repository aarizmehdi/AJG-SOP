# AZIZ JAN TRUST — SOP KNOWLEDGE SYSTEM
### Phase 1 Product Requirements Document & Engineering Build Specification

- **Product:** Aziz Jan Trust SOP Knowledge System
- **Phase:** Phase 1 — SOP Discovery & Grounded Assistant
- **Status:** Foundation implementation can begin immediately
- **Architecture authority:** Team Lead
- **Real SOP status:** Not yet received
- **Primary goal:** Build a production-grade, permission-aware SOP knowledge platform that allows employees to search and understand only the organizational SOP content they are authorized to access.

---

## 1. Product statement

We are not building a general chatbot.

We are building:

> An authoritative SOP retrieval system with a conversational interface.

Employees should be able to:

- Search SOPs using normal questions, keywords, phrases, English, Urdu or Roman Urdu.
- Ask the SOP Assistant questions and receive natural explanations based exclusively on authorized SOP evidence.

The system must never invent company policy.

If the SOP does not contain an answer, the system must say so.

---

## 2. Core product principles

These rules are non-negotiable.

### Authority model

```
SOURCE DOCUMENT
      ↓
VERIFIED CANONICAL SOP
      ↓
RETRIEVAL SYSTEM
      ↓
AUTHORIZED SOP EVIDENCE
      ↓
LLM EXPLANATION
```

The LLM is never the source of organizational truth.

The source document and verified canonical representation are the source of truth.

### Retrieval security

Never:

```
retrieve everything
↓
tell AI not to reveal restricted information
```

Always:

```
authenticate employee
↓
resolve employee permissions
↓
search only permitted SOP scope
↓
send permitted evidence to LLM
```

Unauthorized information must never enter the LLM context.

### Grounding

The assistant may:

- explain
- simplify
- summarize
- translate/explain in selected language
- organize evidence
- clarify policy language

It may not invent:

- procedures
- deadlines
- approval authorities
- requirements
- exceptions
- contacts
- forms
- thresholds
- consequences
- recommendations
- next steps

If SOP evidence does not support:

> "Contact HR."

the assistant must not independently tell the employee to contact HR.

---

## 3. Phase 1 scope

### Phase 1 includes:

- Employee authentication
- Employee SOP permissions
- Language selection
- SOP search
- Grounded SOP assistant
- Policy reader
- Exact citations
- Admin policy library
- Document upload
- Document extraction
- Human extraction review
- Versioning
- Deduplication
- Section-aware chunking
- Pinecone indexing
- Retrieval testing
- Publishing
- Auditability

### Phase 1 does not include:

- Leave request automation
- Expense approvals
- DMN
- Manager approval workflow
- Evidence submission by employees
- Executive overrides
- HR incidents
- Autonomous organizational actions
- Payroll actions

Those can be future phases.

---

## 4. Final technology architecture

Build for future scale from day one.

### Frontend

Use:

- React
- TypeScript
- TSX
- Vite
- React Router
- TanStack Query
- Zod
- React Hook Form where justified

TypeScript must be strict.

No JSX-only application.

No direct DOM-oriented architecture.

No giant frontend framework.

### Backend

Use:

- Python 3.12+
- FastAPI
- Pydantic v2
- async architecture

### Canonical application database

Use:

- MongoDB Atlas

MongoDB Atlas stores authoritative application data.

Pinecone is not the canonical database.

### Retrieval

Use:

- Pinecone

Pinecone stores derived retrieval/index records.

Every Pinecone record must be reproducible from canonical MongoDB data.

### Original file storage

Use:

- Private S3-compatible object storage

Initial production target:

- AWS S3

Architecture must remain provider-neutral enough to support compatible object storage later.

Store original files and extraction artifacts there.

### Redis

Use managed Redis only where appropriate for:

- rate limiting
- caching
- distributed locks
- ingestion coordination
- short-lived job state

Do not store canonical SOP truth in Redis.

### Authentication

Use:

- Auth0

Architecture must allow future enterprise SSO through:

- Microsoft Entra ID
- OIDC
- SAML

Authentication determines identity.

Backend authorization determines SOP access.

---

## 5. High-level architecture

```
                       EMPLOYEE
                          │
                          ▼
                ┌───────────────────┐
                │ React / TypeScript│
                │     Frontend      │
                └─────────┬─────────┘
                          │
                          ▼
                ┌───────────────────┐
                │      FastAPI      │
                │ Backend / Gateway │
                └─────────┬─────────┘
                          │
           ┌──────────────┼──────────────┐
           │              │              │
           ▼              ▼              ▼
        Auth0        MongoDB Atlas      S3
      Identity        Canonical DB    Documents
           │              │
           └──────┬───────┘
                  │
           Authorization Scope
                  │
                  ▼
            Query Understanding
                  │
                  ▼
        ┌──────────────────────┐
        │       Pinecone       │
        │ Search / Retrieval   │
        └──────────┬───────────┘
                   │
                Rerank
                   │
            Answerability
                   │
                   ▼
             Grounded LLM
                   │
             Verification
                   │
                   ▼
           Answer + Citation
```

---

## 6. Repository

Create a completely new repository.

```
aziz-jan-sop-knowledge/
```

Do not modify SOP Forge.

SOP Forge remains a reference implementation for future advanced phases.

---

## 7. Repository architecture

```
aziz-jan-sop-knowledge/
│
├── apps/
│   │
│   ├── web/
│   │   ├── public/
│   │   │   └── brand/
│   │   │
│   │   └── src/
│   │       ├── app/
│   │       │   ├── App.tsx
│   │       │   ├── router.tsx
│   │       │   └── providers.tsx
│   │       │
│   │       ├── routes/
│   │       │
│   │       ├── features/
│   │       │   ├── auth/
│   │       │   ├── language/
│   │       │   ├── home/
│   │       │   ├── search/
│   │       │   ├── assistant/
│   │       │   ├── policies/
│   │       │   └── admin/
│   │       │
│   │       ├── components/
│   │       │   ├── ui/
│   │       │   ├── layout/
│   │       │   └── feedback/
│   │       │
│   │       ├── api/
│   │       ├── hooks/
│   │       ├── lib/
│   │       ├── types/
│   │       └── styles/
│   │
│   └── api/
│       └── app/
│           ├── main.py
│           ├── config.py
│           ├── database.py
│           │
│           ├── api/
│           │   ├── auth.py
│           │   ├── profile.py
│           │   ├── search.py
│           │   ├── assistant.py
│           │   ├── policies.py
│           │   └── admin.py
│           │
│           ├── auth/
│           │   ├── identity.py
│           │   ├── dependencies.py
│           │   └── permissions.py
│           │
│           ├── models/
│           ├── schemas/
│           ├── repositories/
│           │
│           └── services/
│               ├── policy_service.py
│               ├── permission_service.py
│               ├── search_service.py
│               ├── assistant_service.py
│               └── audit_service.py
│
├── services/
│   │
│   ├── ingestion/
│   │   ├── extractors/
│   │   │   ├── base.py
│   │   │   ├── azure_document_intelligence.py
│   │   │   ├── docling.py
│   │   │   └── fixtures.py
│   │   │
│   │   ├── structure/
│   │   │   ├── canonical_document.py
│   │   │   ├── sections.py
│   │   │   ├── tables.py
│   │   │   └── validation.py
│   │   │
│   │   ├── chunking/
│   │   │   ├── semantic_chunker.py
│   │   │   ├── metadata.py
│   │   │   └── validation.py
│   │   │
│   │   ├── embeddings/
│   │   │   ├── base.py
│   │   │   └── provider.py
│   │   │
│   │   ├── indexing/
│   │   │   └── pinecone_index.py
│   │   │
│   │   └── pipeline.py
│   │
│   ├── retrieval/
│   │   ├── query_understanding.py
│   │   ├── authorization_filter.py
│   │   ├── lexical_search.py
│   │   ├── semantic_search.py
│   │   ├── hybrid_search.py
│   │   ├── reranker.py
│   │   └── retriever.py
│   │
│   ├── assistant/
│   │   ├── answerability.py
│   │   ├── answer_generator.py
│   │   ├── grounding.py
│   │   ├── verifier.py
│   │   └── citations.py
│   │
│   └── evaluation/
│       ├── datasets/
│       ├── retrieval.py
│       ├── grounding.py
│       ├── authorization.py
│       └── report.py
│
├── packages/
│   ├── contracts/
│   └── shared/
│
├── scripts/
│   ├── evaluation/
│   ├── maintenance/
│   └── seed/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── retrieval/
│   ├── security/
│   └── e2e/
│
├── docs/
│   ├── PRD.md
│   ├── architecture/
│   ├── research/
│   ├── decisions/
│   ├── design/
│   └── runbooks/
│
├── infra/
├── .github/
├── README.md
├── .env.example
└── docker-compose.yml
```

Do not create meaningless empty folders solely to match this diagram.

---

## 8. User roles

Phase 1 roles:

- employee
- sop_admin
- system_admin

### Employee

Can:

- log in
- choose language
- search authorized SOP content
- ask assistant
- open authorized source sections

### SOP Admin

Can additionally:

- manage policy library
- upload sources
- review extraction
- correct extraction structure
- configure access scope
- create new versions
- compare versions
- test retrieval
- publish
- deactivate
- rollback where supported
- reprocess documents

### System Admin

Can additionally manage:

- accounts
- role assignments
- organizational scopes
- infrastructure-level product configuration

Backend authorization is authoritative.

React route guards are only UX.

---

## 9. Authentication UX

Production login should use Auth0.

Do not store long-lived sensitive tokens in insecure browser storage when avoidable.

Use secure supported Auth0 patterns.

Eventually the system should support organization SSO without redesigning application authorization.

---

## 10. Language UX

After first login, if no language preference exists:

> Choose your language

- English
- اردو
- Roman Urdu

Save the choice.

Assistant output remains locked to that language.

Employee input may still contain supported mixed-language content.

Do not randomly change assistant language based on message language.

---

## 11. Employee experience

Primary routes:

```
/login
/language
/home
/search
/assistant
/policies/:policyId
```

Keep employee navigation minimal.

Home should prominently ask:

> What would you like to know?

Show:

- Search SOPs
- Ask SOP Assistant

Do not expose internal retrieval concepts to employees.

---

## 12. Search UX

Employee can search:

- exact terms
- policy numbers
- questions
- sentences
- English
- Urdu
- Roman Urdu

Search result should resemble:

> **Damaged Stock Handling**
>
> Store Operations SOP
> Inventory Management → Receiving Goods → Damaged Stock
> Page 17
>
> Relevant excerpt...
>
> [View Policy]

Show citations.

Do not show:

- vector scores
- embeddings
- chunk IDs
- reranking internals

---

## 13. Assistant UX

Assistant should feel like a knowledgeable internal SOP officer.

Natural, respectful and clear.

Answer should contain:

- **Answer**
- **Source**
  - SOP name
  - Chapter / section
  - Page
- [View Policy]

If multiple sources support an answer, show them separately.

Do not put every assistant answer inside a giant card.

Use a calm readable conversational layout.

---

## 14. Grounding architecture

Pipeline:

```
Question
   ↓
Identity
   ↓
Authorization scope
   ↓
Query normalization
   ↓
Hybrid retrieval
   ↓
Reranking
   ↓
Answerability gate
   ↓
Grounded generation
   ↓
Citation validation
   ↓
Grounding verification
   ↓
Return answer
```

If answerability fails:

Return controlled response:

> I couldn't find guidance for that in the SOPs available to you.

Translate/localize according to chosen language.

Do not ask the LLM to invent a helpful alternative.

---

## 15. Structured assistant response

Backend assistant service should work with a validated structure similar to:

```json
{
  "answerable": true,
  "answer": "…",
  "citations": [
    {
      "chunk_id": "…",
      "section_id": "4.3",
      "document_id": "…",
      "page_start": 17,
      "page_end": 17
    }
  ]
}
```

Every citation returned by the model must exist in the retrieved evidence set.

Reject invented citation IDs.

---

## 16. Search and assistant must share retrieval

Do not build two retrieval engines.

```
Search ────────┐
               ├── Retrieval Service
Assistant ─────┘
```

Search returns evidence directly.

Assistant explains the same evidence.

---

## 17. MongoDB Atlas model

Design collections around:

```
organizations
users
employee_profiles
stores
departments
organizational_roles
access_rules

sop_policies
sop_versions
source_documents
canonical_sections
retrieval_chunks

ingestion_jobs

chat_sessions
chat_messages

search_events
answer_feedback
audit_events
```

All organization-owned records must carry `organization_id`.

---

## 18. Policy/version model

Do not overwrite published policies.

Model:

```
SOPPolicy
 ├── Version 1
 ├── Version 2
 └── Version 3 [ACTIVE]
```

A version may contain multiple source documents:

> **Store Operations — Version 4**
>
> Sources:
> - Store Manual.pdf
> - Approval Limits.xlsx
> - Damaged Goods Annex.docx

Only approved/published versions become available to employees.

---

## 19. Supported upload formats

Admin system should be designed for:

- PDF
- DOCX
- XLSX
- image/scanned document
- Markdown
- structured pasted text

Not every format needs full production parsing before real SOP receipt.

Architecture must permit each format cleanly.

---

## 20. Admin Add SOP UX

Admin clicks:

> + Add SOP

Then selects:

- Upload PDF
- Upload Word
- Upload Excel
- Upload Scan/Image
- Import Markdown
- Paste Structured Text

Then collects:

- Policy title
- Category
- Applicable department
- Applicable store/location
- Applicable roles
- Effective date
- Version

AI may suggest metadata.

Human admin confirms authoritative scope.

---

## 21. Document extraction architecture

Do not build:

```
PDF
↓
plain Python extraction
↓
immediately Pinecone
```

Build:

```
SOURCE FILE
    ↓
PARSER / DOCUMENT INTELLIGENCE
    ↓
RAW EXTRACTION
    ↓
CANONICALIZATION
    ↓
HUMAN REVIEW
    ↓
APPROVAL
    ↓
CHUNKING
    ↓
INDEXING
```

---

## 22. Parser abstraction

Create a provider interface.

Concept:

```python
class DocumentParser:
    async def parse(self, source) -> RawDocumentResult: ...
```

Providers must remain swappable.

Initial candidates to support/benchmark:

- Azure AI Document Intelligence
- Docling

Other providers may be tested later.

Do not permanently bind the whole application to provider-specific response JSON.

---

## 23. Real-document parser decision

The real SOP has not arrived.

Therefore:

Do not declare one extraction engine final yet.

Build adapter interfaces and test fixtures now.

After receiving the actual SOP:

Benchmark serious candidates on the same difficult pages.

Final decision must be evidence-based.

---

## 24. Canonical SOP representation

This is the trusted intermediate format.

Example:

```json
{
  "document_id": "...",
  "title": "Store Operations SOP",
  "version": 4,
  "sections": [
    {
      "section_id": "4.3",
      "chapter": "Inventory Management",
      "title": "Damaged Stock",
      "page_start": 17,
      "page_end": 18,
      "content": "...",
      "tables": [],
      "applicable_scope": {
        "departments": ["store"],
        "roles": ["store_keeper"]
      }
    }
  ]
}
```

Preserve:

- heading hierarchy
- chapters
- sections
- subsections
- policy numbers
- paragraphs
- bullet relationships
- tables
- pages
- source mapping
- organizational scope

---

## 25. Canonical Markdown

Generate a readable Markdown representation too.

Example:

```markdown
# Store Operations SOP

## 4. Inventory Management

### 4.3 Damaged Stock

**Applicable role:** Store Keeper
**Source page:** 17

When damaged stock is received...

1. ...
2. ...
3. ...
```

Markdown is useful for:

- human review
- debugging
- documentation
- secondary processing

But structured JSON remains the stronger canonical machine representation.

---

## 26. Keep extraction stages

For each ingestion job preserve references to:

- original source
- raw provider extraction
- canonical machine output
- human-reviewed canonical output

This allows future:

- reprocessing
- parser replacement
- debugging
- auditability
- comparison

---

## 27. Human extraction review

No OCR/parser output is automatically trusted.

Admin must have a review screen.

Desktop experience should support:

```
┌────────────────────────┬────────────────────────┐
│ ORIGINAL DOCUMENT      │ EXTRACTED STRUCTURE    │
│                        │                        │
│ Page 17 preview        │ 4.3 Damaged Stock     │
│                        │                        │
│                        │ extracted body...      │
└────────────────────────┴────────────────────────┘
```

Admin can correct extraction problems such as:

- OCR typo
- heading level
- wrong section split
- incorrect page association
- table structure
- repeated header/footer noise

This review modifies the canonical representation.

It does not modify the original source.

---

## 28. Ingestion lifecycle

Implement explicit states:

```
UPLOADED
EXTRACTING
STRUCTURING
REVIEW_REQUIRED
STRUCTURE_APPROVED
CHUNKING
EMBEDDING
INDEXING
VERIFYING
READY_FOR_REVIEW
PUBLISHED
FAILED
```

Do not mark documents published automatically after upload.

---

## 29. Admin ingestion UX

Show understandable stages:

- File uploaded
- Reading document
- Detecting structure
- Building sections
- Waiting for your review
- Preparing search index
- Verifying retrieval
- Ready to publish

Do not show fake numeric progress.

Use real step progress.

---

## 30. Chunking

Do not use arbitrary character-only splitting as primary architecture.

Prefer:

```
Chapter
↓
Section
↓
Subsection
↓
Semantic retrieval unit
```

A small coherent policy should remain intact.

Large sections can be split while preserving parent context.

Each chunk should contain metadata including:

```
organization_id
policy_id
version_id
source_document_id

chapter
section
subsection
policy_number

page_start
page_end

departments
roles
stores
visibility

chunk_index
parent_section_id
publication_status
```

---

## 31. Pinecone

Pinecone is a derived search index.

Canonical chunk content remains in MongoDB.

Use versioned index configuration.

Create provider/repository boundary so future retrieval infrastructure can be changed.

Namespace initially:

```
aziz-jan-trust
```

Later namespace strategy may support additional organizations.

---

## 32. Retrieval

Build for hybrid retrieval.

Architecture should support:

- semantic/vector search
- lexical/exact-term search
- metadata filtering
- candidate fusion
- reranking

Exact policy numbers and organizational terms must remain retrievable.

---

## 33. Authorization before retrieval

Hard rule.

```
employee
↓
profile
↓
department/store/role
↓
access rules
↓
retrieval metadata filter
↓
Pinecone
```

Do not retrieve restricted records and remove them afterward.

---

## 34. Embedding provider

Create:

```
EmbeddingProvider
```

Do not hard-code the platform to a single embedding vendor.

Final model is not frozen until real SOP evaluation.

Must support multilingual/cross-lingual retrieval.

Benchmark serious current multilingual models against:

- English questions
- Urdu questions
- Roman Urdu questions

from the real SOP.

---

## 35. Reranking

Design:

```
Reranker
```

as its own abstraction.

Do not assume nearest-vector ordering is good enough.

Final reranker choice will be benchmarked once real evaluation data exists.

---

## 36. No duplicate documents

Exact file duplicate:

Calculate:

- SHA-256

If identical source already exists, warn/block accidental duplicate upload.

---

## 37. Section duplicate detection

Normalized canonical sections should support content hashes.

Identical repeated sections can be detected.

Do not automatically delete semantically similar policy text.

Semantic similarity can only suggest:

> Possible duplicate

Human confirms.

---

## 38. Policy updates

Admin does not overwrite active policy directly.

Use:

> Create New Version

Options:

- Replace current primary document
- Add supporting document
- Update selected sections

Every published policy version remains available for audit/history.

---

## 39. Version comparison

Before publishing a new version, provide a human-readable diff:

```diff
CHANGED
Section 4.3

- OLD: Report within 24 hours.
+ NEW: Report within 12 hours.

ADDED
Section 4.7 — Returned Goods

REMOVED
Section 3.2 — Manual Stock Adjustment
```

Admin confirms before publication.

---

## 40. Index consistency

Publishing a new version must not create a partially visible knowledge base.

Use publication/index strategy that ensures:

- old published version remains usable

while

- new version is processing

Only switch active/public visibility after indexing and verification succeed.

Failed indexing must never remove the valid previous version.

---

## 41. Retrieval test before publish

Admin should be able to test:

> "What should I do with damaged stock?"

before publishing.

Display ranked sections.

Admin can mark:

- Correct result
- Incorrect result

This becomes useful evaluation feedback.

---

## 42. Policy Library

Admin library displays:

- Policy title
- Active version
- Category
- Audience/scope
- Status
- Updated date
- Source files

Opening policy should support:

- Overview
- Source Documents
- Canonical Policy
- Sections
- Search Preview
- Version History
- Access

Advanced technical views may show chunks/index status.

Do not make vectors primary admin UX.

---

## 43. UI / UX visual direction

Aziz Jan Trust cares strongly about visual quality.

Design accordingly.

Brand:

- Blue
- Blue-black
- White / off-white

Do not use pure white everywhere.

Use a soft cool neutral canvas.

Direction:

- soft blue-white canvas
- white elevated surfaces
- midnight navy hierarchy
- trust blue interaction
- cool gray borders
- slate secondary typography

Approximate visual balance:

- 70% neutral/light
- 20% navy/ink
- 10% brand blue

Final exact blue is derived from actual Aziz Jan Trust logo.

---

## 44. Logo

The real Aziz Jan Trust logo will be provided.

Create:

```
apps/web/public/brand/
```

and a reusable brand component.

Do not create a replacement company logo.

Do not permanently recolor it without approval.

---

## 45. Design psychology

UI should communicate:

- Trust
- Clarity
- Competence
- Authority
- Calmness
- Ease

Not:

- AI gimmick
- futurism
- complexity
- technical infrastructure

Employees should feel:

> "I can easily find the rule I need."

---

## 46. Jakob's Law

Use familiar patterns.

- Search behaves like excellent search.
- Chat behaves like excellent chat.
- Policy viewer behaves like a document reader.
- Admin upload behaves like a polished document-management system.

Do not make common interactions unusual just for originality.

---

## 47. Typography

Use a highly readable modern variable sans for English/Roman Urdu.

Recommended direction:

- Inter Variable
- or comparable production-safe modern UI font

Urdu needs proper Urdu/Arabic-script typography and RTL support.

Do not force Latin typography assumptions on Urdu.

Typography tokens must be centralized.

No random font sizes throughout TSX.

---

## 48. Frontend component system

Build internal reusable primitives approximately around:

```
Button
IconButton
Input
SearchInput
Select
Combobox
Tabs
Badge
Dialog
Drawer
Tooltip
Toast
Skeleton
EmptyState
ErrorState
Surface
Avatar
ProgressSteps
DocumentViewer
SourceCitation
LanguageSelector
```

Do not over-generalize everything.

---

## 49. Loading

Use real skeletons for:

- app bootstrap
- profile
- home
- search
- assistant session
- policy reader
- admin library
- ingestion details
- version history

Skeleton shapes should resemble resulting content.

---

## 50. Realtime behavior

Use Server-Sent Events where useful for:

- streamed assistant responses
- ingestion progress

Do not automatically use WebSockets.

Use them only if a true future bidirectional realtime need appears.

---

## 51. Responsive design

Must be intentionally designed for:

- desktop
- laptop
- tablet
- mobile

Do not merely shrink desktop UI.

Employee search/chat should be excellent on mobile.

Admin review is primarily desktop-oriented but must remain usable on tablet.

---

## 52. Accessibility

Required:

- keyboard navigation
- focus indicators
- semantic HTML
- accessible dialogs
- touch target sizing
- contrast
- reduced motion
- screen-reader labels
- RTL support

Accessibility is a production requirement.

---

## 53. Performance

Use:

- route-level lazy loading
- TanStack Query caching
- abortable searches
- search debounce where appropriate
- bundle discipline
- streaming
- image optimization

Do not add unnecessary heavyweight dependencies.

---

## 54. Dependency quality

Before installing dependencies:

Use current stable supported versions.

Avoid:

- deprecated packages
- deprecated APIs
- abandoned libraries

Commit lockfiles.

No broad use of:

- `any`
- `@ts-ignore`
- `eslint-disable`

to hide architectural problems.

---

## 55. Configuration

Create an accurate `.env.example`.

Include placeholders for:

```
MONGODB_URI
MONGODB_DATABASE

PINECONE_API_KEY
PINECONE_INDEX

AWS/S3 configuration

REDIS_URL

AUTH0 configuration

LLM provider
Embedding provider
Reranker provider
Document intelligence provider
```

Never commit secrets.

Production should fail fast when required configuration is absent.

---

## 56. Observability

Use structured logs.

Track appropriate metrics:

- request latency
- search latency
- retrieval latency
- LLM latency
- ingestion duration
- parsing failures
- retrieval failures
- answerability failures
- grounding failures

Do not expose sensitive internal logs to users.

---

## 57. Retrieval telemetry

Admin/debug environment should make it possible to inspect:

- query
- employee scope
- retrieved candidates
- retrieval scores
- reranked order
- selected context
- provider/model versions
- latencies

Employees never see raw similarity scores.

---

## 58. Evaluation system

Formal evaluation dataset should support:

```json
{
  "question": "...",
  "language": "roman_urdu",
  "employee_scope": {
    "department": "store",
    "role": "store_keeper"
  },
  "expected_sections": ["4.3"],
  "forbidden_sections": ["7.2"],
  "answerable": true
}
```

Evaluate:

- Recall@K
- Precision@K
- MRR
- nDCG where useful
- answerability accuracy
- citation correctness
- groundedness
- unauthorized retrieval rate

Absolute security requirement:

> unauthorized retrieval rate = 0

---

## 59. What to build NOW before the real PDF

Begin implementation immediately.

Build now:

- repository
- CI/CD
- frontend architecture
- design system
- login shell
- language flow
- home/search/chat UI
- policy reader shell
- FastAPI foundation
- Auth0 integration boundary
- MongoDB Atlas integration
- data models
- permissions architecture
- S3 storage abstraction
- document upload
- policy/version/source models
- ingestion job state machine
- parser abstraction
- canonical SOP schema
- canonical Markdown generation
- review UI
- chunking interfaces
- embedding interface
- Pinecone interface
- retrieval interface
- reranker interface
- answerability
- grounding contracts
- citation validation
- admin policy library
- version workflow
- duplicate detection framework
- evaluation harness
- tests
- documentation

---

## 60. What NOT to finalize before receiving the real SOP

Do not freeze:

- final OCR engine
- final parser provider
- final heading detector
- final table reconstruction strategy
- final chunk size
- final chunk overlap
- final embedding model
- final reranking provider
- final retrieval weights
- final answerability thresholds

These must be calibrated against the actual document.

---

## 61. When the real SOP arrives

Do a document reconnaissance first.

Record:

- file format
- page count
- native text vs scanned pages
- scan quality
- columns
- tables
- images
- headers/footers
- TOC
- numbering format
- heading hierarchy
- languages
- forms
- repeated templates
- handwriting
- role/department labels

Do not ingest straight to production.

---

## 62. Parser benchmark after SOP arrival

Take representative pages:

- easy text page
- heading-heavy page
- table-heavy page
- poor scan
- multi-column page
- page with image
- nested-list page

Run them through candidate extraction pipelines.

Compare:

- text fidelity
- reading order
- headings
- tables
- lists
- page mapping
- OCR accuracy
- structure
- latency
- cost

Team must recommend a winner.

Team Lead approves.

---

## 63. Embedding/retrieval benchmark after SOP arrival

Create approximately 50–100 representative questions where practical.

Include:

- English
- Urdu
- Roman Urdu
- exact policy terms
- natural employee questions
- ambiguous questions
- no-answer questions
- restricted questions

Then benchmark embedding/retrieval configurations.

Team Lead approves final configuration.

---

## 64. Team ownership

All work occurs through branches and PRs.

No direct push to main.

### Team Member 1 — Document Extraction

Owns:

```
services/ingestion/extractors/
```

Task:

Build parser abstraction and benchmark harness.

Compare serious document extraction/OCR approaches.

Deliver evidence, code and recommendation.

### Team Member 2 — Canonical Structure + Chunking

Owns:

```
services/ingestion/structure/
services/ingestion/chunking/
```

Task:

Build canonical SOP representation and section-aware chunking framework.

Ensure document hierarchy survives processing.

### Team Member 3 — Versioning + Ingestion Integrity

Owns:

- policy versioning
- source document model
- deduplication
- hashing
- publication consistency
- diffing
- rollback/reindex logic

Must prove updates do not duplicate/corrupt existing policy.

### Team Member 4 — Retrieval + Evaluation

Owns:

```
services/retrieval/
services/evaluation/
```

Task:

Build retrieval abstraction, Pinecone integration, authorization filters, evaluation harness and benchmarking tools.

Must prove retrieval quality, not merely connectivity.

---

## 65. Team Lead ownership

Team Lead owns:

```
apps/web/
```

- product UX
- design system
- architecture approval
- PR review
- research review
- final provider decisions
- integration approval
- acceptance testing

Research recommendations are not final architecture until approved.

---

## 66. PR requirements

Every research/engineering PR must explain:

- What problem was addressed?
- What options were tested?
- What was implemented?
- How was it tested?
- What worked?
- What failed?
- What tradeoffs exist?
- What is recommended?
- What remains unknown before the real SOP?
- How does this component connect to the next stage?

Do not accept:

> "Integrated Pinecone successfully."

as proof of retrieval quality.

Do not accept:

> "OCR works."

without document-quality evidence.

---

## 67. CI/CD

Required frontend checks:

- TypeScript typecheck
- lint
- format
- unit tests
- production build

Required backend checks:

- lint
- format
- tests
- type/static checks where configured

Also:

- dependency auditing
- secret scanning

Required checks must pass before merge.

---

## 68. Documentation

Create and maintain:

```
docs/PRD.md

docs/architecture/SYSTEM_ARCHITECTURE.md
docs/architecture/INGESTION_PIPELINE.md
docs/architecture/RETRIEVAL_PIPELINE.md
docs/architecture/AUTHORIZATION_MODEL.md

docs/design/DESIGN_SYSTEM.md
docs/design/USER_FLOWS.md

docs/research/

docs/decisions/
```

Use ADRs for important architecture decisions.

Do not create miscellaneous report files everywhere.

---

## 69. Initial acceptance criteria before the real SOP arrives

The foundation is acceptable when:

- React/TSX app builds cleanly
- responsive design system exists
- login/auth integration exists
- language-selection flow exists
- employee search/chat UI exists
- admin policy library exists
- MongoDB integration exists
- S3 upload works
- policy/version/source model works
- duplicate file detection works
- ingestion state machine works
- parser abstraction works
- test fixtures can be ingested
- canonical structure can be reviewed
- Pinecone adapter works using test data
- authorization filtering exists
- search and assistant share retrieval
- assistant cannot answer with zero supplied evidence
- citation IDs are validated
- evaluation harness exists
- CI passes
- no real secrets are committed

Do not claim actual SOP accuracy yet.

---

## 70. Final acceptance criteria after receiving the SOP

Phase 1 becomes pilot-ready only when:

- real SOP extraction is verified
- human review completed
- structure preserved
- correct access scopes assigned
- retrieval benchmark reaches agreed quality
- English retrieval works
- Urdu retrieval works
- Roman Urdu retrieval works
- citations are correct
- no-answer behavior works
- unauthorized retrieval is zero
- policy reader points to correct sources
- admin update/version flow works
- production deployment is stable

---

## 71. UX completion standard

Every major view needs deliberate:

- loading
- skeleton
- empty
- success
- error
- unauthorized

states.

- No raw backend exception dumps.
- No fake progress.
- No unexplained technical terminology.
- No accidental language switching.
- No giant dark developer-dashboard styling.
- No random UI patterns.

---

## 72. Final engineering rule

The entire implementation must preserve this distinction:

| Layer | Role |
|---|---|
| Original document | legal/organizational source |
| Verified canonical SOP | application truth |
| MongoDB Atlas | canonical application persistence |
| Pinecone | derived retrieval index |
| LLM | constrained explanation layer |

- If Pinecone disappeared completely, the index must be rebuildable.
- If the LLM disappeared completely, the system must still be able to search and display SOP sections.
- If a parser changes, the original source must remain available for reprocessing.
- If a policy changes, history must remain preserved through versioning.

---

## 73. Final product standard

Do not optimize for making a demo look finished quickly.

Build a foundation designed to scale into future phases.

The product should feel simple to the organization even though the architecture behind it is sophisticated.

Employees should experience:

```
Login
→ choose language
→ ask/search
→ get exact SOP answer
→ inspect source
```

Administrators should experience:

```
Add SOP
→ process
→ review
→ approve structure
→ test search
→ publish
```

The complexity stays behind the interface.
