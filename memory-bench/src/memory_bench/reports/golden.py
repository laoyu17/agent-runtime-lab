from __future__ import annotations

from collections import defaultdict

from memory_bench.types import EvalResult


def infer_category_from_sample_id(sample_id: str) -> str:
    if sample_id.startswith("preference_memory_"):
        return "preference_memory"
    if sample_id.startswith("constraint_memory_"):
        return "constraint_memory"
    if sample_id.startswith("slot_memory_"):
        return "slot_memory"
    if sample_id.startswith("distractor_memory_"):
        return "distractor_memory"
    return "unknown"


def select_golden_subset(
    results: list[EvalResult],
    *,
    per_category: int,
) -> list[EvalResult]:
    grouped: dict[str, list[EvalResult]] = defaultdict(list)
    for result in sorted(results, key=lambda item: item.sample_id):
        grouped[infer_category_from_sample_id(result.sample_id)].append(result)

    selected: list[EvalResult] = []
    for category in sorted(grouped):
        selected.extend(grouped[category][:per_category])
    return selected


def drift_warnings(
    current: dict[str, float],
    baseline: dict[str, float] | None,
    *,
    threshold: float,
) -> list[str]:
    if not baseline:
        return []

    warnings: list[str] = []
    for key, current_value in current.items():
        if key not in baseline:
            continue
        delta = current_value - baseline[key]
        if abs(delta) > threshold:
            warnings.append(
                f"{key} drift={delta:+.4f} exceeds threshold ±{threshold:.4f}"
            )
    return warnings
