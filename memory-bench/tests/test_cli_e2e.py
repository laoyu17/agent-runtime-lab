from __future__ import annotations

import json
import sys
from pathlib import Path

from memory_bench import cli


def _run_cli(monkeypatch, capsys, argv: list[str]) -> dict[str, object]:
    monkeypatch.setattr(sys, "argv", ["memory-bench", *argv])
    code = cli.main()
    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err
    payload = json.loads(captured.out.strip().splitlines()[-1])
    assert payload["ok"] is True
    return payload


def test_generate_eval_report_compare_pipeline(tmp_path: Path, monkeypatch, capsys) -> None:
    project_root = Path(__file__).resolve().parents[1]
    config_path = project_root / "configs" / "benchmark.yaml"
    strategy_config = project_root / "configs" / "strategies.yaml"

    dataset_dir = tmp_path / "dataset"
    runs_dir = tmp_path / "runs"
    reports_dir = tmp_path / "reports"

    generate_payload = _run_cli(
        monkeypatch,
        capsys,
        [
            "generate",
            "--config",
            str(config_path),
            "--output-dir",
            str(dataset_dir),
        ],
    )
    assert generate_payload["total_samples"] == 120

    eval_payload_a = _run_cli(
        monkeypatch,
        capsys,
        [
            "eval",
            "--strategy",
            "full_context",
            "--adapter",
            "mock",
            "--config",
            str(config_path),
            "--dataset-dir",
            str(dataset_dir),
            "--output-dir",
            str(runs_dir),
            "--strategy-config",
            str(strategy_config),
        ],
    )
    run_a = Path(eval_payload_a["run_path"])
    assert run_a.exists()

    eval_payload_b = _run_cli(
        monkeypatch,
        capsys,
        [
            "eval",
            "--strategy",
            "sliding_window",
            "--adapter",
            "runtime",
            "--config",
            str(config_path),
            "--dataset-dir",
            str(dataset_dir),
            "--output-dir",
            str(runs_dir),
            "--strategy-config",
            str(strategy_config),
        ],
    )
    run_b = Path(eval_payload_b["run_path"])
    assert run_b.exists()

    report_payload = _run_cli(
        monkeypatch,
        capsys,
        [
            "report",
            "--run",
            str(run_a),
            "--config",
            str(config_path),
            "--output-dir",
            str(reports_dir),
        ],
    )
    assert Path(report_payload["markdown"]).exists()
    assert Path(report_payload["csv"]).exists()

    compare_payload = _run_cli(
        monkeypatch,
        capsys,
        [
            "compare",
            "--runs",
            str(run_a),
            str(run_b),
            "--output-dir",
            str(reports_dir),
            "--name",
            "comparison",
        ],
    )
    assert Path(compare_payload["markdown"]).exists()
    assert Path(compare_payload["csv"]).exists()
