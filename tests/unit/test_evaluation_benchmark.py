"""End-to-end benchmark tests on a tiny synthetic corpus (no private SOP files needed)."""

import json
from pathlib import Path
from typing import Any

import pytest

from packages.contracts.canonical import RetrievalChunk
from packages.contracts.common import Language
from scripts.evaluation.run_benchmark import main as run_cli
from services.evaluation.corpus import (
    AccessOverlay,
    Corpus,
    OverlayRule,
    load_corpus_async,
    load_overlay,
)
from services.evaluation.dataset import load_dataset, summarize_dataset, validate_dataset
from services.evaluation.harness import run_benchmark
from services.evaluation.matrix import MatrixSpec, RetrievalConfig, load_matrix
from services.evaluation.models import EvaluationCase, EvaluationScope
from services.evaluation.providers import (
    MeteredEmbeddingProvider,
    ProviderUnavailableError,
    StableHashEmbeddingProvider,
    build_embedding,
    build_reranker,
)
from services.evaluation.report import (
    compare_to_baseline,
    evaluate_gate,
    load_result,
    render_markdown,
    write_outputs,
)
from services.evaluation.results import ConfigStatus
from services.retrieval.authorization_filter import AuthorizationFilter

SOP = """# Gate Rules

## Visitor Entry
Visitors must register at the gate and wear a badge. The badge must be returned by 5 PM.

## Waste Dispatch
Waste trucks are weighed twice. Variance above 2 percent must be reported to the excise officer.

## Store Issue
Store items are issued only against a signed requisition slip approved by the store officer.
"""

STORE = EvaluationScope(department="store", location="mill-1", role="store_keeper")
EXCISE = EvaluationScope(department="excise", location="mill-1", role="excise_incharge")


def case(**overrides: Any) -> EvaluationCase:
    values: dict[str, Any] = {
        "id": "c",
        "language": Language.ENGLISH,
        "employee_scope": STORE,
        "answerable": True,
    }
    values.update(overrides)
    return EvaluationCase.model_validate(values)


CASES = [
    case(
        id="visitor",
        question="Until what time must the visitor badge be returned?",
        expected_sections={"d1:visitor-entry"},
        expected_facts=["5 PM"],
    ),
    case(
        id="waste-allowed",
        question="What variance in waste truck weight must be reported?",
        employee_scope=EXCISE,
        expected_sections={"d1:waste-dispatch"},
        expected_facts=["2 percent"],
    ),
    case(
        id="waste-denied",
        question="What variance in waste truck weight must be reported to the excise officer?",
        answerable=False,
        forbidden_sections={"d1:waste-dispatch"},
        forbidden_facts=["2 percent"],
        tags={"restricted", "unauthorized"},
    ),
    case(
        id="no-answer",
        question="What is the cafeteria menu on Fridays?",
        answerable=False,
    ),
]


@pytest.fixture
def corpus_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "corpus"
    directory.mkdir()
    (directory / "sop_1.md").write_text(SOP, encoding="utf-8")
    return directory


@pytest.fixture
def overlay() -> AccessOverlay:
    return AccessOverlay(
        rules=[OverlayRule(keys=["d1:waste-dispatch"], departments=["excise"], reason="test")]
    )


@pytest.fixture
async def corpus(corpus_dir: Path, overlay: AccessOverlay) -> Corpus:
    return await load_corpus_async(corpus_dir, overlay)


async def test_corpus_loads_with_stable_keys_and_oracle(corpus: Corpus) -> None:
    assert list(corpus.sections) == ["d1:visitor-entry", "d1:waste-dispatch", "d1:store-issue"]
    assert corpus.allows("d1:waste-dispatch", EXCISE)
    assert not corpus.allows("d1:waste-dispatch", STORE)
    assert corpus.restricted_for(STORE) == {"d1:waste-dispatch"}
    assert corpus.fingerprint


async def test_unmatched_overlay_rule_is_an_error(corpus_dir: Path) -> None:
    bad = AccessOverlay(rules=[OverlayRule(keys=["d1:does-not-exist"], departments=["x"])])
    with pytest.raises(ValueError):
        await load_corpus_async(corpus_dir, bad)


async def test_dataset_validation_accepts_consistent_cases(corpus: Corpus) -> None:
    assert validate_dataset(CASES, corpus) == []
    assert summarize_dataset(CASES)["cases"] == 4


async def test_dataset_validation_catches_invented_facts_and_access_errors(
    corpus: Corpus,
) -> None:
    invented = case(
        id="invented",
        question="q",
        expected_sections={"d1:visitor-entry"},
        expected_facts=["9 PM"],
    )
    unreadable = case(
        id="unreadable", question="q", expected_sections={"d1:waste-dispatch"}, expected_facts=[]
    )
    not_denied = case(
        id="not-denied",
        question="q",
        answerable=False,
        forbidden_sections={"d1:visitor-entry"},
    )
    unknown = case(id="unknown", question="q", expected_sections={"d1:nope"})
    problems = validate_dataset([invented, unreadable, not_denied, unknown], corpus)
    joined = "\n".join(problems)
    for label in ("invented", "unreadable", "not-denied", "unknown"):
        assert label in joined


def test_load_dataset_assigns_ids_and_rejects_duplicates(tmp_path: Path) -> None:
    payload = CASES[0].model_dump(mode="json")
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps({**payload, "id": ""}) + "\n", encoding="utf-8")
    assert load_dataset(path)[0].id == "cases-001"
    path.write_text(json.dumps(payload) + "\n" + json.dumps(payload) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_dataset(path)


def write_dataset(path: Path) -> Path:
    path.write_text("\n".join(item.model_dump_json() for item in CASES) + "\n", encoding="utf-8")
    return path


MATRIX = MatrixSpec(
    ks=[1, 3],
    primary_k=3,
    configs=[
        RetrievalConfig(name="base"),
        RetrievalConfig(name="lexical", semantic=False),
        RetrievalConfig(name="e5", embedding="plugin:no_such_module:factory"),
    ],
)


async def test_benchmark_runs_gates_and_reports(corpus: Corpus, tmp_path: Path) -> None:
    dataset = write_dataset(tmp_path / "cases.jsonl")
    result = await run_benchmark(corpus, CASES, MATRIX, dataset_path=dataset)
    statuses = {config.name: config.status for config in result.configs}
    assert statuses == {
        "base": ConfigStatus.OK,
        "lexical": ConfigStatus.OK,
        "e5": ConfigStatus.SKIPPED,
    }
    base = result.configs[0]
    assert base.retrieval_by_k["3"].unauthorized_retrieval_count == 0
    assert base.retrieval_by_k["3"].recall_at_k == 1.0
    assert base.assistant is not None
    assert base.assistant.unauthorized_context_count == 0
    assert result.configs[2].retrieval_by_k == {}

    result.gate = evaluate_gate(result)
    assert result.gate.passed

    json_path, markdown_path = write_outputs(result, tmp_path / "out", {"visitor": "badge?"})
    assert load_result(json_path).run_id == result.run_id
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "Gate: PASSED" in markdown
    assert "skipped" in markdown
    assert render_markdown(result) == render_markdown(load_result(json_path))


class _LeakyEligibility(AuthorizationFilter):
    """First stage ignores access scopes, like a broken fail-open filter."""

    def eligible_chunks(self, profile: Any) -> list[RetrievalChunk]:
        return [chunk for chunks in self._store.chunks.values() for chunk in chunks]


class _FullyLeakyFilter(_LeakyEligibility):
    def revalidate(self, profile: Any, chunk: RetrievalChunk) -> bool:
        return True


async def _leak_gate(
    corpus: Corpus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, filter_class: type
) -> Any:
    monkeypatch.setattr("services.evaluation.harness.AuthorizationFilter", filter_class)
    dataset = write_dataset(tmp_path / "cases.jsonl")
    matrix = MatrixSpec(ks=[3], primary_k=3, configs=[RetrievalConfig(name="base")])
    result = await run_benchmark(corpus, CASES, matrix, dataset_path=dataset)
    assert result.configs[0].retrieval_technical_failure_rate == 0
    return evaluate_gate(result)


async def test_gate_fails_when_the_authorization_filter_leaks(
    corpus: Corpus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = await _leak_gate(corpus, tmp_path, monkeypatch, _FullyLeakyFilter)
    assert not gate.passed
    assert gate.unauthorized_retrieval_count > 0
    assert "must be 0" in "\n".join(gate.failures)


async def test_production_revalidation_blocks_a_leaky_first_stage(
    corpus: Corpus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = await _leak_gate(corpus, tmp_path, monkeypatch, _LeakyEligibility)
    assert gate.passed
    assert gate.unauthorized_retrieval_count == 0


async def test_baseline_regression_is_detected(corpus: Corpus, tmp_path: Path) -> None:
    dataset = write_dataset(tmp_path / "cases.jsonl")
    matrix = MatrixSpec(ks=[3], primary_k=3, configs=[RetrievalConfig(name="base")])
    good = await run_benchmark(corpus, CASES, matrix, dataset_path=dataset)
    worse = good.model_copy(deep=True)
    worse.configs[0].retrieval_by_k["3"].recall_at_k = 0.1
    assert compare_to_baseline(worse, good, 0.0)
    assert not compare_to_baseline(good, good, 0.0)
    assert not evaluate_gate(worse, good).passed


async def test_a_failing_config_fails_the_gate(corpus: Corpus, tmp_path: Path) -> None:
    dataset = write_dataset(tmp_path / "cases.jsonl")
    matrix = MatrixSpec(ks=[3], primary_k=3, configs=[RetrievalConfig(name="base")])
    result = await run_benchmark(corpus, CASES, matrix, dataset_path=dataset)
    result.configs[0].status = ConfigStatus.FAILED
    assert not evaluate_gate(result).passed


async def test_unknown_only_name_is_rejected(corpus: Corpus, tmp_path: Path) -> None:
    dataset = write_dataset(tmp_path / "cases.jsonl")
    with pytest.raises(ValueError):
        await run_benchmark(corpus, CASES, MATRIX, dataset_path=dataset, only=["nope"])


async def test_stable_embedding_is_deterministic_and_metered() -> None:
    inner = StableHashEmbeddingProvider()
    assert await inner.embed_query("badge return") == await inner.embed_query("badge return")
    metered = MeteredEmbeddingProvider(inner)
    await metered.embed_documents(["a b", "a b", "c"])
    await metered.embed_documents(["a b"])
    await metered.embed_query("q")
    await metered.embed_query("q")
    assert metered.cost.provider_texts == 3  # "a b", "c", "q"
    assert metered.cost.cache_hits >= 3


def test_unavailable_components_raise_instead_of_substituting() -> None:
    with pytest.raises(ProviderUnavailableError):
        build_embedding("pinecone-e5", {})
    with pytest.raises(ProviderUnavailableError):
        build_embedding("plugin:no_such_module:factory")
    with pytest.raises(ProviderUnavailableError):
        build_reranker("plugin:bad-spec")
    assert build_reranker("none") is not None


def test_default_matrix_is_valid() -> None:
    matrix = load_matrix(Path("services/evaluation/datasets/matrix.default.json"))
    names = {config.name for config in matrix.configs}
    assert {"current-default", "e5", "bge-m3", "no-reranker"} <= names


async def test_cli_exit_codes(corpus_dir: Path, tmp_path: Path, overlay: AccessOverlay) -> None:
    dataset = write_dataset(tmp_path / "cases.jsonl")
    overlay_path = tmp_path / "overlay.json"
    overlay_path.write_text(overlay.model_dump_json(), encoding="utf-8")
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        MatrixSpec(ks=[3], primary_k=3, configs=[RetrievalConfig(name="base")]).model_dump_json(),
        encoding="utf-8",
    )
    base = [
        "--corpus-dir", str(corpus_dir),
        "--dataset", str(dataset),
        "--overlay", str(overlay_path),
        "--matrix", str(matrix_path),
    ]  # fmt: skip
    out = tmp_path / "run"
    assert await _run(base + ["--output-dir", str(out)]) == 0
    assert (out / "results.json").exists() and (out / "report.md").exists()
    assert await _run(base + ["--validate-only"]) == 0
    assert await _run([*base, "--only", "missing", "--output-dir", str(out)]) == 2
    assert await _run(["--corpus-dir", str(tmp_path / "empty"), "--validate-only"]) == 2


async def _run(argv: list[str]) -> int:
    import anyio

    return await anyio.to_thread.run_sync(run_cli, argv)


REAL_CORPUS = Path("services/evaluation/corpus")


@pytest.mark.skipif(
    not any(REAL_CORPUS.glob("*.md")), reason="private SOP corpus not present locally"
)
async def test_shipped_dataset_is_consistent_with_the_real_corpus() -> None:
    overlay = load_overlay(Path("services/evaluation/datasets/access_overlay.json"))
    real = await load_corpus_async(REAL_CORPUS, overlay)
    cases = load_dataset(Path("services/evaluation/datasets/ajg_sop_benchmark.jsonl"))
    assert validate_dataset(cases, real) == []
    assert len(cases) >= 100
