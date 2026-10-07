import math

import pytest
from pydantic import ValidationError

from packages.contracts.common import Language
from services.evaluation.metrics import (
    fact_recall,
    facts_present,
    ndcg_at_k,
    normalize_text,
    percentile,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from services.evaluation.models import EvaluationCase, EvaluationScope
from services.evaluation.retrieval import evaluate_ranked_sections

SCOPE = EvaluationScope(department="store", location="mill-1", role="store_keeper")


def make_case(**overrides: object) -> EvaluationCase:
    values: dict[str, object] = {
        "question": "q",
        "language": Language.ENGLISH,
        "employee_scope": SCOPE,
        "expected_sections": {"a"},
        "answerable": True,
    }
    values.update(overrides)
    return EvaluationCase.model_validate(values)


def test_recall_counts_alternate_once_for_a_missing_expected_section() -> None:
    assert recall_at_k(["x", "alt"], {"a", "b"}, {"alt"}, 5) == 0.5
    assert recall_at_k(["a", "alt", "alt2"], {"a", "b"}, {"alt", "alt2"}, 5) == 1.0
    assert recall_at_k(["x", "a"], {"a"}, set(), 1) == 0.0


def test_recall_requires_expected_sections() -> None:
    with pytest.raises(ValueError):
        recall_at_k(["a"], set(), set(), 3)


def test_precision_is_chunk_level_and_uses_returned_count() -> None:
    assert precision_at_k(["a", "a", "x"], {"a"}, set(), 5) == pytest.approx(2 / 3)
    assert precision_at_k([], {"a"}, set(), 5) == 0.0


def test_reciprocal_rank_uses_deduplicated_sections() -> None:
    assert reciprocal_rank(["x", "x", "a"], {"a"}, set(), 5) == 0.5
    assert reciprocal_rank(["x", "a"], {"a"}, set(), 1) == 0.0


def test_ndcg_perfect_and_degraded() -> None:
    assert ndcg_at_k(["a", "b"], {"a", "b"}, set(), 5) == pytest.approx(1.0)
    worse = ndcg_at_k(["x", "a"], {"a"}, set(), 5)
    assert worse == pytest.approx(1 / math.log2(3))
    assert ndcg_at_k(["x"], {"a"}, set(), 5) == 0.0


def test_fact_matching_normalises_case_and_punctuation() -> None:
    text = "Report within  TWO days – to the Officer"
    assert normalize_text("A  b") == "a b"
    assert facts_present(["two days", "officer", "nope"], text) == [True, True, False]
    assert fact_recall(["two days", "nope"], text) == 0.5


def test_percentile_nearest_rank() -> None:
    assert percentile([], 0.5) == 0.0
    assert percentile([1, 2, 3, 4], 0.5) == 2
    assert percentile([1, 2, 3, 4], 0.95) == 4


def test_unauthorized_rate_detects_forbidden_and_oracle_restricted_sections() -> None:
    case = make_case(forbidden_sections={"hr"})
    metrics = evaluate_ranked_sections(
        [case], [["a", "hr", "secret", "b"]], k=4, restricted_sections=[{"secret"}]
    )
    assert metrics.unauthorized_retrieval_count == 2
    assert metrics.unauthorized_retrieval_rate == 0.5
    assert metrics.cases_with_unauthorized_retrieval == 1


def test_clean_run_reports_zero_unauthorized() -> None:
    metrics = evaluate_ranked_sections([make_case()], [["a"]], k=3)
    assert metrics.unauthorized_retrieval_rate == 0
    assert metrics.recall_at_k == 1


def test_cases_without_expected_sections_do_not_inflate_rank_metrics() -> None:
    no_answer = make_case(expected_sections=set(), answerable=False, forbidden_sections={"hr"})
    metrics = evaluate_ranked_sections([make_case(), no_answer], [["x"], ["hr"]], k=3)
    assert metrics.cases_scored == 1
    assert metrics.recall_at_k == 0
    assert metrics.unauthorized_retrieval_count == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"forbidden_sections": {"a"}},
        {"alternate_sections": {"a"}},
        {"expected_sections": set(), "alternate_sections": {"b"}, "answerable": False},
        {"requires_clarification": True},
        {"answerable": False},
        {"expected_sections": set()},
        {"expected_facts": ["x"], "forbidden_facts": ["x"]},
    ],
)
def test_case_validation_rejects_inconsistent_cases(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make_case(**overrides)


def test_case_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        make_case(surprise=True)
