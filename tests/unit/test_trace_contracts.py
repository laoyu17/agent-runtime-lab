from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from agent_runtime_lab.app import AgentRuntime
from agent_runtime_lab.trace import TraceStore, run_result_to_events
from agent_runtime_lab.types import TaskSpec, TraceEvent


def test_trace_store_append_and_read_jsonl(tmp_path: Path) -> None:
    traces_dir = tmp_path / "traces"
    db_path = traces_dir / "trace.db"
    store = TraceStore(output_dir=str(traces_dir), sqlite_path=str(db_path))

    event = TraceEvent(
        session_id="s1",
        step_id="step-1",
        mode="react",
        thought_summary="think",
        selected_tool="none",
        tool_input=None,
        tool_output={"ok": True},
        state_update="done",
        latency_ms=10,
        token_estimate=5,
    )

    trace_file = store.append(event)
    rows = TraceStore.read_jsonl(trace_file)
    assert len(rows) == 1
    assert rows[0]["session_id"] == "s1"

    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM trace_events").fetchone()[0]
    assert count == 1


def test_trace_store_redacts_sensitive_fields_by_default(tmp_path: Path) -> None:
    traces_dir = tmp_path / "trace"
    db_path = traces_dir / "trace.db"
    store = TraceStore(output_dir=str(traces_dir), sqlite_path=str(db_path))
    event = TraceEvent(
        session_id="s-redact",
        step_id="step-1",
        mode="react",
        thought_summary="api_key: sk-live-123",
        selected_tool="calculator",
        tool_input={
            "api_key": "sk-live-123",
            "nested": {"token": "tok-value"},
        },
        tool_output={
            "cookie": "abc=1",
            "password": "pwd",
            "note": "authorization=abc.def",
        },
        state_update="tool_step_completed",
        latency_ms=3,
        token_estimate=2,
    )

    trace_file = store.append(event, trace_file=traces_dir / "all.jsonl")
    row = TraceStore.read_jsonl(trace_file)[0]
    assert row["thought_summary"] == "api_key: ***REDACTED***"
    assert row["tool_input"]["api_key"] == "***REDACTED***"
    assert row["tool_input"]["nested"]["token"] == "***REDACTED***"
    assert row["tool_output"]["cookie"] == "***REDACTED***"
    assert row["tool_output"]["password"] == "***REDACTED***"
    assert row["tool_output"]["note"] == "authorization=***REDACTED***"

    with sqlite3.connect(db_path) as conn:
        raw_json = conn.execute("SELECT raw_json FROM trace_events").fetchone()[0]
    sqlite_payload = json.loads(raw_json)
    assert sqlite_payload["tool_input"]["api_key"] == "***REDACTED***"
    assert sqlite_payload["tool_output"]["password"] == "***REDACTED***"


def test_trace_store_can_disable_sensitive_redaction(tmp_path: Path) -> None:
    traces_dir = tmp_path / "trace"
    db_path = traces_dir / "trace.db"
    store = TraceStore(
        output_dir=str(traces_dir),
        sqlite_path=str(db_path),
        redact_sensitive=False,
    )
    event = TraceEvent(
        session_id="s-raw",
        step_id="step-1",
        mode="react",
        thought_summary="token: keep-me",
        selected_tool="none",
        tool_input={"token": "keep-me"},
        tool_output={"password": "keep-too"},
        state_update="done",
        latency_ms=0,
        token_estimate=0,
    )

    trace_file = store.append(event, trace_file=traces_dir / "all.jsonl")
    row = TraceStore.read_jsonl(trace_file)[0]
    assert row["thought_summary"] == "token: keep-me"
    assert row["tool_input"]["token"] == "keep-me"
    assert row["tool_output"]["password"] == "keep-too"


def test_trace_store_default_exact_match_avoids_token_estimate_over_redaction(
    tmp_path: Path,
) -> None:
    traces_dir = tmp_path / "trace"
    db_path = traces_dir / "trace.db"
    store = TraceStore(output_dir=str(traces_dir), sqlite_path=str(db_path))
    event = TraceEvent(
        session_id="s-exact",
        step_id="step-1",
        mode="react",
        thought_summary="check",
        selected_tool="none",
        tool_input={"token_estimate": 12, "token": "abc"},
        tool_output={"token_estimate": 34, "token": "xyz"},
        state_update="done",
        latency_ms=0,
        token_estimate=56,
    )

    trace_file = store.append(event, trace_file=traces_dir / "all.jsonl")
    row = TraceStore.read_jsonl(trace_file)[0]
    assert row["tool_input"]["token"] == "***REDACTED***"
    assert row["tool_output"]["token"] == "***REDACTED***"
    assert row["tool_input"]["token_estimate"] == 12
    assert row["tool_output"]["token_estimate"] == 34
    assert row["token_estimate"] == 56


def test_trace_store_contains_match_keeps_legacy_substring_behavior(
    tmp_path: Path,
) -> None:
    traces_dir = tmp_path / "trace"
    db_path = traces_dir / "trace.db"
    store = TraceStore(
        output_dir=str(traces_dir),
        sqlite_path=str(db_path),
        redact_match_mode="contains",
    )
    event = TraceEvent(
        session_id="s-contains",
        step_id="step-1",
        mode="react",
        thought_summary="check",
        selected_tool="none",
        tool_input={"token_estimate": 12},
        tool_output={"token_estimate": 34},
        state_update="done",
        latency_ms=0,
        token_estimate=56,
    )

    trace_file = store.append(event, trace_file=traces_dir / "all.jsonl")
    row = TraceStore.read_jsonl(trace_file)[0]
    assert row["tool_input"]["token_estimate"] == "***REDACTED***"
    assert row["tool_output"]["token_estimate"] == "***REDACTED***"


def test_trace_store_rejects_invalid_redact_match_mode(tmp_path: Path) -> None:
    traces_dir = tmp_path / "trace"
    db_path = traces_dir / "trace.db"
    try:
        TraceStore(
            output_dir=str(traces_dir),
            sqlite_path=str(db_path),
            redact_match_mode="unknown",
        )
    except ValueError as exc:
        assert "redact_match_mode" in str(exc)
    else:
        raise AssertionError("expected ValueError for invalid redact_match_mode")


def test_trace_store_append_many_and_filter(tmp_path: Path) -> None:
    traces_dir = tmp_path / "trace"
    db_path = traces_dir / "events.db"
    store = TraceStore(output_dir=str(traces_dir), sqlite_path=str(db_path))

    events = [
        TraceEvent(
            session_id="s1",
            step_id="a",
            mode="react",
            thought_summary="a",
            selected_tool="none",
            tool_input=None,
            tool_output=None,
            state_update="done",
            latency_ms=0,
            token_estimate=0,
        ),
        TraceEvent(
            session_id="s2",
            step_id="b",
            mode="react",
            thought_summary="b",
            selected_tool="none",
            tool_input=None,
            tool_output=None,
            state_update="done",
            latency_ms=0,
            token_estimate=0,
        ),
    ]

    trace_file = store.append_many(events, trace_file=traces_dir / "all.jsonl")
    assert trace_file is not None

    only_s1 = TraceStore.read_jsonl(trace_file, session_id="s1")
    assert len(only_s1) == 1
    assert only_s1[0]["step_id"] == "a"

    missing = TraceStore.read_jsonl(traces_dir / "missing.jsonl")
    assert missing == []


def test_trace_store_append_many_empty_returns_none(tmp_path: Path) -> None:
    store = TraceStore(
        output_dir=str(tmp_path / "trace"),
        sqlite_path=str(tmp_path / "trace" / "trace.db"),
    )
    assert store.append_many([]) is None


def test_run_result_to_events_from_runtime() -> None:
    runtime = AgentRuntime(max_steps=2)
    task = TaskSpec(title="trace", objective="return json")

    result = runtime.run(task=task, mode="react", session_id="trace-session")
    events = run_result_to_events(result)

    assert len(events) == 2
    first = events[0]
    second = events[1]
    assert first.session_id == "trace-session"
    assert first.mode == "react"
    assert first.selected_tool == "none"
    assert first.state_update == "step_completed"
    assert second.state_update == "summary_completed"
