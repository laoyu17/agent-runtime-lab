from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_runtime_lab.types import (
    BenchmarkCase,
    EvalRecord,
    ExecutionStep,
    PlanNode,
    SessionState,
    TaskSpec,
    ToolCall,
    ToolResult,
    TraceEvent,
)


def test_task_and_session_state_defaults() -> None:
    task = TaskSpec(title="demo", objective="solve task", constraints=["must-json"])
    session = SessionState(mode="react", task=task, goal="return answer")

    assert task.task_id
    assert session.session_id
    assert session.status == "running"
    assert session.plan == []
    assert session.history == []


def test_tool_contracts_and_trace_event() -> None:
    call = ToolCall(tool_name="calculator", arguments={"expr": "1+1"})
    result = ToolResult(
        call_id=call.call_id,
        tool_name=call.tool_name,
        success=True,
        output={"value": 2},
        latency_ms=5,
    )
    step = ExecutionStep(
        thought_summary="calculate quickly",
        selected_tool="calculator",
        tool_call=call,
        tool_result=result,
        state_update="stored output",
        token_estimate=12,
    )
    trace = TraceEvent(
        session_id="session-1",
        step_id=step.step_id,
        mode="react",
        thought_summary=step.thought_summary,
        selected_tool=step.selected_tool or "none",
        tool_input=call.arguments,
        tool_output=result.output,
        state_update=step.state_update,
        latency_ms=result.latency_ms or 0,
        token_estimate=step.token_estimate or 0,
    )

    assert result.success is True
    assert step.tool_result is not None
    assert trace.selected_tool == "calculator"
    assert trace.tool_output == {"value": 2}


def test_validation_rejects_negative_retries() -> None:
    with pytest.raises(ValidationError):
        PlanNode(title="step", description="invalid retries", retries=-1)


def test_validation_rejects_unknown_task_fields() -> None:
    with pytest.raises(ValidationError):
        TaskSpec(title="demo", objective="x", unexpected_field="boom")


def test_eval_record_and_benchmark_case_contracts() -> None:
    record = EvalRecord(case_id="case-1", mode="plan_execute", success=False)
    case = BenchmarkCase(
        case_id="case-1",
        category="constraint",
        prompt="answer in json",
    )

    assert record.steps == 0
    assert record.constraint_retained is False
    assert case.expected_tool_calls == []
