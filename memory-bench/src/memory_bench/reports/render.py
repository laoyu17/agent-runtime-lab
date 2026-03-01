from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from memory_bench.evaluators.metrics import summarize_by_category, summarize_results
from memory_bench.reports.golden import (
    drift_warnings,
    infer_category_from_sample_id,
    select_golden_subset,
)
from memory_bench.types import EvalResult


@dataclass
class ReportArtifacts:
    markdown_path: Path
    csv_path: Path
    summary: dict[str, float]
    by_category: dict[str, dict[str, float]]
    warnings: list[str]


def render_single_run_report(
    *,
    run_results: list[EvalResult],
    output_dir: Path,
    run_label: str,
    golden_per_category: int,
    drift_threshold: float,
    baseline_summary: dict[str, float] | None = None,
) -> ReportArtifacts:
    output_dir.mkdir(parents=True, exist_ok=True)

    sample_to_category = {
        result.sample_id: infer_category_from_sample_id(result.sample_id)
        for result in run_results
    }
    constraint_counts = {
        result.sample_id: 1 if result.sample_id.startswith("constraint_memory_") else 0
        for result in run_results
    }

    overall = summarize_results(run_results, constraint_counts).model_dump()
    by_category = {
        key: value.model_dump()
        for key, value in summarize_by_category(
            run_results,
            sample_to_category,
            constraint_counts,
        ).items()
    }

    golden_results = select_golden_subset(run_results, per_category=golden_per_category)
    golden_summary = summarize_results(golden_results, constraint_counts).model_dump()

    warnings = drift_warnings(
        {
            "memory_recall_rate": overall["memory_recall_rate"],
            "constraint_retention_rate": overall["constraint_retention_rate"],
            "contradiction_rate": overall["contradiction_rate"],
        },
        baseline_summary,
        threshold=drift_threshold,
    )

    markdown_path = output_dir / f"{run_label}.md"
    csv_path = output_dir / f"{run_label}.csv"

    _write_csv(csv_path, overall, by_category, golden_summary, warnings)
    _write_markdown(markdown_path, run_label, overall, by_category, golden_summary, warnings)

    return ReportArtifacts(
        markdown_path=markdown_path,
        csv_path=csv_path,
        summary={
            "memory_recall_rate": overall["memory_recall_rate"],
            "constraint_retention_rate": overall["constraint_retention_rate"],
            "contradiction_rate": overall["contradiction_rate"],
            "avg_latency_ms": overall["avg_latency_ms"],
            "p50_latency_ms": overall["p50_latency_ms"],
            "p95_latency_ms": overall["p95_latency_ms"],
        },
        by_category={
            category: {
                "memory_recall_rate": metrics["memory_recall_rate"],
                "constraint_retention_rate": metrics["constraint_retention_rate"],
                "contradiction_rate": metrics["contradiction_rate"],
                "avg_latency_ms": metrics["avg_latency_ms"],
                "p50_latency_ms": metrics["p50_latency_ms"],
                "p95_latency_ms": metrics["p95_latency_ms"],
            }
            for category, metrics in by_category.items()
        },
        warnings=warnings,
    )


def render_compare_report(
    *,
    run_entries: list[tuple[str, list[EvalResult]]],
    output_dir: Path,
    report_name: str,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    markdown_path = output_dir / f"{report_name}.md"
    csv_path = output_dir / f"{report_name}.csv"

    rows: list[dict[str, str]] = []
    for run_label, results in run_entries:
        constraint_counts = {
            result.sample_id: 1 if result.sample_id.startswith("constraint_memory_") else 0
            for result in results
        }
        summary = summarize_results(results, constraint_counts).model_dump()
        rows.append(
            {
                "run_label": run_label,
                "memory_recall_rate": f"{summary['memory_recall_rate']:.6f}",
                "constraint_retention_rate": (
                    f"{summary['constraint_retention_rate']:.6f}"
                ),
                "contradiction_rate": f"{summary['contradiction_rate']:.6f}",
                "avg_latency_ms": f"{summary['avg_latency_ms']:.4f}",
                "p50_latency_ms": f"{summary['p50_latency_ms']:.4f}",
                "p95_latency_ms": f"{summary['p95_latency_ms']:.4f}",
            }
        )

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = list(rows[0].keys()) if rows else ["run_label"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    lines = [
        f"# Compare Report: {report_name}",
        "",
        "| run | memory_recall_rate | constraint_retention_rate | "
        "contradiction_rate | avg_latency_ms | p50_latency_ms | p95_latency_ms |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {run_label} | {memory_recall_rate} | {constraint_retention_rate} | "
            "{contradiction_rate} | {avg_latency_ms} | {p50_latency_ms} | "
            "{p95_latency_ms} |".format(**row)
        )

    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return markdown_path, csv_path


def _write_csv(
    path: Path,
    overall: dict[str, float],
    by_category: dict[str, dict[str, float]],
    golden_summary: dict[str, float],
    warnings: list[str],
) -> None:
    fieldnames = ["scope", "metric", "value"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        for metric, value in overall.items():
            writer.writerow({"scope": "overall", "metric": metric, "value": f"{value:.6f}"})
        for category, metrics in sorted(by_category.items()):
            for metric, value in metrics.items():
                writer.writerow(
                    {"scope": category, "metric": metric, "value": f"{value:.6f}"}
                )
        for metric, value in golden_summary.items():
            writer.writerow(
                {
                    "scope": "golden_subset",
                    "metric": metric,
                    "value": f"{value:.6f}",
                }
            )
        for warning in warnings:
            writer.writerow({"scope": "warning", "metric": "drift", "value": warning})


def _write_markdown(
    path: Path,
    run_label: str,
    overall: dict[str, float],
    by_category: dict[str, dict[str, float]],
    golden_summary: dict[str, float],
    warnings: list[str],
) -> None:
    lines = [
        f"# Run Report: {run_label}",
        "",
        "## Overall Metrics",
        "",
        "| metric | value |",
        "|---|---:|",
    ]
    for metric, value in overall.items():
        lines.append(f"| {metric} | {value:.6f} |")

    lines.extend(
        [
            "",
            "## Metrics by Category",
            "",
            "| category | memory_recall_rate | constraint_retention_rate | "
            "contradiction_rate | avg_latency_ms | p50_latency_ms | p95_latency_ms |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for category, metrics in sorted(by_category.items()):
        lines.append(
            "| {category} | {memory_recall_rate:.6f} | "
            "{constraint_retention_rate:.6f} | {contradiction_rate:.6f} | "
            "{avg_latency_ms:.6f} | {p50_latency_ms:.6f} | {p95_latency_ms:.6f} |".format(
                category=category,
                **metrics,
            )
        )

    lines.extend(
        [
            "",
            "## Golden Subset Metrics",
            "",
            "| metric | value |",
            "|---|---:|",
        ]
    )
    for metric, value in golden_summary.items():
        lines.append(f"| {metric} | {value:.6f} |")

    lines.extend(["", "## Drift Warnings", ""])
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- none")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
