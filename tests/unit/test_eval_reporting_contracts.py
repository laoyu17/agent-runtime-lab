from __future__ import annotations

import json
from pathlib import Path

from agent_runtime_lab.app import AgentRuntime
from agent_runtime_lab.eval import EvalRunner, load_benchmark_cases
from agent_runtime_lab.reporting import export_report, render_html, render_markdown
from agent_runtime_lab.trace import TraceStore
from agent_runtime_lab.types import BenchmarkCase


def _case(
    case_id: str,
    category: str,
    *,
    prompt: str | None = None,
    constraints: list[str] | None = None,
    expected_keywords: list[str] | None = None,
    forbidden_keywords: list[str] | None = None,
    expected_tool_calls: list[str] | None = None,
    metadata: dict[str, object] | None = None,
) -> BenchmarkCase:
    return BenchmarkCase(
        case_id=case_id,
        category=category,
        prompt=prompt or f"prompt-{case_id}",
        constraints=constraints or ["must json"],
        expected_keywords=expected_keywords or ["status"],
        forbidden_keywords=forbidden_keywords or [],
        expected_tool_calls=expected_tool_calls or [],
        metadata=metadata or {},
    )


def test_load_benchmark_cases_reads_jsonl(tmp_path: Path) -> None:
    dataset = tmp_path / "cases.jsonl"
    rows = [
        {
            "case_id": "tool-1",
            "category": "tool",
            "prompt": "demo",
            "constraints": ["must json"],
        },
        {
            "case_id": "rag-1",
            "category": "rag",
            "prompt": "demo2",
            "constraints": ["must json"],
            "context_docs": ["ctx"],
        },
    ]
    dataset.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

    cases = load_benchmark_cases(dataset)
    assert len(cases) == 2
    assert cases[0].case_id == "tool-1"
    assert cases[1].category == "rag"

    try:
        load_benchmark_cases(tmp_path / "missing.jsonl")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("expected FileNotFoundError")


def test_eval_runner_summary_contains_failures_and_recommendations() -> None:
    dataset = [
        _case("tool-1", "tool"),
        _case("rag-1", "rag", forbidden_keywords=["status"]),
        _case("constraint-1", "constraint", expected_tool_calls=["calculator"]),
    ]

    runner = EvalRunner(runtime=AgentRuntime(max_steps=3))
    summary = runner.run_with_summary(dataset, mode="react")

    assert summary.report.dataset_size == 3
    assert len(summary.report.records) == 3
    assert any(record.success is False for record in summary.report.records)
    assert set(summary.category_metrics) == {"tool", "rag", "constraint"}
    assert summary.failure_slices
    first_failure = summary.failure_slices[0]
    assert "trace_step_id" in first_failure
    assert "trace_selected_tool" in first_failure
    assert "trace_state_update" in first_failure
    assert summary.recommendations


def test_eval_runner_run_sets_last_summary_and_trace_file(tmp_path: Path) -> None:
    trace_dir = tmp_path / "traces"
    trace_store = TraceStore(str(trace_dir), str(trace_dir / "trace.db"))
    runner = EvalRunner(
        runtime=AgentRuntime(max_steps=3),
        trace_store=trace_store,
        mode_default="plan_execute",
    )
    dataset = [
        _case(
            "tool-1",
            "tool",
        )
    ]

    report = runner.run(dataset)
    assert report.dataset_size == 1
    assert runner.last_summary is not None
    trace_file = report.records[0].trace_file
    assert trace_file is not None
    assert Path(trace_file).exists()


def test_eval_runner_counts_expected_constraint_violation_as_pass() -> None:
    dataset = [
        _case(
            "constraint-expected",
            "constraint",
            prompt="Fetch https://example.com but keep json output.",
            constraints=["must json", "no network"],
            expected_tool_calls=["web_fetch_mock"],
            metadata={"expected_constraint_violation": True},
        )
    ]

    summary = EvalRunner(runtime=AgentRuntime(max_steps=3)).run_with_summary(
        dataset,
        mode="plan_execute",
    )
    record = summary.report.records[0]

    assert record.success is True
    assert record.constraint_retained is True
    assert record.notes is not None
    assert "expected constraint violation blocked by policy" in record.notes
    assert summary.expected_violation_stats == {
        "total": 1,
        "blocked_passed": 1,
        "not_blocked": 0,
    }


def test_reporting_render_and_export(tmp_path: Path) -> None:
    dataset = [
        _case("tool-1", "tool"),
        _case("rag-1", "rag", forbidden_keywords=["status"]),
    ]
    summary = EvalRunner(runtime=AgentRuntime(max_steps=3)).run_with_summary(dataset)

    markdown = render_markdown(summary, mode="react")
    assert "# Benchmark Report" in markdown
    assert "## Expected Constraint Violations" in markdown
    assert "## Failure Slices" in markdown

    html = render_html(markdown)
    assert "<html>" in html
    assert "Benchmark Report" in html

    artifacts = export_report(
        summary,
        mode="react",
        out_dir=tmp_path / "reports",
        file_stem="demo",
    )
    assert Path(artifacts.markdown_path).exists()
    assert Path(artifacts.html_path).exists()
    assert summary.report.markdown_report == artifacts.markdown_path
    assert summary.report.html_report == artifacts.html_path
