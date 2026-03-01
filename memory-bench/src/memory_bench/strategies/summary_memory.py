from __future__ import annotations

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

DEFAULT_TEMPLATE = (
    "User preferences: {user_preferences}\n"
    "Hard constraints: {hard_constraints}\n"
    "Named entities: {named_entities}\n"
    "Task goal: {task_goal}"
)


class SummaryMemoryStrategy(MemoryStrategy):
    name = "summary_memory"

    def build_context(
        self,
        history: list[Message],
        memory_state: MemoryState,
        config: StrategyConfig | None = None,
    ) -> list[Message]:
        cfg = dict(config or {})
        recent_turns = int(cfg.get("recent_turns", 2))
        template = str(cfg.get("summary_template", DEFAULT_TEMPLATE))

        summary = _ensure_summary(copy_state(memory_state))
        summary_block = template.format(
            user_preferences=", ".join(summary["user_preferences"]) or "none",
            hard_constraints=", ".join(summary["hard_constraints"]) or "none",
            named_entities=", ".join(summary["named_entities"]) or "none",
            task_goal=summary["task_goal"] or "none",
        )

        messages: list[Message] = [{"role": "system", "content": summary_block}]
        if recent_turns > 0:
            messages.extend([dict(message) for message in history[-recent_turns:]])
        return messages

    def update_memory(
        self,
        turn: Message,
        response: str,
        memory_state: MemoryState,
    ) -> MemoryState:
        state = copy_state(memory_state)
        summary = _ensure_summary(state)

        for key, value in extract_kv_pairs(turn.get("content", ""), response):
            item = f"{key}={value}"
            if key in PREFERENCE_KEYS:
                summary["user_preferences"].append(item)
            elif key in CONSTRAINT_KEYS:
                summary["hard_constraints"].append(item)
            elif key in ENTITY_KEYS:
                summary["named_entities"].append(item)
            elif key in GOAL_KEYS:
                summary["task_goal"] = value

        summary["user_preferences"] = uniq(summary["user_preferences"])
        summary["hard_constraints"] = uniq(summary["hard_constraints"])
        summary["named_entities"] = uniq(summary["named_entities"])
        state["summary"] = summary
        return state


def _ensure_summary(state: MemoryState) -> dict[str, object]:
    summary = dict(state.get("summary") or {})
    summary.setdefault("user_preferences", [])
    summary.setdefault("hard_constraints", [])
    summary.setdefault("named_entities", [])
    summary.setdefault("task_goal", "")
    return summary
