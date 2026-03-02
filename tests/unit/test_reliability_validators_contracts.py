from __future__ import annotations

from time import perf_counter, sleep

from agent_runtime_lab.memory import MemoryManager, ShortTermMemory
from agent_runtime_lab.reliability import (
    ReliabilityManager,
    RepeatCallGuard,
    RetryPolicy,
)
from agent_runtime_lab.types import ExecutionStep, SessionState, TaskSpec, ToolResult
from agent_runtime_lab.validators import (
    ConstraintValidator,
    JSONSchemaValidator,
    KeywordValidator,
    OutputValidator,
    RuleBasedValidator,
    ValidationResult,
)


def _session(session_id: str = "s") -> SessionState:
    task = TaskSpec(title="task", objective="obj", constraints=["must json"])
    return SessionState(
        session_id=session_id,
        mode="react",
        task=task,
        goal=task.objective,
        constraints=list(task.constraints),
    )


def _tool_result(
    call_id: str,
    tool_name: str,
    success: bool,
    output: object,
    error: str | None = None,
) -> ToolResult:
    return ToolResult(
        call_id=call_id,
        tool_name=tool_name,
        success=success,
        output=output,
        error=error,
    )


def test_retry_policy_validation_and_delay_cap() -> None:
    policy = RetryPolicy(
        max_retries=3,
        base_delay_ms=100,
        backoff_factor=2.0,
        max_delay_ms=250,
    )
    assert policy.delay_ms(0) == 100
    assert policy.delay_ms(2) == 250

    for kwargs in (
        {"max_retries": -1},
        {"base_delay_ms": -1},
        {"backoff_factor": 0.5},
        {"max_delay_ms": -1},
        {"timeout_ms": 0},
    ):
        try:
            RetryPolicy(**kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError("expected RetryPolicy validation error")


def test_repeat_guard_and_step_decisions() -> None:
    guard = RepeatCallGuard(window_size=3, threshold=2)
    assert guard.register("calc", {"x": 1}) is False
    assert guard.register("calc", {"x": 1}) is True
    guard.reset()
    assert guard.register("calc", {"x": 1}) is False

    for window_size, threshold in ((0, 2), (3, 1)):
        try:
            RepeatCallGuard(window_size=window_size, threshold=threshold)
        except ValueError:
            pass
        else:
            raise AssertionError("expected RepeatCallGuard validation error")

    manager = ReliabilityManager(max_steps=2, repeat_guard=RepeatCallGuard(threshold=2))
    assert manager.should_stop_for_steps(1).stop is False
    assert manager.should_stop_for_steps(2).reason == "max_steps_exceeded"
    assert manager.should_stop_for_repeat_call("tool", {"k": "v"}).stop is False
    assert manager.should_stop_for_repeat_call("tool", {"k": "v"}).reason == (
        "repeat_call_detected"
    )
    manager.reset_cycle()
    assert manager.should_stop_for_repeat_call("tool", {"k": "v"}).stop is False


def test_reliability_execute_retry_timeout_fallback_and_failures() -> None:
    attempts: list[int] = []

    def flaky() -> dict[str, bool]:
        attempts.append(1)
        if len(attempts) < 2:
            raise RuntimeError("boom")
        return {"ok": True}

    manager = ReliabilityManager(
        retry_policy=RetryPolicy(max_retries=2, base_delay_ms=0),
    )
    outcome = manager.execute(flaky)
    assert outcome.success is True
    assert outcome.value == {"ok": True}
    assert outcome.attempts == 2

    timeout_manager = ReliabilityManager(
        retry_policy=RetryPolicy(max_retries=0, base_delay_ms=0, timeout_ms=5)
    )
    started = perf_counter()
    timeout_outcome = timeout_manager.execute(
        lambda: (sleep(0.2), "late")[1],
        fallback=lambda: {"source": "fallback"},
    )
    elapsed_ms = int((perf_counter() - started) * 1000)
    assert timeout_outcome.success is True
    assert timeout_outcome.used_fallback is True
    assert timeout_outcome.timed_out is True
    assert elapsed_ms < 120

    empty_fallback = timeout_manager.execute(lambda: "", fallback=lambda: "")
    assert empty_fallback.success is False
    assert empty_fallback.error == "fallback_empty_result"

    bad_fallback = timeout_manager.execute(
        lambda: None,
        fallback=lambda: (_ for _ in ()).throw(ValueError("fallback boom")),
    )
    assert bad_fallback.success is False
    assert bad_fallback.error and "fallback_failed" in bad_fallback.error

    fail = manager.execute(
        lambda: (_ for _ in ()).throw(RuntimeError("fail")),
        retry_policy=RetryPolicy(max_retries=1, base_delay_ms=0),
    )
    assert fail.success is False
    assert fail.error == "fail"
    assert fail.attempts == 2


def test_json_schema_validator_keyword_and_constraints() -> None:
    schema = {
        "type": "object",
        "required": ["name", "items", "score"],
        "properties": {
            "name": {"type": "string", "minLength": 2, "pattern": r"^[a-z]+$"},
            "items": {
                "type": "array",
                "minItems": 1,
                "maxItems": 2,
                "items": {"type": "integer", "minimum": 1, "maximum": 9},
            },
            "score": {"type": "number", "minimum": 0.1, "maximum": 1.0},
            "status": {"enum": ["ok", "bad"]},
        },
    }

    validator = JSONSchemaValidator()
    bad_payload = {"name": "A", "items": [0, 2, 3], "score": 2, "status": "unknown"}
    bad_result = validator.validate(bad_payload, schema)
    assert bad_result.passed is False
    assert any("minLength" in item for item in bad_result.errors)
    assert any("maxItems" in item for item in bad_result.errors)
    assert any("minimum" in item for item in bad_result.errors)
    assert any("maximum" in item for item in bad_result.errors)
    assert any("enum" in item for item in bad_result.errors)

    good_payload = {"name": "alpha", "items": [1, 2], "score": 0.9, "status": "ok"}
    good_result = validator.validate(good_payload, schema)
    assert good_result.passed is True

    keyword_result = KeywordValidator().validate(
        "alpha beta",
        required_keywords=["alpha"],
        forbidden_keywords=["gamma"],
    )
    assert keyword_result.passed is True

    constraint_validator = ConstraintValidator()
    must_json_fail = constraint_validator.validate(
        "plain text",
        constraints=["must be json"],
    )
    assert must_json_fail.passed is False
    assert must_json_fail.errors == ["constraint violated: must json"]

    network_fail = constraint_validator.validate(
        '{"x": 1, "url": "https://example.com"}',
        constraints=["禁止联网"],
    )
    assert network_fail.passed is False
    assert network_fail.errors == ["constraint violated: no network"]

    constraint_pass = constraint_validator.validate(
        '{"x": 1}',
        constraints=["必须是 JSON", "no network"],
    )
    assert constraint_pass.passed is True


def test_rule_based_and_output_validator_merge() -> None:
    rule_validator = RuleBasedValidator()

    def tuple_rule(
        payload: object,
        context: dict[str, object],
    ) -> tuple[bool, str | None]:
        expected = context.get("expected")
        ok = isinstance(payload, dict) and payload.get("value") == expected
        return ok, "tuple rule failed"

    def object_rule(payload: object, context: dict[str, object]) -> ValidationResult:
        result = ValidationResult()
        if isinstance(payload, dict) and payload.get("warn"):
            result.add_warning("warned")
        return result

    rule_validator.add_rule(tuple_rule)
    rule_validator.add_rule(object_rule)
    rule_validator.rules.append(lambda payload, context: True)  # type: ignore[arg-type]

    merged = rule_validator.validate(
        {"value": 1, "warn": True},
        context={"expected": 2},
    )
    assert merged.passed is False
    assert "tuple rule failed" in merged.errors
    assert "rule violation" in merged.errors
    assert merged.warnings == ["warned"]

    output_validator = OutputValidator(rule_validator=RuleBasedValidator([tuple_rule]))
    composite = output_validator.validate(
        payload={"value": 1},
        text='{"value": 1}',
        schema={"type": "object", "required": ["value"]},
        required_keywords=["value"],
        forbidden_keywords=["forbidden"],
        constraints=["must json"],
        context={"expected": 1},
    )
    assert composite.passed is True


def test_memory_manager_context_compression_and_session_scope_reset() -> None:
    try:
        MemoryManager(tool_result_keep=0)
    except ValueError:
        pass
    else:
        raise AssertionError("expected tool_result_keep validation error")

    try:
        MemoryManager(summary_max_chars=7)
    except ValueError:
        pass
    else:
        raise AssertionError("expected summary_max_chars validation error")

    memory = ShortTermMemory(window_size=2)
    memory.extend(["a", "b"])
    memory.clear()
    assert memory.recent() == []

    manager = MemoryManager(summary_window=3, tool_result_keep=2, summary_max_chars=120)
    session = _session("s1")
    session.history.extend(
        [
            ExecutionStep(thought_summary="first", observation="1", state_update="ok"),
            ExecutionStep(thought_summary="second", observation="2", state_update="ok"),
            ExecutionStep(thought_summary="third", observation="3", state_update="ok"),
            ExecutionStep(thought_summary="fourth", observation="4", state_update="ok"),
        ]
    )
    session.interim_conclusions.extend(["必须 输出 JSON", "internal note"])
    session.tool_results.extend(
        [
            _tool_result("c1", "search_docs", True, {"hit": 1}),
            _tool_result("c2", "web_fetch_mock", False, None, error="timeout"),
            _tool_result("c3", "calculator", True, {"value": 42}),
        ]
    )

    snapshot = manager.sync(session)
    assert "必须 输出 JSON" in snapshot.retained_constraints
    assert snapshot.compressed_history and snapshot.compressed_history[1] == "..."
    assert len(snapshot.compressed_tool_results) == 2
    assert snapshot.compressed_tool_results[0]["status"] == "error"
    assert session.metadata["compressed_history"] == snapshot.compressed_history

    old_summary = snapshot.summary
    second_snapshot = manager.sync(session)
    assert second_snapshot.summary == old_summary

    recycled = _session("s1")
    recycled.history.append(
        ExecutionStep(
            thought_summary="fresh session item",
            observation="ok",
            state_update="done",
        )
    )
    recycled_snapshot = manager.sync(recycled)
    assert "fresh session item" in recycled_snapshot.summary
    assert "fourth" not in recycled_snapshot.summary

    other = _session("s2")
    other.history.append(
        ExecutionStep(thought_summary="other", observation="ok", state_update="done")
    )
    reset_snapshot = manager.sync(other)
    assert "other" in reset_snapshot.summary
    assert "fourth" not in reset_snapshot.summary
