from __future__ import annotations

import json
from typing import Any

from memory_bench.adapters.base import ChatAdapter
from memory_bench.strategies.base import Message
from memory_bench.strategies.parsing import extract_kv_pairs


class MockAdapter(ChatAdapter):
    """Deterministic adapter that infers facts from input context only."""

    name = "mock"

    def generate(self, messages: list[Message], *, metadata: dict[str, Any] | None = None) -> str:
        _ = metadata
        pairs = extract_kv_pairs(*[message.get("content", "") for message in messages])

        facts: dict[str, str] = {}
        for key, value in pairs:
            facts[key] = value

        hard_constraints = {
            key: value
            for key, value in facts.items()
            if key in {"format", "forbidden_word", "max_items"}
        }

        payload = {
            key: value
            for key, value in facts.items()
            if key not in {"format", "forbidden_word", "max_items"}
        }

        if hard_constraints.get("max_items"):
            max_items = int(hard_constraints["max_items"])
            sliced = list(payload.items())[:max_items]
            payload = dict(sliced)

        if hard_constraints.get("format") == "json_only":
            answer = json.dumps(payload, ensure_ascii=False)
        else:
            if not payload:
                answer = "No memory facts found in context."
            else:
                answer = "; ".join(f"{key}={value}" for key, value in payload.items())

        forbidden = hard_constraints.get("forbidden_word", "").lower().strip()
        if forbidden:
            answer = answer.replace(forbidden, "")

        return answer
