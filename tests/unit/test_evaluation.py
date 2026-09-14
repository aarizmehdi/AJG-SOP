from packages.contracts.common import Language
from services.evaluation.models import EvaluationCase, EvaluationScope
from services.evaluation.retrieval import evaluate_ranked_sections


def test_evaluation_reports_unauthorized_retrieval() -> None:
    case = EvaluationCase(
        question="damaged stock",
        language=Language.ENGLISH,
        employee_scope=EvaluationScope(
            department="store", location="peshawar-main", role="store_keeper"
        ),
        expected_sections={"section-4.3"},
        forbidden_sections={"section-hr"},
        answerable=True,
    )

    metrics = evaluate_ranked_sections([case], [["section-4.3", "section-hr"]])

    assert metrics.recall_at_k == 1
    assert metrics.precision_at_k == 0.5
    assert metrics.mean_reciprocal_rank == 1
    assert metrics.unauthorized_retrieval_rate == 0.5
