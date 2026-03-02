from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_runtime_lab.cli import _build_runtime
from agent_runtime_lab.config import AppConfig, list_profiles, load_config, save_config


def test_load_default_config_file() -> None:
    config = load_config("configs/default.yaml")

    assert config.runtime.max_steps == 12
    assert config.runtime.mode_default == "react"
    assert config.llm.provider == "mock"
    assert config.eval.dataset_path == "data/benchmarks/tasks.jsonl"
    assert config.trace.redact_sensitive is True
    assert "token" in config.trace.redact_keys


def test_save_and_reload_config_roundtrip(tmp_path: Path) -> None:
    config = AppConfig.from_dict(
        {
            "runtime": {"max_steps": 3, "mode_default": "plan_execute"},
            "llm": {"provider": "mock", "model": "mock-v2", "mock_seed": 7},
            "memory": {"summary_window": 4, "constraint_extractor": "keyword"},
            "retrieval": {"top_k": 2, "chunk_size": 256},
            "tool": {"timeout_ms": 2000, "retry": 2},
            "trace": {
                "output_dir": "outputs/traces",
                "sqlite_path": "outputs/traces/test.db",
                "redact_sensitive": False,
                "redact_keys": ["api_key"],
            },
            "eval": {"dataset_path": "data/benchmarks/tasks.jsonl", "metrics": ["a"]},
        }
    )
    path = tmp_path / "roundtrip.yaml"

    save_config(config, path)
    loaded = load_config(path)

    assert loaded.runtime.max_steps == 3
    assert loaded.runtime.mode_default == "plan_execute"
    assert loaded.tool.retry == 2
    assert loaded.trace.sqlite_path.endswith("test.db")
    assert loaded.trace.redact_sensitive is False
    assert loaded.trace.redact_keys == ["api_key"]


def test_yaml_root_must_be_mapping(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("- item1\n- item2\n", encoding="utf-8")

    with pytest.raises(ValueError, match="config root must be a mapping"):
        AppConfig.from_yaml_file(path)


def test_app_config_rejects_unknown_root_key() -> None:
    with pytest.raises(ValidationError):
        AppConfig.from_dict({"runtime": {"max_steps": 1}, "unknown": {}})


def test_load_config_with_profile_patch(tmp_path: Path) -> None:
    path = tmp_path / "profile.yaml"
    path.write_text(
        "\n".join(
            [
                "runtime:",
                "  max_steps: 12",
                "  mode_default: react",
                "profiles:",
                "  fast:",
                "    runtime:",
                "      max_steps: 2",
                "      mode_default: plan_execute",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(path, profile="fast", env_prefix=None)
    assert config.runtime.max_steps == 2
    assert config.runtime.mode_default == "plan_execute"

    with pytest.raises(ValueError, match="unknown profile"):
        load_config(path, profile="missing", env_prefix=None)


def test_list_profiles_and_env_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "profile-env.yaml"
    path.write_text(
        "\n".join(
            [
                "runtime:",
                "  max_steps: 5",
                "  mode_default: react",
                "retrieval:",
                "  top_k: 2",
                "  chunk_size: 128",
                "eval:",
                "  dataset_path: data/benchmarks/tasks.jsonl",
                "  metrics:",
                "    - task_success_rate",
                "profiles:",
                "  fast:",
                "    runtime:",
                "      max_steps: 3",
                "  safe:",
                "    runtime:",
                "      max_steps: 8",
            ]
        ),
        encoding="utf-8",
    )

    assert list_profiles(path) == ["fast", "safe"]

    monkeypatch.setenv("ARL_RUNTIME__MAX_STEPS", "9")
    monkeypatch.setenv("ARL_RETRIEVAL__TOP_K", "7")
    monkeypatch.setenv("ARL_EVAL__METRICS", '["a","b"]')
    config = load_config(path, profile="fast")
    assert config.runtime.max_steps == 9
    assert config.retrieval.top_k == 7
    assert config.eval.metrics == ["a", "b"]


def test_build_runtime_applies_config_to_runtime_dependencies() -> None:
    config = AppConfig.from_dict(
        {
            "runtime": {"max_steps": 3, "mode_default": "react"},
            "memory": {"summary_window": 2, "constraint_extractor": "keyword"},
            "retrieval": {"top_k": 6, "chunk_size": 128},
            "tool": {"timeout_ms": 1234, "retry": 2},
        }
    )

    runtime = _build_runtime(config)

    assert runtime.max_steps == 3
    assert runtime.retriever.top_k == 6
    assert runtime.retriever.chunk_size == 128
    assert runtime.reliability_manager.retry_policy.max_retries == 2
    assert runtime.reliability_manager.retry_policy.timeout_ms == 1234
    for spec in runtime.tool_registry.list_specs():
        assert spec.timeout_ms == 1234
        assert spec.retry == 2
