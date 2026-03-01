from __future__ import annotations

import json
from pathlib import Path

from memory_bench.types import EvalResult


def load_run(path: str | Path) -> list[EvalResult]:
    run_path = Path(path)
    if not run_path.exists():
        raise ValueError(f"run file not found: {run_path}")

    results: list[EvalResult] = []
    with run_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            payload = line.strip()
            if not payload:
                continue
            try:
                parsed = json.loads(payload)
                results.append(EvalResult.model_validate(parsed))
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"invalid run row at {run_path}:{line_number}") from exc

    return results
