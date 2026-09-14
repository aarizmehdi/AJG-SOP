# ADR 0003: Provider abstractions

**Status:** accepted

Parsers, artifact stores, embeddings, indexes, semantic and lexical candidate retrieval, fusion, reranking, answerability, grounding, and language-model generation use application-owned interfaces. Phase 1 selects DeepSeek through `LLM_PROVIDER=deepseek`. DeepSeek request fields stay inside its adapter so another provider can be added without changing retrieval or assistant services.
