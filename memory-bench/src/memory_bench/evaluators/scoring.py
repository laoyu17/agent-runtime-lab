from __future__ import annotations

import json
import re
from typing import Iterable

from memory_bench.strategies.parsing import extract_kv_pairs


def memory_recall(answer: str, expected_facts: Iterable[str]) -> float:
    facts = [fact.strip() for fact in expected_facts if fact.strip()]
    if not facts:
        return 1.0

    answer_lower = answer.lower()
    hits = sum(1 for fact in facts if fact.lower() in answer_lower)
    return hits / len(facts)


def constraint_violations(answer: str, hard_constraints: Iterable[str]) -> int:
    constraints = [constraint.strip() for constraint in hard_constraints if constraint.strip()]
    if not constraints:
        return 0

    violations = 0
    parsed_json: dict[str, object] | list[object] | None = None
    json_checked = False

    for constraint in constraints:
        if constraint == "format=json_only":
            json_checked = True
            try:
                parsed_json = json.loads(answer)
            except json.JSONDecodeError:
                violations += 1
        elif constraint.startswith("forbidden_word="):
            word = constraint.split("=", 1)[1].strip().lower()
            if word and re.search(rf"\b{re.escape(word)}\b", answer.lower()):
                violations += 1
        elif constraint.startswith("max_items="):
            value = constraint.split("=", 1)[1].strip()
            try:
                max_items = int(value)
            except ValueError:
                continue

            if json_checked and parsed_json is not None:
                if isinstance(parsed_json, list) and len(parsed_json) > max_items:
                    violations += 1
                if isinstance(parsed_json, dict) and len(parsed_json) > max_items:
                    violations += 1
            else:
                line_items = [line for line in answer.splitlines() if line.strip()]
                if len(line_items) > max_items:
                    violations += 1

    return violations


def contradiction_count(answer: str, expected_facts: Iterable[str]) -> int:
    expected: dict[str, str] = {}
    for fact in expected_facts:
        if "=" not in fact:
            continue
        key, value = fact.split("=", 1)
        expected[key.strip().lower()] = value.strip().lower()

    observed: dict[str, str] = {}
    for key, value in extract_kv_pairs(answer):
        observed[key.lower()] = value.lower()

    contradictions = 0
    for key, value in expected.items():
        observed_value = observed.get(key)
        if observed_value is None:
            continue
        if observed_value != value:
            contradictions += 1
    return contradictions
