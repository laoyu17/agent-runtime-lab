from __future__ import annotations

import json
from pathlib import Path

from memory_bench.types import Sample


def write_jsonl(samples: list[Sample], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(sample.model_dump(), ensure_ascii=False) + "\n")


def read_jsonl(path: str | Path) -> list[Sample]:
    file_path = Path(path)
    samples: list[Sample] = []
    with file_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            payload = line.strip()
            if not payload:
                continue
            try:
                parsed = json.loads(payload)
                samples.append(Sample.model_validate(parsed))
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"invalid sample line: {file_path}:{line_number}") from exc
    return samples
