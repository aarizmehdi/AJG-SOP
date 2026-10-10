"""Quick check that the evaluation framework works.

    uv run python -m scripts.evaluation.check_setup

Runs the shipped dataset against the local SOP corpus (services/evaluation/corpus/*.md) if it is
present, otherwise against a tiny built-in corpus. Prints PASS/FAIL per check, exits 1 on failure.
"""

import asyncio
import sys
import tempfile
from pathlib import Path

from services.evaluation.corpus import load_corpus_async, load_overlay
from services.evaluation.dataset import load_dataset, validate_dataset
from services.evaluation.harness import run_benchmark
from services.evaluation.matrix import MatrixSpec, RetrievalConfig
from services.evaluation.report import evaluate_gate, write_outputs

DATA = Path("services/evaluation/datasets")
CORPUS = Path("services/evaluation/corpus")
TINY = "# Gate\n\n## Visitor Entry\nVisitors must wear a badge returned by 5 PM.\n"


def _report(name: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}".rstrip())
    return ok


def _prepare() -> tuple[bool, Path]:
    if any(CORPUS.glob("*.md")):
        return True, CORPUS
    directory = Path(tempfile.mkdtemp()) / "c"
    directory.mkdir()
    (directory / "sop_1.md").write_text(TINY, encoding="utf-8")
    return False, directory


async def main() -> int:
    results: list[bool] = []
    real, directory = _prepare()
    print(f"corpus: {'local SOP files' if real else 'built-in tiny corpus'}")
    corpus = await load_corpus_async(
        directory, load_overlay(DATA / "access_overlay.json" if real else None)
    )
    results.append(
        _report("corpus loads", len(corpus.sections) > 0, f"({len(corpus.sections)} sections)")
    )
    dataset = DATA / "ajg_sop_benchmark.jsonl"
    cases = load_dataset(dataset)
    results.append(_report("dataset loads", len(cases) > 0, f"({len(cases)} cases)"))
    if real:
        problems = validate_dataset(cases, corpus)
        results.append(
            _report("dataset matches SOP text", not problems, f"({len(problems)} problems)")
        )
        for problem in problems[:20]:
            print(f"    - {problem}")
    else:
        cases = []
    matrix = MatrixSpec(ks=[1, 5], primary_k=5, configs=[RetrievalConfig(name="check")])
    if not cases:
        print("skipping benchmark run (needs local SOP files)")
    else:
        result = await run_benchmark(corpus, cases, matrix, dataset_path=dataset)
        config = result.configs[0]
        results.append(_report("benchmark runs", config.status.value == "ok"))
        metrics = config.retrieval_by_k["5"]
        results.append(
            _report("unauthorized retrieval == 0", metrics.unauthorized_retrieval_count == 0)
        )
        results.append(
            _report("recall@5 > 0", metrics.recall_at_k > 0, f"({metrics.recall_at_k:.3f})")
        )
        result.gate = evaluate_gate(result)
        results.append(_report("gate passes", result.gate.passed))
        out = Path(tempfile.mkdtemp())
        json_path, md_path = write_outputs(result, out)
        results.append(
            _report("reports written", json_path.exists() and md_path.exists(), f"({out})")
        )
    print("ALL CHECKS PASSED" if all(results) else "SOME CHECKS FAILED")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))