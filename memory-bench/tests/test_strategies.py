from __future__ import annotations

import pytest

from memory_bench.strategies import create_strategy


@pytest.mark.parametrize(
    "name",
    ["full_context", "sliding_window", "summary_memory", "structured_memory"],
)
def test_strategy_can_build_context_and_update_memory(name: str) -> None:
    strategy = create_strategy(name)
    history = [
        {"role": "user", "content": "remember favorite_drink=black_coffee"},
        {"role": "assistant", "content": "stored"},
        {"role": "user", "content": "what is my drink"},
    ]

    state = strategy.update_memory(history[0], history[1]["content"], {})
    context = strategy.build_context(history, state, {"window_turns": 2})

    assert isinstance(context, list)
    assert len(context) >= 1


def test_sliding_window_respects_window_turns() -> None:
    strategy = create_strategy("sliding_window")
    history = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
    ]

    context = strategy.build_context(history, {}, {"window_turns": 2})
    assert context == history[-2:]


def test_summary_and_structured_strategy_store_slots() -> None:
    for name, key in [("summary_memory", "summary"), ("structured_memory", "slots")]:
        strategy = create_strategy(name)
        state = strategy.update_memory(
            {"role": "user", "content": "remember destination=Kyoto and travel_date=2026-04-18"},
            "ok",
            {},
        )
        assert key in state
