# Verified Markdown ingestion contract

The MVP accepts one human-verified policy per Markdown file. UTF-8 is required. An optional front matter block at the beginning of the file is the authoritative metadata boundary:

```markdown
---
title: Store Leave Policy
policy_number: SOP-76
effective_date: 2026-09-25
---
```

Supported keys are `title`, `policy_number`, `sop_number`, `effective_date`, and `issue_date`. Dates should use ISO `YYYY-MM-DD`. Missing values remain null. Unknown or invalid metadata is not invented.

For compatibility, the first H1 becomes the document title when front matter has no title. Explicit labels such as `SOP #76`, `SOP-76`, and `Policy #93` are retained as policy-number metadata. `Effective Date:` and `Issue Date:` lines are retained as content and parsed when their dates are valid.

ATX headings (`#` through `######`), paragraphs, ordered lists, bullet lists, indentation levels, and GitHub-style pipe tables are converted into provider-neutral canonical structures. A table requires a header row followed by a delimiter row. Header and data cells retain source line anchors. The original Markdown remains private and immutable in object storage; reviewed canonical JSON remains authoritative for publication and retrieval.
