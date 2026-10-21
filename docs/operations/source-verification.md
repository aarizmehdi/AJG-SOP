# Source verification and structured-document preservation

Original source documents remain authoritative. A successful parse or token-bounded chunk preview
does not establish transcription accuracy, translation accuracy or policy precedence.

## Canonical structure

- Markdown headings retain their source levels through canonical export/re-import. Heading-only
  policy/subsection parents remain navigable; the collection title need not be a content section.
- Child sections inherit the nearest identifiable policy number when they do not have their own.
  Different source occurrences with identical heading paths receive distinct, repeatable occurrence
  keys. These keys are not evidence that documents with the same number supersede one another.
- Decimal, alphabetic and Roman list markers are retained, including gaps in numbering. The shared
  document reader displays source markers rather than replacing them with browser numbering.
- Nested list conditions are present in both structured blocks and plain canonical-reader text.
- Blank table cells stay blank. The parser does not invent zeros, recalculate totals or fill stock
  entry fields. HTML comments and horizontal separators do not become policy paragraphs. Comment
  removal preserves original line numbers for source anchors.
- Section page ranges include nested list/cell locators. A Markdown line number is not an original
  PDF page number. Original-page citations require separately verified source mapping.

## Handwriting and annotations

A readable, explicitly approved replacement may be incorporated into its affected policy clause,
with the original scan and amendment provenance preserved. Questions, margin notes and annotations
must remain distinguishable from policy requirements. Do not infer an allocation change, mixing
permission, effective year or precedence from a note that does not establish it.

`CanonicalSection.content_role` defaults to `policy` for backward compatibility. Reviewed
non-normative sections use `source_annotation`. The Markdown parser recognizes an explicitly
labeled `Handwritten source annotation...` heading and its descendants. These sections remain
available in authorized canonical reading, but the chunker excludes them from policy-rule retrieval.
An annotation's child headings must not accidentally contain the subsequent printed policy body.
Extraction review must check the boundary explicitly. Changing a section's content role changes its
content hash so version comparison can identify the change.

This is content classification, never an authorization mechanism. Organization, membership, section
scope and current-version checks remain authoritative for reading, retrieval and assistant release.

## Local verification

Use synthetic fixtures in Git and public test logs. Keep confidential originals, converted text,
full canonical artifacts, review ledgers and source maps in ignored private storage.

Run the actual parser, canonicalizer and pinned E5 tokenizer against each private candidate. Check:

1. Every expected policy occurrence and parent/child relationship.
2. Exact paragraph/list-item content, markers, table cells and blank cells from raw to canonical.
3. Complete source-page and clause mappings, with no guessed original pages.
4. Token limits on every final embedding input and content coverage across the chunk preview.
5. Exclusion of non-normative annotations from rule evidence, without deleting reader content.
6. Unresolved translations, diagram coverage, conflicts and amendments against the original scan.

Counts and ordered-token checks are diagnostics, not proof of semantic accuracy or source approval.
Publication remains blocked for unresolved material source discrepancies. Preserve existing published
versions and originals until a corrected version passes source review and indexing verification;
use the existing versioned publication/rollback workflow, never destructive replacement.

## Focused regression checks

```powershell
uv run pytest tests/unit/test_source_structure_preservation.py tests/unit/test_canonical_pipeline.py tests/test_chunking.py tests/integration/test_publication_chunking.py
npm run test --workspace @ajt/web -- src/components/documents/CanonicalDocumentRenderer.test.tsx
```

These tests use synthetic documents and do not read or modify production SOP data.
