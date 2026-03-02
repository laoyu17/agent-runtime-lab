from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

from agent_runtime_lab.app import AgentRuntime
from agent_runtime_lab.trace import TraceStore, run_result_to_events
from agent_runtime_lab.types import TaskSpec


def test_runtime_end_to_end_both_modes_with_trace(tmp_path: Path) -> None:
    trace_dir = tmp_path / "traces"
    store = TraceStore(
        output_dir=str(trace_dir),
        sqlite_path=str(trace_dir / "trace.db"),
    )
    runtime = AgentRuntime(max_steps=3)

    react_task = TaskSpec(
        title="react",
        objective="must return json",
        constraints=["must json"],
    )
    react_result = runtime.run(react_task, mode="react", session_id="react-e2e")
    react_trace = store.append_many(run_result_to_events(react_result))

    assert react_result.success is True
    assert react_result.metrics.steps == 2
    assert react_result.steps[-1].state_update == "summary_completed"
    assert react_trace is not None

    plan_task = TaskSpec(
        title="plan",
        objective="complete subtasks",
        input_payload={"subtasks": ["collect", "execute", "finalize"]},
        constraints=["must json"],
    )
    plan_result = runtime.run(plan_task, mode="plan_execute", session_id="plan-e2e")
    plan_trace = store.append_many(run_result_to_events(plan_result))

    assert plan_result.success is True
    assert plan_result.metrics.steps == 3
    assert plan_trace is not None


def test_cli_commands_integration(tmp_path: Path) -> None:
    task_file = tmp_path / "task.yaml"
    failing_task_file = tmp_path / "task-fail.yaml"
    config_file = tmp_path / "config.yaml"
    out_dir = tmp_path / "reports"
    dataset_file = tmp_path / "dataset.jsonl"
    trace_dir = tmp_path / "trace"

    task_file.write_text(
        "\n".join(
            [
                "title: cli-demo",
                "objective: produce json response",
                "constraints:",
                "  - must json",
            ]
        ),
        encoding="utf-8",
    )
    failing_task_file.write_text(
        "\n".join(
            [
                "title: cli-fail",
                "objective: Fetch https://example.com and return JSON status.",
                "constraints:",
                "  - must json",
                "  - no network",
            ]
        ),
        encoding="utf-8",
    )

    yaml.safe_dump(
        {
            "runtime": {"max_steps": 3, "mode_default": "react"},
            "profiles": {
                "fast": {
                    "runtime": {
                        "max_steps": 2,
                        "mode_default": "plan_execute",
                    }
                }
            },
            "trace": {
                "output_dir": str(trace_dir),
                "sqlite_path": str(trace_dir / "trace.db"),
            },
            "eval": {
                "dataset_path": str(dataset_file),
                "metrics": [
                    "task_success_rate",
                    "tool_call_success_rate",
                    "avg_steps_per_task",
                    "avg_latency_ms",
                    "constraint_retention_rate",
                ],
            },
        },
        config_file.open("w", encoding="utf-8"),
        sort_keys=False,
        allow_unicode=True,
    )

    dataset_rows = [
        {"case_id": "c1", "prompt": "solve task", "constraints": ["must json"]},
        {"case_id": "c2", "prompt": "another task", "constraints": ["must json"]},
    ]
    dataset_file.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in dataset_rows),
        encoding="utf-8",
    )

    list_tools = subprocess.run(
        [sys.executable, "-m", "agent_runtime_lab.cli", "list-tools"],
        check=True,
        capture_output=True,
        text=True,
    )
    tools = json.loads(list_tools.stdout)
    assert any(item["name"] == "calculator" for item in tools)

    list_profiles = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_runtime_lab.cli",
            "list-profiles",
            "--config",
            str(config_file),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    profile_payload = json.loads(list_profiles.stdout)
    assert profile_payload["profiles"] == ["fast"]

    show_config = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_runtime_lab.cli",
            "show-config",
            "--config",
            str(config_file),
            "--profile",
            "fast",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    config_payload = json.loads(show_config.stdout)
    assert config_payload["runtime"]["max_steps"] == 2

    run_task = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_runtime_lab.cli",
            "run-task",
            "--task-file",
            str(task_file),
            "--mode",
            "react",
            "--session-id",
            "cli-session",
            "--resume",
            "--config",
            str(config_file),
            "--profile",
            "fast",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    task_payload = json.loads(run_task.stdout)
    assert task_payload["ok"] is True
    assert task_payload["session_id"] == "cli-session"
    assert Path(task_payload["trace_file"]).exists()

    strict_run = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_runtime_lab.cli",
            "run-task",
            "--task-file",
            str(failing_task_file),
            "--mode",
            "plan_execute",
            "--strict-result",
            "--config",
            str(config_file),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert strict_run.returncode == 1
    strict_payload = json.loads(strict_run.stdout)
    assert strict_payload["ok"] is False
    assert strict_payload["success"] is False

    inspect = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_runtime_lab.cli",
            "inspect-trace",
            "--trace-file",
            str(task_payload["trace_file"]),
            "--session-id",
            "cli-session",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "step_completed" in inspect.stdout

    inspect_json = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_runtime_lab.cli",
            "inspect-trace",
            "--trace-file",
            str(task_payload["trace_file"]),
            "--format",
            "json",
            "--tool",
            "none",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    inspect_payload = json.loads(inspect_json.stdout)
    assert inspect_payload["ok"] is True
    assert inspect_payload["summary"]["steps"] >= 1

    inspect_sqlite = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_runtime_lab.cli",
            "inspect-trace",
            "--sqlite-path",
            str(trace_dir / "trace.db"),
            "--session-id",
            "cli-session",
            "--format",
            "json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    sqlite_payload = json.loads(inspect_sqlite.stdout)
    assert sqlite_payload["ok"] is True
    assert sqlite_payload["count"] >= 1

    benchmark = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_runtime_lab.cli",
            "run-benchmark",
            "--dataset",
            str(dataset_file),
            "--out",
            str(out_dir),
            "--mode",
            "plan_execute",
            "--config",
            str(config_file),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    bench_payload = json.loads(benchmark.stdout)
    assert bench_payload["ok"] is True
    assert Path(bench_payload["markdown"]).exists()
    assert Path(bench_payload["html"]).exists()
