from __future__ import annotations

from pathlib import Path

from memory_bench.datasets import generate_samples, load_benchmark_config, read_jsonl, write_jsonl


def test_generate_samples_from_config_has_120_items() -> None:
    config_path = Path(__file__).resolve().parents[1] / "configs" / "benchmark.yaml"
    config = load_benchmark_config(config_path)

    by_category = generate_samples(config)

    assert set(by_category.keys()) == {
        "preference_memory",
        "constraint_memory",
        "slot_memory",
        "distractor_memory",
    }
    assert sum(len(samples) for samples in by_category.values()) == 120
    assert all(len(samples) == 30 for samples in by_category.values())



def test_jsonl_roundtrip(tmp_path: Path) -> None:
    config_path = Path(__file__).resolve().parents[1] / "configs" / "benchmark.yaml"
    config = load_benchmark_config(config_path)
    samples = generate_samples(config)["preference_memory"][:3]

    output_path = tmp_path / "roundtrip.jsonl"
    write_jsonl(samples, output_path)
    loaded = read_jsonl(output_path)

    assert len(loaded) == 3
    assert loaded[0].id.startswith("preference_memory_")
    assert loaded[0].dialogue[0].role == "user"
