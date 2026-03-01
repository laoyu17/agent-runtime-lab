from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from memory_bench.types import Category


class DatasetConfig(BaseModel):
    categories: dict[Category, int] = Field(default_factory=dict)
    default_distractor_level: str = "medium"


class EvaluationConfig(BaseModel):
    golden_subset_per_category: int = 5
    drift_threshold: float = 0.03
    collect_latency: bool = True


class BenchmarkConfig(BaseModel):
    seed: int = 20260301
    schema_version: int = 1
    output_dir: str = "outputs"
    dataset: DatasetConfig
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)


def load_benchmark_config(path: str | Path) -> BenchmarkConfig:
    config_path = Path(path)
    raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return BenchmarkConfig.model_validate(raw)
