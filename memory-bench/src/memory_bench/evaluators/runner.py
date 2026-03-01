from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from memory_bench.adapters import create_adapter
from memory_bench.datasets import read_jsonl
from memory_bench.evaluators.metrics import summarize_by_category, summarize_results
from memory_bench.evaluators.scoring import (
    constraint_violations,
    contradiction_count,
    memory_recall,
)
from memory_bench.strategies import create_strategy
from memory_bench.strategies.base import Message
from memory_bench.types import EvalResult, Sample


def run_evaluation(
    *,
    strategy_name: str,
    adapter_name: str,
    benchmark_config_path: Path,
    dataset_dir: Path,
    output_dir: Path,
    strategy_config_path: Path,
) -> dict[str, Any]:
    strategy_cfg_map = _load_strategy_config(strategy_config_path)
    strategy_cfg = strategy_cfg_map.get(strategy_name, {})
    strategy = create_strategy(strategy_name)

    benchmark_config = _load_yaml(benchmark_config_path)
    adapter_config = (benchmark_config.get("adapter") or {}).get(adapter_name, {})
    adapter = create_adapter(adapter_name, adapter_config)

    samples = load_all_samples(dataset_dir)
    if not samples:
        raise ValueError(f"no samples found in dataset_dir: {dataset_dir}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{timestamp}_{strategy_name}_{adapter_name}"

    results: list[EvalResult] = []
    sample_to_category: dict[str, str] = {}
    constraint_counts: dict[str, int] = {}

    for sample in samples:
        sample_to_category[sample.id] = sample.category
        constraint_counts[sample.id] = len(sample.hard_constraints)

        history_messages = [
            {"role": turn.role, "content": turn.content} for turn in sample.dialogue
        ]
        ensure_role_messages(history_messages)
        memory_state: dict[str, Any] = {}

        for idx, turn in enumerate(history_messages):
            if turn["role"] != "user":
                continue

            response_text = ""
            if idx + 1 < len(history_messages):
                next_turn = history_messages[idx + 1]
                if next_turn["role"] == "assistant":
                    response_text = next_turn["content"]

            memory_state = strategy.update_memory(turn, response_text, memory_state)

        context_messages = strategy.build_context(history_messages, memory_state, strategy_cfg)
        final_messages = [*context_messages, {"role": "user", "content": sample.target_query}]

        started_at = time.perf_counter()
        final_answer = adapter.generate(final_messages, metadata={"sample_id": sample.id})
        latency_ms = (time.perf_counter() - started_at) * 1000

        expected = sample.expected_facts or sample.memory_points
        memory_hits = memory_recall(final_answer, expected)
        violations = constraint_violations(final_answer, sample.hard_constraints)
        contradictions = contradiction_count(final_answer, expected)

        results.append(
            EvalResult(
                run_id=run_id,
                sample_id=sample.id,
                strategy=strategy_name,
                adapter=adapter_name,
                final_answer=final_answer,
                memory_hits=memory_hits,
                constraint_violations=violations,
                contradictions=contradictions,
                latency_ms=latency_ms,
            )
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    run_path = output_dir / f"{run_id}.jsonl"
    with run_path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result.model_dump(), ensure_ascii=False) + "\n")

    summary = summarize_results(results, constraint_counts)
    category_summary = summarize_by_category(results, sample_to_category, constraint_counts)

    return {
        "run_id": run_id,
        "run_path": str(run_path),
        "total_samples": len(results),
        "summary": summary.model_dump(),
        "by_category": {
            key: value.model_dump() for key, value in category_summary.items()
        },
    }


def load_all_samples(dataset_dir: Path) -> list[Sample]:
    files = sorted(dataset_dir.glob("*.jsonl"))
    samples: list[Sample] = []
    for file in files:
        samples.extend(read_jsonl(file))
    return samples


def infer_default_dataset_dir(config_path: Path) -> Path:
    return config_path.resolve().parent.parent / "data" / "benchmark_sets"


def infer_default_output_dir(config_path: Path) -> Path:
    return config_path.resolve().parent.parent / "outputs" / "runs"


def infer_strategy_config_path(config_path: Path) -> Path:
    return config_path.resolve().parent / "strategies.yaml"


def ensure_role_messages(messages: list[Message]) -> list[Message]:
    for message in messages:
        role = message.get("role", "")
        if role not in {"system", "user", "assistant"}:
            raise ValueError(f"invalid message role: {role}")
        if not str(message.get("content", "")).strip():
            raise ValueError("message content must not be empty")
    return messages


def _load_strategy_config(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}

    raw = _load_yaml(path)
    output: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        if isinstance(value, dict):
            cfg = dict(value)
            cfg.pop("enabled", None)
            output[key] = cfg
        else:
            output[key] = {}
    return output


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
