"""Benchmark dataset loading and validation against the corpus.

Validation is what keeps expected answers honest: every expected fact must literally appear in
an expected or alternate section, every expected/alternate section must be readable by the
case's employee, and every forbidden fact must be absent from everything that employee may read.
"""

from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from services.evaluation.corpus import Corpus
from services.evaluation.metrics import normalize_text
from services.evaluation.models import EvaluationCase


def load_dataset(path: Path) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        case = EvaluationCase.model_validate_json(line)
        if not case.id:
            case = case.model_copy(update={"id": f"{path.stem}-{line_number:03d}"})
        cases.append(case)
    ids = [case.id for case in cases]
    duplicates = sorted(identifier for identifier, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise ValueError(f"Duplicate case ids: {duplicates}")
    return cases


def validate_dataset(cases: Sequence[EvaluationCase], corpus: Corpus) -> list[str]:
    """Return human-readable problems; an empty list means the dataset is consistent."""
    problems: list[str] = []
    for case in cases:
        label = case.id or case.question[:40]
        referenced = case.expected_sections | case.alternate_sections | case.forbidden_sections
        unknown = sorted(key for key in referenced if key not in corpus.sections)
        if unknown:
            problems.append(f"{label}: unknown section keys {unknown}")
            continue
        denied = corpus.restricted_for(case.employee_scope)
        for key in sorted((case.expected_sections | case.alternate_sections) & denied):
            problems.append(f"{label}: expected/alternate section {key} is not readable by scope")
        for key in sorted(case.forbidden_sections - denied):
            problems.append(f"{label}: forbidden section {key} is readable by the case scope")
        relevant_text = " ".join(
            corpus.sections[key].normalized_text
            for key in case.expected_sections | case.alternate_sections
        )
        for fact in case.expected_facts:
            if normalize_text(fact) not in relevant_text:
                problems.append(f"{label}: expected fact not found in expected sections: {fact!r}")
        readable_text = " ".join(
            section.normalized_text for key, section in corpus.sections.items() if key not in denied
        )
        denied_text = " ".join(
            corpus.sections[key].normalized_text for key in case.forbidden_sections
        )
        for fact in case.forbidden_facts:
            if normalize_text(fact) in readable_text:
                problems.append(f"{label}: forbidden fact appears in readable content: {fact!r}")
        if (
            "unauthorized" in case.tags
            and case.forbidden_sections
            and case.forbidden_facts
            and not any(normalize_text(fact) in denied_text for fact in case.forbidden_facts)
        ):
            problems.append(f"{label}: no forbidden fact appears in the forbidden sections")
    return problems


def summarize_dataset(cases: Sequence[EvaluationCase]) -> dict[str, object]:
    tags: Counter[str] = Counter()
    for case in cases:
        tags.update(case.tags)
    return {
        "cases": len(cases),
        "answerable": sum(case.answerable for case in cases),
        "unanswerable": sum(not case.answerable for case in cases),
        "requires_clarification": sum(case.requires_clarification for case in cases),
        "languages": dict(Counter(case.language.value for case in cases)),
        "tags": dict(sorted(tags.items())),
    }
