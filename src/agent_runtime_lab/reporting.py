"""Benchmark report rendering and export helpers."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path

from agent_runtime_lab.eval import EvalSummary
from agent_runtime_lab.result import EvalMetrics
from agent_runtime_lab.types import ExecutionMode


@dataclass(slots=True)
class ReportArtifacts:
    """Generated benchmark report artifact paths."""

    markdown_path: str
    html_path: str


def render_markdown(summary: EvalSummary, mode: ExecutionMode) -> str:
    """Render benchmark summary with category and failure sections."""

    report = summary.report
    metrics = report.metrics
    expected_violation_stats = summary.expected_violation_stats
    lines = [
        "# Benchmark Report",
        "",
        f"- Mode: `{mode}`",
        f"- Dataset size: `{report.dataset_size}`",
        "",
        "## Overall Metrics",
        "",
        f"- task_success_rate: `{metrics.task_success_rate:.3f}`",
        f"- tool_call_success_rate: `{metrics.tool_call_success_rate:.3f}`",
        f"- avg_steps_per_task: `{metrics.avg_steps_per_task:.3f}`",
        f"- avg_latency_ms: `{metrics.avg_latency_ms:.3f}`",
        f"- constraint_retention_rate: `{metrics.constraint_retention_rate:.3f}`",
        "",
        "## Expected Constraint Violations",
        "",
        (
            "- expected_violation_total: "
            f"`{expected_violation_stats.get('total', 0)}`"
        ),
        (
            "- expected_violation_blocked_passed: "
            f"`{expected_violation_stats.get('blocked_passed', 0)}`"
        ),
        (
            "- expected_violation_not_blocked: "
            f"`{expected_violation_stats.get('not_blocked', 0)}`"
        ),
        "",
        "## Threshold Check",
        "",
        f"- task_success_rate >= 0.60: `{_status(metrics.task_success_rate >= 0.60)}`",
        (
            "- tool_call_success_rate >= 0.90: "
            f"`{_status(metrics.tool_call_success_rate >= 0.90)}`"
        ),
        (
            "- constraint_retention_rate >= 0.90: "
            f"`{_status(metrics.constraint_retention_rate >= 0.90)}`"
        ),
        "",
        "## Category Metrics",
        "",
        (
            "| category | task_success_rate | tool_call_success_rate "
            "| avg_steps | avg_latency_ms | constraint_retention |"
        ),
        "|---|---:|---:|---:|---:|---:|",
    ]

    for category in ("tool", "rag", "constraint"):
        category_metrics = summary.category_metrics.get(category, EvalMetrics())
        lines.append(
            "| "
            f"{category} | "
            f"{category_metrics.task_success_rate:.3f} | "
            f"{category_metrics.tool_call_success_rate:.3f} | "
            f"{category_metrics.avg_steps_per_task:.3f} | "
            f"{category_metrics.avg_latency_ms:.3f} | "
            f"{category_metrics.constraint_retention_rate:.3f} |"
        )

    lines.extend(["", "## Failure Slices", ""])
    if summary.failure_slices:
        lines.extend(
            [
                (
                    "| case_id | category | reason | trace_step_id | "
                    "trace_selected_tool | trace_state_update |"
                ),
                "|---|---|---|---|---|---|",
            ]
        )
        for item in summary.failure_slices:
            reason = item["reason"].replace("|", "\\|")
            lines.append(
                f"| {item['case_id']} | {item['category']} | {reason} "
                f"| {item.get('trace_step_id', '-')} "
                f"| {item.get('trace_selected_tool', '-')} "
                f"| {item.get('trace_state_update', '-')} |"
            )
    else:
        lines.append("- No failed cases in this run.")

    lines.extend(["", "## Improvement Suggestions", ""])
    for suggestion in summary.recommendations:
        lines.append(f"- {suggestion}")

    lines.extend(["", "## Records", ""])
    lines.extend(
        [
            "| case_id | success | steps | latency_ms | score | trace_file |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for record in report.records:
        trace_file = record.trace_file or "-"
        score = f"{record.score:.3f}" if record.score is not None else "-"
        lines.append(
            f"| {record.case_id} | {record.success} | {record.steps} "
            f"| {record.latency_ms} | {score} | {trace_file} |"
        )

    return "\n".join(lines)


def render_html(markdown: str) -> str:
    """Render a lightweight HTML view for markdown content."""

    body = escape(markdown)
    return (
        '<html><head><meta charset="utf-8"><style>'
        "body{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;"
        "background:#0b1020;color:#e6edf3;padding:24px;}"
        "pre{white-space:pre-wrap;line-height:1.45;}"
        "</style></head><body><pre>"
        f"{body}"
        "</pre></body></html>"
    )


def export_report(
    summary: EvalSummary,
    *,
    mode: ExecutionMode,
    out_dir: str | Path,
    file_stem: str = "benchmark_report",
) -> ReportArtifacts:
    """Write markdown/html reports to output directory."""

    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)

    markdown = render_markdown(summary, mode)
    html = render_html(markdown)

    markdown_path = output / f"{file_stem}.md"
    html_path = output / f"{file_stem}.html"
    markdown_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")

    summary.report.markdown_report = str(markdown_path)
    summary.report.html_report = str(html_path)
    return ReportArtifacts(
        markdown_path=str(markdown_path),
        html_path=str(html_path),
    )


def _status(passed: bool) -> str:
    return "pass" if passed else "fail"


__all__ = [
    "ReportArtifacts",
    "export_report",
    "render_html",
    "render_markdown",
]
