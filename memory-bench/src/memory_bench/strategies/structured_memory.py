from __future__ import annotations

import json

from memory_bench.strategies.base import (
    MemoryState,
    MemoryStrategy,
    Message,
    StrategyConfig,
    copy_state,
)
from memory_bench.strategies.parsing import (
    CONSTRAINT_KEYS,
    ENTITY_KEYS,
    GOAL_KEYS,
    PREFERENCE_KEYS,
    extract_kv_pairs,
    uniq,
)

DEFAULT_SLOTS = [
    "user_preferences",
    "hard_constraints",
    "named_entities",
    "task_goal",
]


class StructuredMemoryStrategy(MemoryStrategy):
    name = "structured_memory"

    def build_context(
        self,
        history: list[Message],
        memory_state: MemoryState,
        config: StrategyConfig | None = None,
    ) -> list[Message]:
        cfg = dict(config or {})
        slots = list(cfg.get("slots", DEFAULT_SLOTS))

        state = copy_state(memory_state)
        memory_slots = _ensure_slots(state, slots)
        memory_json = json.dumps(memory_slots, ensure_ascii=False)

        return [
            {
                "role": "system",
                "content": f"Structured memory slots: {memory_json}",
            },
            *[dict(message) for message in history],
        ]

    def update_memory(
        self,
        turn: Message,
        response: str,
        memory_state: MemoryState,
    ) -> MemoryState:
        state = copy_state(memory_state)
        slots = _ensure_slots(state, DEFAULT_SLOTS)

        for key, value in extract_kv_pairs(turn.get("content", ""), response):
            item = f"{key}={value}"
            if key in PREFERENCE_KEYS:
                slots["user_preferences"].append(item)
            elif key in CONSTRAINT_KEYS:
                slots["hard_constraints"].append(item)
            elif key in ENTITY_KEYS:
                slots["named_entities"].append(item)
            elif key in GOAL_KEYS:
                slots["task_goal"] = value

        slots["user_preferences"] = uniq(slots["user_preferences"])
        slots["hard_constraints"] = uniq(slots["hard_constraints"])
        slots["named_entities"] = uniq(slots["named_entities"])
        state["slots"] = slots
        return state


def _ensure_slots(state: MemoryState, slot_names: list[str]) -> dict[str, object]:
    slots = dict(state.get("slots") or {})
    for slot in slot_names:
        if slot == "task_goal":
            slots.setdefault(slot, "")
        else:
            slots.setdefault(slot, [])
    return slots
