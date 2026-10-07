# Evaluation & Quality

Repeatable benchmark for SOP retrieval and assistant behaviour (Phase 2, section 7).

```bash
# SOP Markdown stays local and is git-ignored (services/evaluation/corpus/*.md)
uv run python -m scripts.evaluation.run_benchmark                 # full matrix + assistant
uv run python -m scripts.evaluation.run_benchmark --validate-only # check the dataset only
uv run python -m scripts.evaluation.run_benchmark --only current-default --no-assistant
uv run python -m scripts.evaluation.run_benchmark --baseline evaluation_runs/<old>/results.json
```

Each run writes `results.json` (machine-readable) and `report.md` (human-readable) under
`evaluation_runs/<timestamp>/`. Exit code `0` = gate passed, `1` = gate failed, `2` = bad
dataset/config/corpus.

**Gate (7.6):** unauthorized retrieval must be 0 for every configuration and k, and no
unauthorized section may reach assistant context. Optional: `--baseline` fails on metric
regressions beyond `--tolerance`; `--max-technical-failure-rate` fails on technical errors.

## What is exercised

The real `FixtureDocumentParser` + `Canonicalizer`, `SectionAwareFixtureChunker`,
`AuthorizationFilter`, `RetrievalService`, `ReciprocalRankFusion`, reranker and `AssistantService`
run unchanged, entirely in memory. Nothing touches MongoDB, R2 or Pinecone (the E5 config only
calls stateless embedding inference, and only when `PINECONE_API_KEY` is set).

## Layout

| File | Purpose |
| --- | --- |
| `models.py` | `EvaluationCase` (7.2 fields), `RetrievalMetrics` |
| `metrics.py` | Recall@K, Precision@K, MRR, nDCG, fact recall, percentiles |
| `retrieval.py` | Per-case scoring, aggregation, unauthorized rate |
| `corpus.py` | Loads SOP Markdown, chunker-independent section keys, access overlay + oracle |
| `dataset.py` | Loads/validates cases against the corpus |
| `providers.py` | Chunker / embedding / reranker factories, metering, skip-on-unavailable |
| `matrix.py`, `datasets/matrix.default.json` | Comparison matrix (7.4) |
| `harness.py` | Runs retrieval and assistant evaluation per configuration |
| `report.py`, `results.py` | Gate, baseline comparison, JSON/Markdown output |
| `datasets/ajg_sop_benchmark.jsonl` | 141 cases, including adversarial ones (7.5) |
| `datasets/access_overlay.json` | Synthetic access labels (see caveat) |

## Dataset rules

Section keys are chunker-independent (`d<doc>:<heading-slug>`, `~2` for repeats), so one dataset
scores any chunker. `validate_dataset` enforces that every expected fact literally appears in an
expected/alternate section, expected sections are readable by the case's scope, forbidden
sections are denied, and forbidden facts never appear in readable text. Nothing is invented.

## Benchmarking other work

Names in the matrix may be `plugin:<module>:<factory>` (a zero-argument callable returning a
`Chunker`, `EmbeddingProvider` or `Reranker`). Example config entry:

```json
{"name": "new-chunker", "chunker": "plugin:services.ingestion.chunking.new:build"}
```

Unavailable components (no `PINECONE_API_KEY`, no `sentence-transformers`, missing module) are
recorded as `skipped` with a reason. No numbers are ever estimated for them.

## Caveats

* The source SOPs carry no access labels; `access_overlay.json` is **synthetic** test data.
  Unauthorized retrieval is checked by an oracle independent of the production filter.
* Fixture embeddings are a hash bag-of-words stand-in, not a semantic model. Their results say
  nothing about E5 or BGE-M3. The fixture LLM/answerability gate echo evidence, so assistant
  metrics here validate the harness; they must be re-run with real providers.
* Retrieval runs once at depth `max(ks)` and is truncated for smaller k.
* Jev has no adapter; use the plugin mechanism once an implementation exists.
