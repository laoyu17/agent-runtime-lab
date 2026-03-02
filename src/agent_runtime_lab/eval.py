"""Benchmark evaluation runner and dataset helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_runtime_lab.app import AgentRuntime
from agent_runtime_lab.result import EvalMetrics, EvalReport
from agent_runtime_lab.trace import TraceStore, run_result_to_events
from agent_runtime_lab.types import BenchmarkCase, EvalRecord, ExecutionMode, TaskSpec
from agent_runtime_lab.validators import ConstraintValidator, KeywordValidator


@dataclass(slots=True)
class EvalSummary:
    """Post-run analysis used for reporting output."""

    report: EvalReport
    category_metrics: dict[str, EvalMetrics]
    failure_slices: list[dict[str, str]]
    recommendations: list[str]
    expected_violation_stats: dict[str, int]


class EvalRunner:
    """Run a benchmark dataset and aggregate metrics with trace references."""

    def __init__(
        self,
        runtime: AgentRuntime | None = None,
        trace_store: TraceStore | None = None,
        mode_default: ExecutionMode = "react",
    ) -> None:
        self.runtime = runtime or AgentRuntime()
        self.trace_store = trace_store
        self.mode_default = mode_default
        self._keyword_validator = KeywordValidator()
        self._constraint_validator = ConstraintValidator()
        self.last_summary: EvalSummary | None = None

    def run(
        self,
        dataset: list[BenchmarkCase],
        mode: ExecutionMode | None = None,
    ) -> EvalReport:
        summary = self.run_with_summary(dataset, mode=mode)
        self.last_summary = summary
        return summary.report

    def run_with_summary(
        self,
        dataset: list[BenchmarkCase],
        mode: ExecutionMode | None = None,
    ) -> EvalSummary:
        run_mode = mode or self.mode_default
        records: list[EvalRecord] = []
        expected_violation_total = 0
        expected_violation_blocked = 0
        expected_violation_not_blocked = 0

        for case in dataset:
            run_result = self.runtime.run(
                task=benchmark_case_to_task(case),
                mode=run_mode,
            )
            trace_file = self._write_trace(run_result)

            answer_text = run_result.final_answer or ""
            keyword_result = self._keyword_validator.validate(
                answer_text,
                required_keywords=case.expected_keywords,
                forbidden_keywords=case.forbidden_keywords,
            )
            constraint_result = self._constraint_validator.validate(
                answer_text,
                constraints=case.constraints,
            )
            expected_tools_ok, tool_errors = _validate_expected_tools(case, run_result)
            expected_violation = _expects_constraint_violation(case)
            expected_violation_blocked_by_policy = (
                expected_violation and _is_policy_blocked_no_network(run_result)
            )
            if expected_violation:
                expected_violation_total += 1
                if expected_violation_blocked_by_policy:
                    expected_violation_blocked += 1
                else:
                    expected_violation_not_blocked += 1

            runtime_gate = run_result.success or expected_violation_blocked_by_policy

            success = (
                runtime_gate
                and keyword_result.passed
                and constraint_result.passed
                and expected_tools_ok
            )

            note_parts = [
                *keyword_result.errors,
                *constraint_result.errors,
                *tool_errors,
            ]
            if expected_violation:
                if expected_violation_blocked_by_policy:
                    note_parts.append("expected constraint violation blocked by policy")
                else:
                    note_parts.append("expected constraint violation was not blocked")
            if run_result.error and not expected_violation_blocked_by_policy:
                note_parts.insert(0, run_result.error)
            note_parts = _dedupe_keep_order(note_parts)

            records.append(
                EvalRecord(
                    case_id=case.case_id,
                    mode=run_mode,
                    success=success,
                    steps=run_result.metrics.steps,
                    latency_ms=run_result.metrics.total_latency_ms,
                    tool_calls=run_result.metrics.tool_calls,
                    tool_call_success=run_result.metrics.tool_call_success,
                    constraint_retained=(
                        constraint_result.passed
                        and (
                            run_result.metrics.constraint_retained
                            or expected_violation_blocked_by_policy
                        )
                    ),
                    score=_score_case(
                        runtime_success=runtime_gate,
                        keyword_passed=keyword_result.passed,
                        constraint_passed=constraint_result.passed,
                        tools_passed=expected_tools_ok,
                    ),
                    notes="; ".join(note_parts) if note_parts else None,
                    trace_file=trace_file,
                )
            )

        report = EvalReport.from_records(records)
        category_metrics = compute_category_metrics(dataset, records)
        failure_slices = collect_failure_slices(dataset, records)
        recommendations = suggest_improvements(report, category_metrics, failure_slices)
        expected_violation_stats = {
            "total": expected_violation_total,
            "blocked_passed": expected_violation_blocked,
            "not_blocked": expected_violation_not_blocked,
        }
        return EvalSummary(
            report=report,
            category_metrics=category_metrics,
            failure_slices=failure_slices,
            recommendations=recommendations,
            expected_violation_stats=expected_violation_stats,
        )

    def _write_trace(self, run_result: Any) -> str | None:
        if self.trace_store is None:
            return None
        return self.trace_store.append_many(run_result_to_events(run_result))


def load_benchmark_cases(path: str | Path) -> list[BenchmarkCase]:
    """Load benchmark dataset from JSONL into validated BenchmarkCase list."""

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"dataset not found: {file_path}")

    rows: list[BenchmarkCase] = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError(f"dataset row must be object: {text}")
        normalized = _normalize_case_payload(payload)
        rows.append(BenchmarkCase.model_validate(normalized))
    return rows


def benchmark_case_to_task(case: BenchmarkCase) -> TaskSpec:
    """Map benchmark contract to runtime task contract."""

    input_payload: dict[str, Any] = {}
    subtasks = case.metadata.get("subtasks")
    if isinstance(subtasks, list):
        clean_subtasks = [str(item) for item in subtasks if str(item).strip()]
        if clean_subtasks:
            input_payload["subtasks"] = clean_subtasks

    return TaskSpec(
        title=case.case_id,
        objective=case.prompt,
        input_payload=input_payload,
        constraints=list(case.constraints),
        context=list(case.context_docs),
        metadata=case.model_dump(mode="python"),
    )


def compute_category_metrics(
    dataset: list[BenchmarkCase],
    records: list[EvalRecord],
) -> dict[str, EvalMetrics]:
    """Compute metrics by benchmark category (tool/rag/constraint)."""

    categories = {case.case_id: case.category for case in dataset}
    grouped: dict[str, list[EvalRecord]] = {
        "tool": [],
        "rag": [],
        "constraint": [],
    }
    for record in records:
        category_name = categories.get(record.case_id)
        if category_name is None:
            continue
        grouped[category_name].append(record)

    metrics: dict[str, EvalMetrics] = {}
    for bucket, values in grouped.items():
        metrics[bucket] = EvalReport.from_records(values).metrics
    return metrics


def collect_failure_slices(
    dataset: list[BenchmarkCase],
    records: list[EvalRecord],
    limit: int = 5,
) -> list[dict[str, str]]:
    """Collect concise failure samples for report slicing."""

    case_map = {case.case_id: case for case in dataset}
    slices: list[dict[str, str]] = []

    for record in records:
        if record.success:
            continue
        case = case_map.get(record.case_id)
        if case is None:
            continue
        reason = record.notes or "runtime_failed"
        trace_snippet = _extract_trace_snippet(record.trace_file)
        slices.append(
            {
                "case_id": record.case_id,
                "category": case.category,
                "reason": reason,
                "trace_step_id": trace_snippet["step_id"],
                "trace_selected_tool": trace_snippet["selected_tool"],
                "trace_state_update": trace_snippet["state_update"],
            }
        )
        if len(slices) >= limit:
            break

    return slices


def suggest_improvements(
    report: EvalReport,
    category_metrics: dict[str, EvalMetrics],
    failure_slices: list[dict[str, str]],
) -> list[str]:
    """Generate rule-based next-action suggestions from metric gaps."""

    suggestions: list[str] = []
    if report.metrics.task_success_rate < 0.6:
        suggestions.append("提升 Planner/Critic 约束对齐，优先修复低成功率样本。")

    if report.metrics.tool_call_success_rate < 0.9:
        suggestions.append("增强工具重试与 fallback 策略，减少工具调用失败。")

    constraint_metrics = category_metrics.get("constraint")
    if (
        constraint_metrics is not None
        and constraint_metrics.constraint_retention_rate < 0.9
    ):
        suggestions.append("加强约束常驻与输出校验，提升 constraint retention。")

    if failure_slices:
        suggestions.append("针对失败样本建立回归集并固化 golden trace。")

    if not suggestions:
        suggestions.append("当前指标达标，建议扩充高难样本验证稳定性。")
    return suggestions


def _validate_expected_tools(
    case: BenchmarkCase,
    run_result: Any,
) -> tuple[bool, list[str]]:
    if not case.expected_tool_calls:
        return True, []

    selected_tools = {
        step.selected_tool
        for step in run_result.steps
        if step.selected_tool is not None and step.selected_tool != "none"
    }
    missing = [name for name in case.expected_tool_calls if name not in selected_tools]
    if not missing:
        return True, []

    return False, [f"missing expected tool call: {name}" for name in missing]


def _score_case(
    runtime_success: bool,
    keyword_passed: bool,
    constraint_passed: bool,
    tools_passed: bool,
) -> float:
    score = 0.0
    if runtime_success:
        score += 0.4
    if keyword_passed:
        score += 0.2
    if constraint_passed:
        score += 0.2
    if tools_passed:
        score += 0.2
    return round(score, 3)


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _extract_trace_snippet(trace_file: str | None) -> dict[str, str]:
    if not trace_file:
        return {"step_id": "-", "selected_tool": "-", "state_update": "-"}

    rows = TraceStore.read_jsonl(trace_file)
    if not rows:
        return {"step_id": "-", "selected_tool": "-", "state_update": "-"}

    chosen = _pick_trace_row(rows)
    return {
        "step_id": str(chosen.get("step_id") or "-"),
        "selected_tool": str(chosen.get("selected_tool") or "-"),
        "state_update": str(chosen.get("state_update") or "-"),
    }


def _pick_trace_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    for row in rows:
        state_update = str(row.get("state_update") or "").lower()
        if "fail" in state_update or "repeat_call_detected" in state_update:
            return row
    return rows[-1]


def _normalize_case_payload(payload: dict[str, Any]) -> dict[str, Any]:
    case_id = str(payload.get("case_id") or payload.get("id") or "case")
    prompt = str(payload.get("prompt") or payload.get("objective") or "")
    category = str(payload.get("category") or "tool")
    normalized = dict(payload)
    metadata = normalized.get("metadata")
    if isinstance(metadata, dict):
        normalized_metadata: dict[str, Any] = dict(metadata)
    else:
        normalized_metadata = {}

    raw_subtasks = normalized.get("subtasks")
    if isinstance(raw_subtasks, list) and "subtasks" not in normalized_metadata:
        clean_subtasks = [str(item) for item in raw_subtasks if str(item).strip()]
        if clean_subtasks:
            normalized_metadata["subtasks"] = clean_subtasks
    normalized.pop("subtasks", None)

    normalized["case_id"] = case_id
    normalized["prompt"] = prompt
    normalized["category"] = category
    normalized["metadata"] = normalized_metadata
    return normalized


def _expects_constraint_violation(case: BenchmarkCase) -> bool:
    raw = case.metadata.get("expected_constraint_violation")
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "y"}
    return False


def _is_policy_blocked_no_network(run_result: Any) -> bool:
    for step in getattr(run_result, "steps", []):
        state_update = str(getattr(step, "state_update", ""))
        if "policy_blocked_no_network" in state_update:
            return True
    return False


__all__ = [
    "EvalRunner",
    "EvalSummary",
    "benchmark_case_to_task",
    "collect_failure_slices",
    "compute_category_metrics",
    "load_benchmark_cases",
    "suggest_improvements",
]
