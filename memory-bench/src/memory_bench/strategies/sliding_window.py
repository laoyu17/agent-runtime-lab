from __future__ import annotations

from memory_bench.strategies.base import Message, StatelessStrategy, StrategyConfig


class SlidingWindowStrategy(StatelessStrategy):
    name = "sliding_window"

    def build_context(
        self,
        history: list[Message],
        memory_state: dict[str, object],
        config: StrategyConfig | None = None,
    ) -> list[Message]:
        _ = memory_state
        cfg = dict(config or {})
        window_turns = int(cfg.get("window_turns", 6))
        if window_turns <= 0:
            return []
        return [dict(message) for message in history[-window_turns:]]
