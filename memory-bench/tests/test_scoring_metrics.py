from __future__ import annotations

from memory_bench.evaluators.metrics import percentile, summarize_results
from memory_bench.evaluators.scoring import (
    constraint_violations,
    contradiction_count,
    memory_recall,
)
from memory_bench.types import EvalResult


def test_memory_recall_and_contradiction() -> None:
    answer = "traveler_name=Avery destination=Kyoto"
    expected = ["traveler_name=Avery", "destination=Kyoto", "travel_date=2026-04-18"]

    assert memory_recall(answer, expected) == 2 / 3
    assert contradiction_count(answer, expected) == 0
    assert contradiction_count("traveler_name=Jordan", expected) == 1


def test_constraint_violations_json_and_forbidden_word() -> None:
    constraints = ["format=json_only", "forbidden_word=sorry", "max_items=2"]

    assert constraint_violations('{"a":1,"b":2}', constraints) == 0
    assert constraint_violations("sorry", constraints) >= 1
    assert constraint_violations('{"a":1,"b":2,"c":3}', constraints) >= 1


def test_metrics_summary_and_percentiles() -> None:
    results = [
        EvalResult(
            run_id="r1",
            sample_id="constraint_memory_001",
            strategy="full_context",
            adapter="mock",
            final_answer="{}",
            memory_hits=1.0,
            constraint_violations=0,
            contradictions=0,
            latency_ms=10,
        ),
        EvalResult(
            run_id="r1",
            sample_id="preference_memory_001",
            strategy="full_context",
            adapter="mock",
            final_answer="{}",
            memory_hits=0.5,
            constraint_violations=0,
            contradictions=1,
            latency_ms=20,
        ),
    ]

    summary = summarize_results(results, {"constraint_memory_001": 1, "preference_memory_001": 0})
    assert summary.memory_recall_rate == 0.75
    assert summary.constraint_retention_rate == 1.0
    assert summary.contradiction_rate == 0.5
    assert summary.avg_latency_ms == 15
    assert percentile([1, 2, 3, 4], 50) == 2.5
