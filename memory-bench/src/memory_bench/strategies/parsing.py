from __future__ import annotations

import re
from collections.abc import Iterable

KV_PATTERN = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)=([^,.;\s]+)")

PREFERENCE_KEYS = {"favorite_drink", "breakfast_style", "budget_usd"}
CONSTRAINT_KEYS = {"format", "forbidden_word", "max_items"}
ENTITY_KEYS = {
    "traveler_name",
    "destination",
    "travel_date",
    "project",
    "preferred_channel",
    "deadline",
}
GOAL_KEYS = {"task_goal", "goal", "target"}


def extract_kv_pairs(*texts: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for text in texts:
        for key, value in KV_PATTERN.findall(text):
            pairs.append((key.lower(), value))
    return pairs


def uniq(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output
