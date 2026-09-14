# Real SOP benchmark plan

When the real SOP arrives, first record format, pages, native/scanned regions, scan quality, columns, tables, images, headers, footers, contents pages, numbering, hierarchy, languages, forms, repeated templates, handwriting, and access labels.

Benchmark representative easy-text, heading-heavy, table-heavy, poor-scan, multi-column, image, and nested-list pages across candidate parsers. Measure text fidelity, reading order, headings, tables, lists, coordinates, OCR accuracy, latency, and cost. A human reviewer chooses the parser only after inspecting canonical output.

Build 50–100 English, Urdu, Roman Urdu, exact-term, natural, ambiguous, no-answer, and restricted questions. Compare chunk size/overlap, embedding models, lexical/semantic fusion weights, rerankers, and answerability thresholds using Recall@K, Precision@K, MRR, nDCG, answerability accuracy, citation correctness, groundedness, latency, and an unauthorized retrieval rate fixed at zero.

Until this benchmark and human validation finish, no parser winner, extraction accuracy, chunk sizing, embedding model, reranker, fusion weight, or answerability threshold is final, and the system is not pilot-ready.
