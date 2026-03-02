"""Run and evaluation result contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from statistics import fmean
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent_runtime_lab.types import (
    EvalRecord,
    ExecutionMode,
    ExecutionStep,
    SessionState,
)


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


class ResultBase(BaseModel):
    """Shared strict result model config."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class RunMetrics(ResultBase):
    """Aggregated runtime counters for a single run."""

    steps: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    tool_call_success: int = Field(default=0, ge=0)
    total_latency_ms: int = Field(default=0, ge=0)
    token_estimate: int = Field(default=0, ge=0)
    constraint_retained: bool = False


class RunResult(ResultBase):
    """Return payload for AgentRuntime.run."""

    session_id: str
    mode: ExecutionMode
    success: bool
    final_answer: str | None = None
    final_state: SessionState | None = None
    steps: list[ExecutionStep] = Field(default_factory=list)
    metrics: RunMetrics = Field(default_factory=RunMetrics)
    trace_file: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=_utc_now)
    finished_at: datetime = Field(default_factory=_utc_now)

    @property
    def duration_ms(self) -> int:
        """Wall-clock run duration in milliseconds."""

        delta = self.finished_at - self.started_at
        return max(0, int(delta.total_seconds() * 1000))


class EvalMetrics(ResultBase):
    """Aggregated benchmark metrics."""

    task_success_rate: float = 0.0
    tool_call_success_rate: float = 0.0
    avg_steps_per_task: float = 0.0
    avg_latency_ms: float = 0.0
    constraint_retention_rate: float = 0.0


class EvalReport(ResultBase):
    """Return payload for EvalRunner.run."""

    generated_at: datetime = Field(default_factory=_utc_now)
    dataset_size: int = Field(default=0, ge=0)
    records: list[EvalRecord] = Field(default_factory=list)
    metrics: EvalMetrics = Field(default_factory=EvalMetrics)
    markdown_report: str | None = None
    html_report: str | None = None

    @classmethod
    def from_records(cls, records: list[EvalRecord]) -> EvalReport:
        """Build report with computed aggregate metrics from records."""

        dataset_size = len(records)
        if dataset_size == 0:
            return cls(dataset_size=0, records=[], metrics=EvalMetrics())

        task_success_rate = fmean(1.0 if r.success else 0.0 for r in records)
        total_tool_calls = sum(r.tool_calls for r in records)
        total_tool_success = sum(r.tool_call_success for r in records)
        tool_call_success_rate = (
            total_tool_success / total_tool_calls if total_tool_calls > 0 else 0.0
        )
        avg_steps = fmean(float(r.steps) for r in records)
        avg_latency = fmean(float(r.latency_ms) for r in records)
        constraint_retention = fmean(
            1.0 if r.constraint_retained else 0.0 for r in records
        )

        metrics = EvalMetrics(
            task_success_rate=task_success_rate,
            tool_call_success_rate=tool_call_success_rate,
            avg_steps_per_task=avg_steps,
            avg_latency_ms=avg_latency,
            constraint_retention_rate=constraint_retention,
        )
        return cls(dataset_size=dataset_size, records=records, metrics=metrics)


__all__ = ["EvalMetrics", "EvalReport", "RunMetrics", "RunResult"]
