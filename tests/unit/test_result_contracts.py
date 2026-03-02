from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agent_runtime_lab.result import EvalReport, RunResult
from agent_runtime_lab.types import EvalRecord


def test_run_result_duration_ms_positive() -> None:
    started_at = datetime(2026, 1, 1, tzinfo=UTC)
    finished_at = started_at + timedelta(milliseconds=150)

    result = RunResult(
        session_id="s1",
        mode="react",
        success=True,
        started_at=started_at,
        finished_at=finished_at,
    )

    assert result.duration_ms == 150


def test_run_result_duration_ms_floors_to_zero() -> None:
    started_at = datetime(2026, 1, 1, tzinfo=UTC)
    finished_at = started_at - timedelta(milliseconds=20)

    result = RunResult(
        session_id="s1",
        mode="react",
        success=False,
        started_at=started_at,
        finished_at=finished_at,
    )

    assert result.duration_ms == 0


def test_eval_report_from_empty_records() -> None:
    report = EvalReport.from_records([])

    assert report.dataset_size == 0
    assert report.metrics.task_success_rate == 0.0
    assert report.records == []


def test_eval_report_aggregate_metrics() -> None:
    records = [
        EvalRecord(
            case_id="case-1",
            mode="react",
            success=True,
            steps=3,
            latency_ms=120,
            tool_calls=2,
            tool_call_success=2,
            constraint_retained=True,
        ),
        EvalRecord(
            case_id="case-2",
            mode="plan_execute",
            success=False,
            steps=5,
            latency_ms=180,
            tool_calls=2,
            tool_call_success=1,
            constraint_retained=False,
        ),
    ]

    report = EvalReport.from_records(records)

    assert report.dataset_size == 2
    assert report.metrics.task_success_rate == pytest.approx(0.5)
    assert report.metrics.tool_call_success_rate == pytest.approx(0.75)
    assert report.metrics.avg_steps_per_task == pytest.approx(4.0)
    assert report.metrics.avg_latency_ms == pytest.approx(150.0)
    assert report.metrics.constraint_retention_rate == pytest.approx(0.5)
