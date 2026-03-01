from __future__ import annotations

import argparse
import json
from pathlib import Path

from memory_bench.datasets import generate_samples, load_benchmark_config, write_jsonl
from memory_bench.evaluators import (
    infer_default_dataset_dir,
    infer_default_output_dir,
    infer_strategy_config_path,
    run_evaluation,
)
from memory_bench.reports import load_run, render_compare_report, render_single_run_report


def _default_dataset_dir(config_path: Path) -> Path:
    return config_path.resolve().parent.parent / "data" / "benchmark_sets"


def _cmd_generate(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    config = load_benchmark_config(config_path)
    by_category = generate_samples(config)

    output_dir = Path(args.output_dir) if args.output_dir else _default_dataset_dir(config_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    written_files: list[str] = []
    total = 0
    for category, samples in by_category.items():
        path = output_dir / f"{category}.jsonl"
        write_jsonl(samples, path)
        written_files.append(str(path))
        total += len(samples)

    print(
        json.dumps(
            {
                "ok": True,
                "total_samples": total,
                "categories": {k: len(v) for k, v in by_category.items()},
                "output_dir": str(output_dir),
                "files": written_files,
            },
            ensure_ascii=False,
        )
    )
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    benchmark_config_path = Path(args.config)
    dataset_dir = (
        Path(args.dataset_dir)
        if args.dataset_dir
        else infer_default_dataset_dir(benchmark_config_path)
    )
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else infer_default_output_dir(benchmark_config_path)
    )
    strategy_config_path = (
        Path(args.strategy_config)
        if args.strategy_config
        else infer_strategy_config_path(benchmark_config_path)
    )

    result = run_evaluation(
        strategy_name=args.strategy,
        adapter_name=args.adapter,
        benchmark_config_path=benchmark_config_path,
        dataset_dir=dataset_dir,
        output_dir=output_dir,
        strategy_config_path=strategy_config_path,
    )
    print(json.dumps({"ok": True, **result}, ensure_ascii=False))
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    run_paths = [Path(item) for item in args.runs]
    output_dir = Path(args.output_dir)

    run_entries = []
    for run_path in run_paths:
        results = load_run(run_path)
        run_entries.append((run_path.stem, results))

    markdown_path, csv_path = render_compare_report(
        run_entries=run_entries,
        output_dir=output_dir,
        report_name=args.name,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "markdown": str(markdown_path),
                "csv": str(csv_path),
                "runs": [str(path) for path in run_paths],
            },
            ensure_ascii=False,
        )
    )
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    run_path = Path(args.run)
    config = load_benchmark_config(Path(args.config))
    output_dir = Path(args.output_dir)

    artifacts = render_single_run_report(
        run_results=load_run(run_path),
        output_dir=output_dir,
        run_label=run_path.stem,
        golden_per_category=config.evaluation.golden_subset_per_category,
        drift_threshold=config.evaluation.drift_threshold,
    )

    print(
        json.dumps(
            {
                "ok": True,
                "markdown": str(artifacts.markdown_path),
                "csv": str(artifacts.csv_path),
                "summary": artifacts.summary,
                "warnings": artifacts.warnings,
            },
            ensure_ascii=False,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="memory-bench")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="Generate benchmark dataset JSONL files")
    generate.add_argument("--config", default="configs/benchmark.yaml")
    generate.add_argument("--output-dir", default="")

    eval_parser = subparsers.add_parser("eval", help="Evaluate a strategy")
    eval_parser.add_argument("--strategy", required=True)
    eval_parser.add_argument(
        "--adapter",
        choices=["mock", "openai", "runtime"],
        required=True,
    )
    eval_parser.add_argument("--config", default="configs/benchmark.yaml")
    eval_parser.add_argument("--dataset-dir", default="")
    eval_parser.add_argument("--output-dir", default="")
    eval_parser.add_argument("--strategy-config", default="")

    compare_parser = subparsers.add_parser("compare", help="Compare run outputs")
    compare_parser.add_argument("--runs", nargs="+", required=True)
    compare_parser.add_argument("--output-dir", default="outputs/reports")
    compare_parser.add_argument("--name", default="compare")

    report_parser = subparsers.add_parser("report", help="Generate report for one run")
    report_parser.add_argument("--run", required=True)
    report_parser.add_argument("--config", default="configs/benchmark.yaml")
    report_parser.add_argument("--output-dir", default="outputs/reports")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "generate":
            return _cmd_generate(args)
        if args.command == "eval":
            return _cmd_eval(args)
        if args.command == "compare":
            return _cmd_compare(args)
        if args.command == "report":
            return _cmd_report(args)

        parser.error(f"unsupported command: {args.command}")
        return 2
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
