from __future__ import annotations

import random
from typing import Callable

from memory_bench.datasets.config import BenchmarkConfig
from memory_bench.types import Category, DialogueTurn, Sample

LEVELS = ("low", "medium", "high")


def generate_samples(config: BenchmarkConfig) -> dict[Category, list[Sample]]:
    rng = random.Random(config.seed)
    builders: dict[Category, Callable[[int, random.Random, str], Sample]] = {
        "preference_memory": _build_preference_sample,
        "constraint_memory": _build_constraint_sample,
        "slot_memory": _build_slot_sample,
        "distractor_memory": _build_distractor_sample,
    }

    results: dict[Category, list[Sample]] = {}
    for category, count in config.dataset.categories.items():
        if category not in builders:
            raise ValueError(f"unsupported category: {category}")
        if count <= 0:
            raise ValueError(f"invalid sample count for {category}: {count}")

        samples: list[Sample] = []
        for index in range(1, count + 1):
            distractor_level = LEVELS[(index - 1) % len(LEVELS)]
            samples.append(builders[category](index, rng, distractor_level))
        results[category] = samples

    return results


def _build_preference_sample(index: int, rng: random.Random, level: str) -> Sample:
    drinks = ["black_coffee", "green_tea", "oat_latte", "sparkling_water"]
    meals = ["high_protein", "low_carb", "vegetarian", "quick_breakfast"]
    drink = rng.choice(drinks)
    meal = rng.choice(meals)
    budget = rng.choice([12, 15, 18, 20, 22])

    memory_points = [
        f"favorite_drink={drink}",
        f"breakfast_style={meal}",
        f"budget_usd={budget}",
    ]

    dialogue = [
        DialogueTurn(
            role="user",
            content=(
                "Please remember my breakfast profile: "
                f"style={meal}, drink={drink}, budget={budget} USD."
            ),
        ),
        DialogueTurn(
            role="assistant",
            content="Stored. I will keep these preferences for later requests.",
        ),
        *_distractor_turns(rng, level),
    ]

    return Sample(
        id=f"preference_memory_{index:03d}",
        category="preference_memory",
        dialogue=dialogue,
        target_query="Based on my stored profile, suggest one breakfast set.",
        memory_points=memory_points,
        hard_constraints=[],
        expected_facts=memory_points,
        distractor_level=level,
    )


def _build_constraint_sample(index: int, rng: random.Random, level: str) -> Sample:
    forbidden_words = ["sorry", "cannot", "unavailable", "maybe"]
    banned = rng.choice(forbidden_words)
    max_items = rng.choice([2, 3, 4])

    hard_constraints = [
        "format=json_only",
        f"forbidden_word={banned}",
        f"max_items={max_items}",
    ]

    dialogue = [
        DialogueTurn(
            role="user",
            content=(
                "Persist these hard constraints for all future answers: "
                "JSON only, avoid forbidden wording, and keep item count bounded."
            ),
        ),
        DialogueTurn(
            role="assistant",
            content="Constraints captured and will be enforced in follow-up responses.",
        ),
        *_distractor_turns(rng, level),
    ]

    return Sample(
        id=f"constraint_memory_{index:03d}",
        category="constraint_memory",
        dialogue=dialogue,
        target_query=(
            "Return a short packing checklist that must obey earlier constraints "
            "without restating them."
        ),
        memory_points=hard_constraints,
        hard_constraints=hard_constraints,
        expected_facts=hard_constraints,
        distractor_level=level,
    )


def _build_slot_sample(index: int, rng: random.Random, level: str) -> Sample:
    names = ["Avery", "Jordan", "Morgan", "Taylor", "Riley"]
    destinations = ["Kyoto", "Lisbon", "Vancouver", "Seoul", "Prague"]
    dates = ["2026-04-18", "2026-05-02", "2026-05-19", "2026-06-03", "2026-06-24"]
    name = rng.choice(names)
    destination = rng.choice(destinations)
    date = rng.choice(dates)

    slots = [
        f"traveler_name={name}",
        f"destination={destination}",
        f"travel_date={date}",
    ]

    dialogue = [
        DialogueTurn(
            role="user",
            content=(
                "Store my trip slots for later: "
                f"name={name}, destination={destination}, date={date}."
            ),
        ),
        DialogueTurn(
            role="assistant",
            content="Trip slots stored and ready for retrieval.",
        ),
        *_distractor_turns(rng, level),
    ]

    return Sample(
        id=f"slot_memory_{index:03d}",
        category="slot_memory",
        dialogue=dialogue,
        target_query="Draft a one-line itinerary header using my saved slots.",
        memory_points=slots,
        hard_constraints=[],
        expected_facts=slots,
        distractor_level=level,
    )


def _build_distractor_sample(index: int, rng: random.Random, level: str) -> Sample:
    projects = ["atlas", "nebula", "solstice", "meridian", "aurora"]
    channels = ["email", "slack", "sms", "call"]
    project = rng.choice(projects)
    channel = rng.choice(channels)
    deadline = rng.choice(["2026-03-20", "2026-03-28", "2026-04-01", "2026-04-09"])

    facts = [
        f"project={project}",
        f"preferred_channel={channel}",
        f"deadline={deadline}",
    ]

    dialogue = [
        DialogueTurn(
            role="user",
            content=(
                "Keep these task facts even if later turns are noisy: "
                f"project={project}, channel={channel}, deadline={deadline}."
            ),
        ),
        DialogueTurn(
            role="assistant",
            content="Task facts saved. I will keep them despite unrelated context.",
        ),
        *_distractor_turns(rng, "high" if level == "high" else level),
    ]

    return Sample(
        id=f"distractor_memory_{index:03d}",
        category="distractor_memory",
        dialogue=dialogue,
        target_query="Summarize my active task using the original saved facts only.",
        memory_points=facts,
        hard_constraints=[],
        expected_facts=facts,
        distractor_level=level,
    )


def _distractor_turns(rng: random.Random, level: str) -> list[DialogueTurn]:
    distractor_prompts = [
        "What is a good way to clean a keyboard?",
        "Can you explain how rainbows are formed?",
        "Give one tip for writing concise emails.",
        "Name two healthy afternoon snacks.",
        "What is a safe way to organize desktop cables?",
        "How do I estimate commute time with uncertainty?",
    ]
    distractor_replies = [
        "Use compressed air and a microfiber cloth in short passes.",
        "Rainbows appear when light refracts, reflects, and disperses in droplets.",
        "Lead with the ask, then add context, then deadline.",
        "Try fruit with nuts or yogurt with oats.",
        "Bundle cables with labels and separate power from signal lines.",
        "Use median travel time plus a small safety buffer.",
    ]

    rounds = {"low": 1, "medium": 2, "high": 3}.get(level, 2)
    turns: list[DialogueTurn] = []
    for _ in range(rounds):
        idx = rng.randrange(len(distractor_prompts))
        turns.append(DialogueTurn(role="user", content=distractor_prompts[idx]))
        turns.append(DialogueTurn(role="assistant", content=distractor_replies[idx]))
    return turns
