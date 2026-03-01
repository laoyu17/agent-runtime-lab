from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Category = Literal[
    "preference_memory",
    "constraint_memory",
    "slot_memory",
    "distractor_memory",
]
Role = Literal["system", "user", "assistant"]


class DialogueTurn(BaseModel):
    role: Role
    content: str = Field(min_length=1)


class Sample(BaseModel):
    id: str = Field(min_length=1)
    category: Category
    dialogue: list[DialogueTurn] = Field(min_length=3)
    target_query: str = Field(min_length=1)
    memory_points: list[str] = Field(default_factory=list)
    hard_constraints: list[str] = Field(default_factory=list)
    expected_facts: list[str] = Field(default_factory=list)
    distractor_level: Literal["low", "medium", "high"]

    @field_validator("memory_points", "hard_constraints", "expected_facts")
    @classmethod
    def _no_empty_items(cls, values: list[str]) -> list[str]:
        if any(not item.strip() for item in values):
            raise ValueError("list contains empty item")
        return values


class EvalResult(BaseModel):
    run_id: str
    sample_id: str
    strategy: str
    adapter: str
    final_answer: str
    memory_hits: float = Field(ge=0.0, le=1.0)
    constraint_violations: int = Field(ge=0)
    contradictions: int = Field(ge=0)
    latency_ms: float = Field(ge=0)


class MetricsSummary(BaseModel):
    memory_recall_rate: float = Field(ge=0.0, le=1.0)
    constraint_retention_rate: float = Field(ge=0.0, le=1.0)
    contradiction_rate: float = Field(ge=0.0, le=1.0)
    avg_latency_ms: float = Field(ge=0.0)
    p50_latency_ms: float = Field(ge=0.0)
    p95_latency_ms: float = Field(ge=0.0)
