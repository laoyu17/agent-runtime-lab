from __future__ import annotations

from memory_bench.strategies.base import Message, StatelessStrategy, StrategyConfig


class FullContextStrategy(StatelessStrategy):
    name = "full_context"

    def build_context(
        self,
        history: list[Message],
        memory_state: dict[str, object],
        config: StrategyConfig | None = None,
    ) -> list[Message]:
        _ = memory_state
        _ = config
        return [dict(message) for message in history]
