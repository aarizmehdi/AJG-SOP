from collections.abc import Collection, Sequence

from pydantic import BaseModel

from services.evaluation.metrics import (
    fact_recall,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from services.evaluation.models import EvaluationCase, RetrievalMetrics


class CaseRetrievalScore(BaseModel):
    """Per-case retrieval result; rank fields are ``None`` for cases without expected sections."""

    case_id: str
    k: int
    returned: int
    recall: float | None = None
    precision: float | None = None
    reciprocal_rank: float | None = None
    ndcg: float | None = None
    fact_recall: float | None = None
    unauthorized_sections: list[str] = []


def score_case(
    case: EvaluationCase,
    ranked: Sequence[str],
    k: int,
    *,
    ranked_texts: Sequence[str] | None = None,
    restricted_sections: Collection[str] = (),
) -> CaseRetrievalScore:
    """Score one ranked chunk list.

    ``restricted_sections`` are sections the employee may not read according to an oracle that is
    independent of the retrieval pipeline (the corpus access labels). They are added to the
    case's own ``forbidden_sections`` when counting unauthorized retrieval.
    """
    top = list(ranked[:k])
    forbidden = set(case.forbidden_sections) | set(restricted_sections)
    score = CaseRetrievalScore(
        case_id=case.id,
        k=k,
        returned=len(top),
        unauthorized_sections=[key for key in top if key in forbidden],
    )
    if case.expected_sections:
        score.recall = recall_at_k(top, case.expected_sections, case.alternate_sections, k)
        score.precision = precision_at_k(top, case.expected_sections, case.alternate_sections, k)
        score.reciprocal_rank = reciprocal_rank(
            top, case.expected_sections, case.alternate_sections, k
        )
        score.ndcg = ndcg_at_k(top, case.expected_sections, case.alternate_sections, k)
        if case.expected_facts and ranked_texts is not None:
            score.fact_recall = fact_recall(case.expected_facts, "\n".join(ranked_texts[:k]))
    return score


def aggregate_scores(scores: Sequence[CaseRetrievalScore], k: int) -> RetrievalMetrics:
    ranked = [score for score in scores if score.recall is not None]
    facts = [score.fact_recall for score in scores if score.fact_recall is not None]
    returned = sum(score.returned for score in scores)
    leaked = sum(len(score.unauthorized_sections) for score in scores)

    def mean(values: Sequence[float | None]) -> float:
        present = [value for value in values if value is not None]
        return sum(present) / len(present) if present else 0.0

    return RetrievalMetrics(
        k=k,
        cases_scored=len(ranked),
        recall_at_k=mean([score.recall for score in ranked]),
        precision_at_k=mean([score.precision for score in ranked]),
        mean_reciprocal_rank=mean([score.reciprocal_rank for score in ranked]),
        ndcg_at_k=mean([score.ndcg for score in ranked]),
        fact_recall_at_k=sum(facts) / len(facts) if facts else None,
        unauthorized_retrieval_rate=leaked / returned if returned else 0.0,
        unauthorized_retrieval_count=leaked,
        cases_with_unauthorized_retrieval=sum(1 for score in scores if score.unauthorized_sections),
    )


def evaluate_ranked_sections(
    cases: Sequence[EvaluationCase],
    ranked_sections: Sequence[Sequence[str]],
    *,
    k: int | None = None,
    ranked_texts: Sequence[Sequence[str]] | None = None,
    restricted_sections: Sequence[Collection[str]] | None = None,
) -> RetrievalMetrics:
    if len(cases) != len(ranked_sections):
        raise ValueError("Every evaluation case requires one ranked result list")
    if ranked_texts is not None and len(ranked_texts) != len(cases):
        raise ValueError("Every evaluation case requires one ranked text list")
    if restricted_sections is not None and len(restricted_sections) != len(cases):
        raise ValueError("Every evaluation case requires one restricted-section set")
    depth = k if k is not None else max((len(ranked) for ranked in ranked_sections), default=1)
    depth = max(depth, 1)
    scores = [
        score_case(
            case,
            ranked,
            depth,
            ranked_texts=ranked_texts[index] if ranked_texts is not None else None,
            restricted_sections=restricted_sections[index] if restricted_sections else (),
        )
        for index, (case, ranked) in enumerate(zip(cases, ranked_sections, strict=True))
    ]
    return aggregate_scores(scores, depth)
