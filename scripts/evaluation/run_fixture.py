import json
from pathlib import Path

from services.evaluation.models import EvaluationCase
from services.evaluation.retrieval import evaluate_ranked_sections


def main() -> None:
    dataset = Path("services/evaluation/datasets/fixture.jsonl")
    cases = [
        EvaluationCase.model_validate_json(line)
        for line in dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    # This smoke command validates the harness shape. Real ranked results arrive after SOP review.
    metrics = evaluate_ranked_sections(cases, [[] for _ in cases])
    print(json.dumps(metrics.model_dump(), indent=2))


if __name__ == "__main__":
    main()
