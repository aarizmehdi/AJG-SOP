# Ingestion pipeline

The enforced boundary is:

**original source → provider raw output → normalized raw contract → canonical SOP → human-reviewed canonical SOP → retrieval chunks**

Originals are hashed with SHA-256 and stored privately before parsing. Duplicate file hashes are rejected within an organization. Provider-native output is written as an immutable private artifact; downstream code receives only `RawDocumentResult`. Canonical JSON is authoritative and canonical Markdown is a readable derived artifact.

The source model supports native PDF, scanned PDF, images, DOCX, XLSX, Markdown, and pasted structured text. The fixture parser handles native PDF, DOCX, XLSX, Markdown, and structured text. Scans and images report a truthful provider-required status. The Azure adapter uses `prebuilt-layout` API version `2024-11-30`; its accuracy is unverified. The Docling boundary remains unavailable until the optional provider is installed and benchmarked.

Canonical locators preserve pages, normalized bounding boxes, text spans, sheet/cell coordinates, and block anchors when supplied. The review workspace shows the private original on the left and canonical data on the right. Corrections can change text, headings, levels, section splits, lists, tables, and valid page mappings. Ownership and source-document mappings cannot be changed. Saving a correction clears approval and staged derived data.

Jobs record uploaded, extracting, structuring, review, chunking, embedding, indexing, verification, ready, published, and failed events. Failed parsing can be retried against the preserved original. Failed indexing marks only the candidate version failed; it never changes the active published version.
