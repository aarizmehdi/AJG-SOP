"""Run the AJG SOP retrieval/assistant benchmark.

    uv run python -m scripts.evaluation.run_benchmark

Writes ``results.json`` and ``report.md`` to the output directory. Exit codes:
0 = gate passed, 1 = gate failed (unauthorized retrieval > 0, regression or failed config),
2 = dataset/configuration/corpus error.
"""

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from services.evaluation.corpus import load_corpus_async, load_overlay
from services.evaluation.dataset import load_dataset, summarize_dataset, validate_dataset
from services.evaluation.harness import run_benchmark
from services.evaluation.matrix import load_matrix
from services.evaluation.report import evaluate_gate, load_result, write_outputs

DATASETS = Path("services/evaluation/datasets")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, prog="run_benchmark")
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=Path(os.environ.get("AJG_EVAL_CORPUS_DIR", "services/evaluation/corpus")),
        help="Directory of SOP Markdown files (never committed)",
    )
    parser.add_argument("--dataset", type=Path, default=DATASETS / "ajg_sop_benchmark.jsonl")
    parser.add_argument("--overlay", type=Path, default=DATASETS / "access_overlay.json")
    parser.add_argument("--matrix", type=Path, default=DATASETS / "matrix.default.json")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--only", action="append", default=None, help="Run only this config")
    parser.add_argument("--no-assistant", action="store_true", help="Skip assistant evaluation")
    parser.add_argument("--baseline", type=Path, default=None, help="Earlier results.json")
    parser.add_argument("--tolerance", type=float, default=0.0)
    parser.add_argument("--max-technical-failure-rate", type=float, default=None)
    parser.add_argument("--validate-only", action="store_true", help="Validate dataset and exit")
    return parser


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


async def _main(args: argparse.Namespace) -> int:
    try:
        corpus = await load_corpus_async(args.corpus_dir, load_overlay(args.overlay))
        cases = load_dataset(args.dataset)
        matrix = load_matrix(args.matrix)
    except (OSError, ValueError) as error:
        _log(f"error: {error}")
        return 2
    problems = validate_dataset(cases, corpus)
    if problems:
        _log(f"dataset validation failed with {len(problems)} problem(s):")
        for problem in problems[:50]:
            _log(f"  - {problem}")
        return 2
    _log(f"dataset ok: {summarize_dataset(cases)}")
    if args.validate_only:
        return 0
    if args.no_assistant:
        matrix = matrix.model_copy(
            update={
                "configs": [
                    config.model_copy(update={"assistant": False}) for config in matrix.configs
                ]
            }
        )
    try:
        result = await run_benchmark(
            corpus,
            cases,
            matrix,
            dataset_path=args.dataset,
            environment=os.environ,
            only=args.only,
            progress=_log,
        )
    except ValueError as error:
        _log(f"error: {error}")
        return 2
    baseline = load_result(args.baseline) if args.baseline else None
    result.gate = evaluate_gate(
        result,
        baseline,
        tolerance=args.tolerance,
        max_technical_failure_rate=args.max_technical_failure_rate,
    )
    output_dir = args.output_dir or Path("evaluation_runs") / datetime.now(UTC).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    json_path, markdown_path = write_outputs(
        result, output_dir, {case.id: case.question for case in cases}
    )
    _log(f"wrote {json_path} and {markdown_path}")
    if result.gate.passed:
        _log("GATE PASSED: unauthorized retrieval rate is 0")
        return 0
    _log("GATE FAILED:")
    for failure in result.gate.failures:
        _log(f"  - {failure}")
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_main(build_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
