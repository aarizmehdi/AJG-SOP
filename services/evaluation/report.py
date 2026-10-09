"""Regression gate, baseline comparison and Markdown rendering for benchmark results."""

from collections.abc import Sequence
from pathlib import Path

from services.evaluation.results import (
    BenchmarkResult,
    ConfigResult,
    ConfigStatus,
    GateOutcome,
)

REGRESSION_FIELDS = ("recall_at_k", "mean_reciprocal_rank", "ndcg_at_k")
ASSISTANT_REGRESSION_FIELDS = (
    "answerability_accuracy",
    "clarification_accuracy",
    "kind_accuracy",
    "citation_correctness",
    "grounding_correctness",
)


def evaluate_gate(
    result: BenchmarkResult,
    baseline: BenchmarkResult | None = None,
    *,
    tolerance: float = 0.0,
    max_technical_failure_rate: float | None = None,
) -> GateOutcome:
    """Hard gate: unauthorized retrieval must be zero everywhere.

    Optional: fail on quality regressions against an earlier result for the same configuration
    names, and on technical failures above a threshold.
    """
    failures: list[str] = []
    unauthorized = 0
    runnable = [config for config in result.configs if config.status is ConfigStatus.OK]
    if not runnable:
        failures.append("No configuration produced results")
    for config in result.configs:
        if config.status is ConfigStatus.FAILED:
            failures.append(f"{config.name}: configuration failed to run ({config.reason})")
        if config.status is not ConfigStatus.OK:
            continue
        for k, metrics in config.retrieval_by_k.items():
            unauthorized += metrics.unauthorized_retrieval_count
            if metrics.unauthorized_retrieval_count:
                failures.append(
                    f"{config.name}: {metrics.unauthorized_retrieval_count} unauthorized "
                    f"chunk(s) retrieved at k={k} (must be 0)"
                )
        if config.assistant and config.assistant.unauthorized_context_count:
            unauthorized += config.assistant.unauthorized_context_count
            failures.append(
                f"{config.name}: assistant context contained "
                f"{config.assistant.unauthorized_context_count} unauthorized section(s)"
            )
        if max_technical_failure_rate is not None:
            rates = [config.retrieval_technical_failure_rate]
            if config.assistant:
                rates.append(config.assistant.technical_failure_rate)
            if max(rates) > max_technical_failure_rate:
                failures.append(
                    f"{config.name}: technical failure rate {max(rates):.3f} exceeds "
                    f"{max_technical_failure_rate:.3f}"
                )
    if baseline is not None:
        failures.extend(compare_to_baseline(result, baseline, tolerance))
    return GateOutcome(
        passed=not failures, failures=failures, unauthorized_retrieval_count=unauthorized
    )


def compare_to_baseline(
    result: BenchmarkResult, baseline: BenchmarkResult, tolerance: float
) -> list[str]:
    regressions: list[str] = []
    if baseline.dataset_sha256 != result.dataset_sha256:
        regressions.append(
            "Baseline was produced from a different dataset; regression comparison skipped"
        )
        return regressions
    old_by_name = {config.name: config for config in baseline.configs}
    key = str(result.primary_k)
    for config in result.configs:
        old = old_by_name.get(config.name)
        if config.status is not ConfigStatus.OK or old is None or old.status is not ConfigStatus.OK:
            continue
        new_metrics = config.retrieval_by_k.get(key)
        old_metrics = old.retrieval_by_k.get(key)
        if new_metrics and old_metrics:
            for name in REGRESSION_FIELDS:
                before = float(getattr(old_metrics, name))
                after = float(getattr(new_metrics, name))
                if after < before - tolerance:
                    regressions.append(
                        f"{config.name}: {name}@{key} regressed {before:.3f} -> {after:.3f}"
                    )
        if config.assistant and old.assistant:
            for name in ASSISTANT_REGRESSION_FIELDS:
                before_value = getattr(old.assistant, name)
                after_value = getattr(config.assistant, name)
                if (
                    before_value is not None
                    and after_value is not None
                    and after_value < before_value - tolerance
                ):
                    regressions.append(
                        f"{config.name}: assistant {name} regressed "
                        f"{before_value:.3f} -> {after_value:.3f}"
                    )
    return regressions


def _fmt(value: float | None, digits: int = 3) -> str:
    return "–" if value is None else f"{value:.{digits}f}"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def _tag_cases(configs: Sequence[ConfigResult], tag: str) -> int:
    return max((c.by_tag[tag].cases for c in configs if tag in c.by_tag), default=0)


def _short(text: str, limit: int = 70) -> str:
    cleaned = " ".join(text.split()).replace("|", "\\|")
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1] + "…"


def render_markdown(result: BenchmarkResult, questions: dict[str, str] | None = None) -> str:
    questions = questions or {}
    primary = str(result.primary_k)
    ok = [config for config in result.configs if config.status is ConfigStatus.OK]
    lines: list[str] = [
        f"# AJG SOP benchmark report — run {result.run_id}",
        "",
        f"- Created: {result.created_at.isoformat()}",
        f"- Commit: `{result.git_commit or 'unknown'}`",
        f"- Dataset: `{result.dataset}` (sha256 `{result.dataset_sha256[:16]}…`, "
        f"{result.case_count} cases)",
        f"- Corpus fingerprint: `{result.corpus_fingerprint}`",
        f"- Primary k: {result.primary_k}; k values: {', '.join(map(str, result.ks))}",
        "",
    ]
    if result.gate:
        status = "PASSED" if result.gate.passed else "FAILED"
        lines += [
            f"## Gate: {status}",
            "",
            f"Unauthorized retrieval count across all runnable configurations: "
            f"**{result.gate.unauthorized_retrieval_count}** (must be 0).",
            "",
        ]
        lines += [f"- {failure}" for failure in result.gate.failures]
        if result.gate.failures:
            lines.append("")

    lines += ["## Configurations", ""]
    lines += _table(
        ["Configuration", "Status", "Chunker", "Embedding", "Reranker", "Notes"],
        [
            [
                config.name,
                config.status.value,
                str(config.settings.get("chunker", "")),
                str(config.settings.get("embedding", "")),
                str(config.settings.get("reranker", "")),
                _short(config.reason) if config.reason else "",
            ]
            for config in result.configs
        ],
    )
    skipped = [config for config in result.configs if config.status is not ConfigStatus.OK]
    if skipped:
        lines += [
            "",
            "Skipped or failed configurations produced **no numbers**; nothing is estimated "
            "for them.",
        ]

    lines += ["", f"## Retrieval quality @k={result.primary_k}", ""]
    lines += _table(
        [
            "Configuration",
            "Cases",
            "Recall",
            "Precision",
            "MRR",
            "nDCG",
            "Fact recall",
            "Unauthorized",
            "Tech fail",
            "p50 ms",
            "p95 ms",
        ],
        [
            [
                config.name,
                str(config.retrieval_by_k[primary].cases_scored),
                _fmt(config.retrieval_by_k[primary].recall_at_k),
                _fmt(config.retrieval_by_k[primary].precision_at_k),
                _fmt(config.retrieval_by_k[primary].mean_reciprocal_rank),
                _fmt(config.retrieval_by_k[primary].ndcg_at_k),
                _fmt(config.retrieval_by_k[primary].fact_recall_at_k),
                str(config.retrieval_by_k[primary].unauthorized_retrieval_count),
                _fmt(config.retrieval_technical_failure_rate),
                _fmt(config.retrieval_latency_ms_p50, 1),
                _fmt(config.retrieval_latency_ms_p95, 1),
            ]
            for config in ok
        ],
    )

    lines += ["", "## Recall and nDCG by rank depth", ""]
    lines += _table(
        ["Configuration", *[f"Recall@{k}" for k in result.ks], *[f"nDCG@{k}" for k in result.ks]],
        [
            [
                config.name,
                *[_fmt(config.retrieval_by_k[str(k)].recall_at_k) for k in result.ks],
                *[_fmt(config.retrieval_by_k[str(k)].ndcg_at_k) for k in result.ks],
            ]
            for config in ok
        ],
    )

    assistants = [config for config in ok if config.assistant]
    if assistants:
        lines += ["", "## Assistant behaviour (fixture LLM and fixture answerability gate)", ""]
        lines += _table(
            [
                "Configuration",
                "Answerability",
                "Clarification",
                "Clarif. recall",
                "False clarif.",
                "Kind",
                "Citation",
                "Grounding",
                "Fact coverage",
                "Forbidden-fact leak",
                "Tech fail",
                "Unauth ctx",
            ],
            [
                [
                    config.name,
                    _fmt(config.assistant.answerability_accuracy),
                    _fmt(config.assistant.clarification_accuracy),
                    _fmt(config.assistant.clarification_recall),
                    _fmt(config.assistant.false_clarification_rate),
                    _fmt(config.assistant.kind_accuracy),
                    _fmt(config.assistant.citation_correctness),
                    _fmt(config.assistant.grounding_correctness),
                    _fmt(config.assistant.fact_coverage),
                    _fmt(config.assistant.forbidden_fact_leak_rate),
                    _fmt(config.assistant.technical_failure_rate),
                    str(config.assistant.unauthorized_context_count),
                ]
                for config in assistants
                if config.assistant
            ],
        )

    tags = sorted({tag for config in ok for tag in config.by_tag})
    if tags:
        lines += ["", f"## Recall@{result.primary_k} by case category", ""]
        lines += _table(
            ["Category", *[config.name for config in ok]],
            [
                [
                    f"{tag} ({_tag_cases(ok, tag)})",
                    *[_fmt(c.by_tag[tag].recall_at_k) if tag in c.by_tag else "–" for c in ok],
                ]
                for tag in tags
            ],
        )

    lines += ["", "## Index and embedding cost", ""]
    lines += _table(
        [
            "Configuration",
            "Embedding model",
            "Chunks",
            "Chunk chars",
            "Index s",
            "Provider texts",
            "Provider chars",
            "Provider s",
        ],
        [
            [
                config.name,
                config.cost.embedding_model if config.cost else "",
                str(config.cost.chunks) if config.cost else "",
                str(config.cost.chunk_chars) if config.cost else "",
                _fmt(config.cost.index_build_seconds if config.cost else None, 2),
                str(config.cost.provider_texts) if config.cost else "",
                str(config.cost.provider_chars) if config.cost else "",
                _fmt(config.cost.provider_seconds if config.cost else None, 2),
            ]
            for config in ok
        ],
    )

    if ok:
        focus = ok[0]
        misses = [case for case in focus.cases if case.missing_sections]
        lines += ["", f"## Misses for `{focus.name}` (recall < 1 at k={result.primary_k})", ""]
        if misses:
            lines += _table(
                ["Case", "Question", "Missing sections"],
                [
                    [
                        case.case_id,
                        _short(questions.get(case.case_id, "")),
                        _short(", ".join(case.missing_sections), 90),
                    ]
                    for case in misses[:40]
                ],
            )
            if len(misses) > 40:
                lines.append(f"\n…and {len(misses) - 40} more in `results.json`.")
        else:
            lines.append("None.")

    leaks = [
        (config.name, case) for config in ok for case in config.cases if case.unauthorized_sections
    ]
    lines += ["", "## Unauthorized retrieval details", ""]
    if leaks:
        lines += _table(
            ["Configuration", "Case", "Leaked sections"],
            [[name, case.case_id, ", ".join(case.unauthorized_sections)] for name, case in leaks],
        )
    else:
        lines.append("No unauthorized sections were returned at the primary k.")

    lines += [
        "",
        "## How to read these numbers",
        "",
        "- Section keys are chunker-independent; every case is scored on the section its answer "
        "lives in, plus declared alternates.",
        "- `fixture-hash` is a deterministic bag-of-words stand-in, not a semantic model. It says "
        "nothing about E5 or BGE-M3 quality; those rows exist only when a provider could be built.",
        "- The assistant section uses the repository's fixture LLM (echoes the top evidence) and "
        "evidence-presence answerability gate, so it measures the current routing, gate, citation "
        "and grounding code, not generation quality.",
        "- Access labels come from a synthetic overlay (`access_overlay.json`) because the source "
        "Markdown carries none.",
        "- Unauthorized retrieval is verified by an oracle independent of the production filter.",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(
    result: BenchmarkResult, output_dir: Path, questions: dict[str, str] | None = None
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "results.json"
    markdown_path = output_dir / "report.md"
    json_path.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(result, questions), encoding="utf-8")
    return json_path, markdown_path


def load_result(path: Path) -> BenchmarkResult:
    return BenchmarkResult.model_validate_json(path.read_text(encoding="utf-8"))


def config_by_name(result: BenchmarkResult, name: str) -> ConfigResult | None:
    return next((config for config in result.configs if config.name == name), None)
