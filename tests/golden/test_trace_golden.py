from __future__ import annotations

import json
from pathlib import Path

from agent_runtime_lab.app import AgentRuntime
from agent_runtime_lab.trace import run_result_to_events
from agent_runtime_lab.types import TaskSpec


def test_react_trace_matches_golden_snapshot() -> None:
    runtime = AgentRuntime(max_steps=2)
    task = TaskSpec(title="golden", objective="return json payload")
    result = runtime.run(task=task, mode="react", session_id="golden-session")

    events = run_result_to_events(result)
    assert len(events) == 2
    assert events[1].state_update == "summary_completed"

    payload = events[0].model_dump(mode="json")
    payload["step_id"] = "<dynamic-step-id>"
    payload["timestamp"] = "<dynamic-timestamp>"
    payload["latency_ms"] = "<dynamic-latency-ms>"
    payload["token_estimate"] = "<dynamic-token-estimate>"

    expected_path = Path("tests/golden/expected_react_trace_event.json")
    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    assert payload == expected
