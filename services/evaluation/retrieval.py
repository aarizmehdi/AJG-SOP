from collections.abc import Sequence

from services.evaluation.models import EvaluationCase, RetrievalMetrics


def evaluate_ranked_sections(
    cases: Sequence[EvaluationCase], ranked_sections: Sequence[Sequence[str]]
) -> RetrievalMetrics:
    if len(cases) != len(ranked_sections):
        raise ValueError("Every evaluation case requires one ranked result list")
    if not cases:
        return RetrievalMetrics(
            recall_at_k=0,
            precision_at_k=0,
            mean_reciprocal_rank=0,
            unauthorized_retrieval_rate=0,
        )
    recalls: list[float] = []
    precisions: list[float] = []
    reciprocal_ranks: list[float] = []
    unauthorized = 0
    retrieved_total = 0
    for case, ranked in zip(cases, ranked_sections, strict=True):
        result_set = set(ranked)
        hits = len(case.expected_sections & result_set)
        recalls.append(hits / len(case.expected_sections) if case.expected_sections else 1.0)
        precisions.append(hits / len(ranked) if ranked else 0.0)
        first_rank = next(
            (
                index
                for index, section_id in enumerate(ranked, start=1)
                if section_id in case.expected_sections
            ),
            None,
        )
        reciprocal_ranks.append(1 / first_rank if first_rank else 0.0)
        unauthorized += len(case.forbidden_sections & result_set)
        retrieved_total += len(ranked)
    count = len(cases)
    return RetrievalMetrics(
        recall_at_k=sum(recalls) / count,
        precision_at_k=sum(precisions) / count,
        mean_reciprocal_rank=sum(reciprocal_ranks) / count,
        unauthorized_retrieval_rate=unauthorized / retrieved_total if retrieved_total else 0.0,
    )
