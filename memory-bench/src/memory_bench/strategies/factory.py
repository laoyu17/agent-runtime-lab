from __future__ import annotations

from memory_bench.strategies.base import MemoryStrategy
from memory_bench.strategies.full_context import FullContextStrategy
from memory_bench.strategies.sliding_window import SlidingWindowStrategy
from memory_bench.strategies.structured_memory import StructuredMemoryStrategy
from memory_bench.strategies.summary_memory import SummaryMemoryStrategy


def available_strategies() -> dict[str, type[MemoryStrategy]]:
    return {
        "full_context": FullContextStrategy,
        "sliding_window": SlidingWindowStrategy,
        "summary_memory": SummaryMemoryStrategy,
        "structured_memory": StructuredMemoryStrategy,
    }


def create_strategy(name: str) -> MemoryStrategy:
    registry = available_strategies()
    if name not in registry:
        raise ValueError(f"unsupported strategy: {name}")
    return registry[name]()
