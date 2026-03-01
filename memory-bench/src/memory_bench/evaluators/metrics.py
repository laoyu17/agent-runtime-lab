from __future__ import annotations

import math
from collections import defaultdict

from memory_bench.types import EvalResult, MetricsSummary


def summarize_results(
    results: list[EvalResult],
    constraint_counts: dict[str, int] | None = None,
) -> MetricsSummary:
    if not results:
        return MetricsSummary(
            memory_recall_rate=0.0,
            constraint_retention_rate=1.0,
            contradiction_rate=0.0,
            avg_latency_ms=0.0,
            p50_latency_ms=0.0,
            p95_latency_ms=0.0,
        )

    memory_recall_rate = sum(result.memory_hits for result in results) / len(results)
    constraint_retention_rate = _constraint_retention_rate(results, constraint_counts or {})
    contradiction_rate = sum(result.contradictions for result in results) / len(results)

    latencies = [result.latency_ms for result in results]
    avg_latency = sum(latencies) / len(latencies)

    return MetricsSummary(
        memory_recall_rate=memory_recall_rate,
        constraint_retention_rate=constraint_retention_rate,
        contradiction_rate=contradiction_rate,
        avg_latency_ms=avg_latency,
        p50_latency_ms=percentile(latencies, 50),
        p95_latency_ms=percentile(latencies, 95),
    )


def summarize_by_category(
    results: list[EvalResult],
    sample_to_category: dict[str, str],
    constraint_counts: dict[str, int] | None = None,
) -> dict[str, MetricsSummary]:
    grouped: dict[str, list[EvalResult]] = defaultdict(list)
    for result in results:
        category = sample_to_category.get(result.sample_id, "unknown")
        grouped[category].append(result)

    counts = constraint_counts or {}
    output: dict[str, MetricsSummary] = {}
    for category, category_results in grouped.items():
        category_counts = {
            sample_id: count
            for sample_id, count in counts.items()
            if sample_to_category.get(sample_id, "unknown") == category
        }
        output[category] = summarize_results(category_results, category_counts)
    return output


def percentile(values: list[float], p: int) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    rank = (p / 100) * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]

    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _constraint_retention_rate(
    results: list[EvalResult],
    constraint_counts: dict[str, int],
) -> float:
    constrained = [
        result for result in results if constraint_counts.get(result.sample_id, 0) > 0
    ]
    if not constrained:
        return 1.0

    satisfied = sum(1 for result in constrained if result.constraint_violations == 0)
    return satisfied / len(constrained)
