"""Pure ranking metrics. No retrieval, model, or I/O dependencies.

Conventions (kept identical everywhere in the framework):

* A ranked list holds one section key per returned chunk, best first. Duplicates are allowed
  when a section was split into several chunks.
* ``relevant`` = expected sections plus acceptable alternates. An alternate may stand in for an
  expected section that was not retrieved, but never counts for more than one expected section.
* Recall / MRR / nDCG work on the de-duplicated section order inside the first ``k`` chunks.
* Precision counts chunks, so duplicate chunks of one section do not inflate it and wasted
  slots show up. The denominator is the number of chunks actually returned (at most ``k``).
"""

import math
from collections.abc import Collection, Sequence


def _unique(ranked: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for key in ranked:
        if key not in seen:
            seen.add(key)
            ordered.append(key)
    return ordered


def recall_at_k(
    ranked: Sequence[str], expected: Collection[str], alternates: Collection[str], k: int
) -> float:
    if not expected:
        raise ValueError("Recall is undefined without expected sections")
    found = set(ranked[:k])
    expected_set = set(expected)
    hits = len(expected_set & found)
    substitutes = min(len(expected_set) - hits, len((set(alternates) - expected_set) & found))
    return (hits + substitutes) / len(expected_set)


def precision_at_k(
    ranked: Sequence[str], expected: Collection[str], alternates: Collection[str], k: int
) -> float:
    top = ranked[:k]
    if not top:
        return 0.0
    relevant = set(expected) | set(alternates)
    return sum(1 for key in top if key in relevant) / len(top)


def reciprocal_rank(
    ranked: Sequence[str], expected: Collection[str], alternates: Collection[str], k: int
) -> float:
    relevant = set(expected) | set(alternates)
    for position, key in enumerate(_unique(ranked[:k]), start=1):
        if key in relevant:
            return 1.0 / position
    return 0.0


def ndcg_at_k(
    ranked: Sequence[str], expected: Collection[str], alternates: Collection[str], k: int
) -> float:
    """Binary-gain nDCG over de-duplicated sections.

    Gain stops after ``len(expected)`` relevant sections so alternates cannot push the score
    above 1.0.
    """
    expected_set = set(expected)
    if not expected_set:
        raise ValueError("nDCG is undefined without expected sections")
    relevant = expected_set | set(alternates)
    budget = len(expected_set)
    dcg = 0.0
    for position, key in enumerate(_unique(ranked[:k]), start=1):
        if key in relevant and budget > 0:
            dcg += 1.0 / math.log2(position + 1)
            budget -= 1
    ideal = sum(
        1.0 / math.log2(position + 1) for position in range(1, min(len(expected_set), k) + 1)
    )
    return dcg / ideal if ideal else 0.0


def normalize_text(text: str) -> str:
    """Casefold and collapse whitespace/punctuation variants so fact matching is not brittle."""
    translated = (
        text.replace("’", "'")
        .replace("‘", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("–", "-")
        .replace("—", "-")
        .replace(" ", " ")
    )
    return " ".join(translated.casefold().split())


def facts_present(facts: Sequence[str], text: str) -> list[bool]:
    haystack = normalize_text(text)
    return [normalize_text(fact) in haystack for fact in facts]


def fact_recall(facts: Sequence[str], text: str) -> float:
    if not facts:
        raise ValueError("Fact recall is undefined without expected facts")
    present = facts_present(facts, text)
    return sum(present) / len(present)


def percentile(values: Sequence[float], fraction: float) -> float:
    """Nearest-rank percentile; 0.0 for an empty sample."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]
