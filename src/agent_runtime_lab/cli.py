"""CLI entrypoint for Agent Runtime Lab."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

import yaml

from agent_runtime_lab.app import AgentRuntime
from agent_runtime_lab.config import AppConfig, list_profiles, load_config
from agent_runtime_lab.eval import EvalRunner, load_benchmark_cases
from agent_runtime_lab.memory import MemoryManager
from agent_runtime_lab.reliability import ReliabilityManager, RetryPolicy
from agent_runtime_lab.reporting import export_report
from agent_runtime_lab.retrieval import Retriever
from agent_runtime_lab.tools import ToolRegistry, create_builtin_tools
from agent_runtime_lab.trace import TraceStore, run_result_to_events
from agent_runtime_lab.types import ExecutionMode, TaskSpec

_DEFAULT_BENCHMARK_THRESHOLDS = {
    "task_success_rate": 0.60,
    "tool_call_success_rate": 0.90,
    "constraint_retention_rate": 0.90,
}


def _as_str_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]


def _load_yaml_mapping(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"yaml root must be mapping: {file_path}")
    return data


def _load_task(path: str | Path) -> TaskSpec:
    raw = _load_yaml_mapping(path)
    input_payload = raw.get("input_payload")
    metadata = raw.get("metadata")
    return TaskSpec(
        title=str(raw.get("title", "task")),
        objective=str(raw.get("objective") or raw.get("prompt") or ""),
        input_payload=input_payload if isinstance(input_payload, dict) else {},
        constraints=_as_str_list(raw.get("constraints")),
        context=_as_str_list(raw.get("context")),
        metadata=metadata if isinstance(metadata, dict) else {},
    )


def _build_runtime(config: AppConfig) -> AgentRuntime:
    registry = ToolRegistry()
    tools = create_builtin_tools()
    for tool in tools:
        tool.spec.timeout_ms = config.tool.timeout_ms
        tool.spec.retry = config.tool.retry
    registry.register_many(tools)

    reliability_manager = ReliabilityManager(
        max_steps=config.runtime.max_steps,
        retry_policy=RetryPolicy(
            max_retries=config.tool.retry,
            timeout_ms=config.tool.timeout_ms,
        ),
    )
    memory_manager = MemoryManager(summary_window=config.memory.summary_window)
    retriever = Retriever(
        chunk_size=config.retrieval.chunk_size,
        top_k=config.retrieval.top_k,
    )
    return AgentRuntime(
        max_steps=config.runtime.max_steps,
        tool_registry=registry,
        memory_manager=memory_manager,
        retriever=retriever,
        reliability_manager=reliability_manager,
    )


def _evaluate_thresholds(
    metrics: dict[str, Any],
    thresholds: dict[str, float],
) -> tuple[bool, dict[str, dict[str, Any]]]:
    results: dict[str, dict[str, Any]] = {}
    all_passed = True

    for key, threshold in thresholds.items():
        raw_value = metrics.get(key, 0.0)
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            value = 0.0
        passed = value >= threshold
        all_passed = all_passed and passed
        results[key] = {
            "value": round(value, 6),
            "threshold": threshold,
            "passed": passed,
        }

    return all_passed, results


def _cmd_run_task(args: argparse.Namespace) -> int:
    config = load_config(args.config, profile=args.profile)
    mode: ExecutionMode = args.mode or config.runtime.mode_default
    task = _load_task(args.task_file)
    runtime = _build_runtime(config)
    result = runtime.run(
        task=task,
        mode=mode,
        session_id=args.session_id,
        resume=bool(args.resume),
    )

    store = TraceStore(
        config.trace.output_dir,
        config.trace.sqlite_path,
        redact_sensitive=config.trace.redact_sensitive,
        redact_keys=list(config.trace.redact_keys),
    )
    trace_file = store.append_many(run_result_to_events(result))
    strict_fail = bool(args.strict_result) and not result.success

    payload = {
        "ok": not strict_fail,
        "session_id": result.session_id,
        "mode": result.mode,
        "success": result.success,
        "steps": result.metrics.steps,
        "trace_file": trace_file,
        "error": result.error,
        "strict_result": bool(args.strict_result),
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 1 if strict_fail else 0


def _cmd_run_benchmark(args: argparse.Namespace) -> int:
    config = load_config(args.config, profile=args.profile)
    mode: ExecutionMode = args.mode or config.runtime.mode_default
    dataset_path = args.dataset or config.eval.dataset_path

    cases = load_benchmark_cases(dataset_path)
    runtime = _build_runtime(config)
    trace_store = TraceStore(
        config.trace.output_dir,
        config.trace.sqlite_path,
        redact_sensitive=config.trace.redact_sensitive,
        redact_keys=list(config.trace.redact_keys),
    )
    runner = EvalRunner(runtime=runtime, trace_store=trace_store, mode_default=mode)
    summary = runner.run_with_summary(cases, mode=mode)

    artifacts = export_report(
        summary,
        mode=mode,
        out_dir=args.out,
    )
    metrics = summary.report.metrics.model_dump(mode="python")
    thresholds_passed, threshold_results = _evaluate_thresholds(
        metrics,
        _DEFAULT_BENCHMARK_THRESHOLDS,
    )
    strict_fail = bool(args.strict_thresholds) and not thresholds_passed

    payload = {
        "ok": not strict_fail,
        "dataset_size": summary.report.dataset_size,
        "mode": mode,
        "markdown": artifacts.markdown_path,
        "html": artifacts.html_path,
        "metrics": metrics,
        "thresholds": threshold_results,
        "strict_thresholds": bool(args.strict_thresholds),
        "failures": len(summary.failure_slices),
        "expected_violation": summary.expected_violation_stats,
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 1 if strict_fail else 0


def _cmd_inspect_trace(args: argparse.Namespace) -> int:
    if not args.trace_file and not args.sqlite_path:
        raise ValueError("inspect-trace requires --trace-file or --sqlite-path")

    if args.sqlite_path:
        rows = _read_trace_from_sqlite(
            args.sqlite_path,
            session_id=args.session_id,
            tool=args.tool,
            limit=args.limit,
        )
    else:
        rows = TraceStore.read_jsonl(args.trace_file, session_id=args.session_id)
        rows = _filter_trace_rows(rows, tool=args.tool, limit=args.limit)

    summary = _build_trace_summary(rows)

    if args.format == "json":
        print(
            json.dumps(
                {
                    "ok": True,
                    "count": len(rows),
                    "summary": summary,
                    "rows": rows,
                },
                ensure_ascii=False,
            )
        )
        return 0

    for row in rows:
        print(
            f"{row.get('step_id')} | tool={row.get('selected_tool')} "
            f"| latency={row.get('latency_ms')}ms | state={row.get('state_update')}"
        )
    print(
        json.dumps(
            {"ok": True, "count": len(rows), "summary": summary},
            ensure_ascii=False,
        )
    )
    return 0


def _read_trace_from_sqlite(
    sqlite_path: str,
    *,
    session_id: str | None,
    tool: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    path = Path(sqlite_path)
    if not path.exists():
        raise FileNotFoundError(f"sqlite trace not found: {path}")

    sql = "SELECT raw_json FROM trace_events"
    params: list[str] = []
    clauses: list[str] = []

    if session_id:
        clauses.append("session_id = ?")
        params.append(session_id)
    if tool:
        clauses.append("selected_tool = ?")
        params.append(tool)

    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY timestamp"
    if limit > 0:
        sql += " LIMIT ?"
        params.append(str(limit))

    rows: list[dict[str, Any]] = []
    with sqlite3.connect(path) as conn:
        cursor = conn.execute(sql, params)
        for item in cursor.fetchall():
            rows.append(json.loads(item[0]))
    return rows


def _filter_trace_rows(
    rows: list[dict[str, Any]],
    *,
    tool: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    filtered = [
        row for row in rows if tool is None or str(row.get("selected_tool")) == tool
    ]
    if limit > 0:
        return filtered[:limit]
    return filtered


def _build_trace_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_latency = 0
    tool_counts: dict[str, int] = {}
    failed_steps = 0
    for row in rows:
        total_latency += int(row.get("latency_ms") or 0)
        selected_tool = str(row.get("selected_tool") or "none")
        tool_counts[selected_tool] = tool_counts.get(selected_tool, 0) + 1
        state_update = str(row.get("state_update") or "")
        if "fail" in state_update.lower():
            failed_steps += 1

    return {
        "steps": len(rows),
        "total_latency_ms": total_latency,
        "failed_steps": failed_steps,
        "tool_counts": tool_counts,
    }


def _cmd_list_tools(args: argparse.Namespace) -> int:
    _ = args
    registry = ToolRegistry()
    registry.register_many(create_builtin_tools())
    payload = [
        {
            "name": spec.name,
            "kind": spec.kind,
            "description": spec.description,
        }
        for spec in registry.list_specs()
    ]
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def _cmd_list_profiles(args: argparse.Namespace) -> int:
    names = list_profiles(args.config)
    print(json.dumps({"ok": True, "profiles": names}, ensure_ascii=False))
    return 0


def _cmd_show_config(args: argparse.Namespace) -> int:
    config = load_config(args.config, profile=args.profile)
    print(json.dumps(config.model_dump(mode="python"), ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-runtime-lab")
    parser.description = "Agent Runtime Lab CLI"
    sub = parser.add_subparsers(dest="command", required=True)

    run_task = sub.add_parser("run-task")
    run_task.add_argument("--task-file", required=True)
    run_task.add_argument("--mode", choices=["react", "plan_execute"])
    run_task.add_argument("--session-id")
    run_task.add_argument("--resume", action="store_true")
    run_task.add_argument("--strict-result", action="store_true")
    run_task.add_argument("--profile")
    run_task.add_argument("--config", default="configs/default.yaml")
    run_task.set_defaults(func=_cmd_run_task)

    run_benchmark = sub.add_parser("run-benchmark")
    run_benchmark.add_argument("--dataset")
    run_benchmark.add_argument("--out", default="outputs/reports")
    run_benchmark.add_argument("--mode", choices=["react", "plan_execute"])
    run_benchmark.add_argument("--strict-thresholds", action="store_true")
    run_benchmark.add_argument("--profile")
    run_benchmark.add_argument("--config", default="configs/default.yaml")
    run_benchmark.set_defaults(func=_cmd_run_benchmark)

    inspect_trace = sub.add_parser("inspect-trace")
    inspect_trace.add_argument("--trace-file")
    inspect_trace.add_argument("--sqlite-path")
    inspect_trace.add_argument("--session-id")
    inspect_trace.add_argument("--tool")
    inspect_trace.add_argument("--limit", type=int, default=0)
    inspect_trace.add_argument("--format", choices=["text", "json"], default="text")
    inspect_trace.set_defaults(func=_cmd_inspect_trace)

    list_tools = sub.add_parser("list-tools")
    list_tools.set_defaults(func=_cmd_list_tools)

    list_profile_cmd = sub.add_parser("list-profiles")
    list_profile_cmd.add_argument("--config", default="configs/default.yaml")
    list_profile_cmd.set_defaults(func=_cmd_list_profiles)

    show_config = sub.add_parser("show-config")
    show_config.add_argument("--config", default="configs/default.yaml")
    show_config.add_argument("--profile")
    show_config.set_defaults(func=_cmd_show_config)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        code = args.func(args)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1) from exc
    raise SystemExit(code)


if __name__ == "__main__":
    main()
