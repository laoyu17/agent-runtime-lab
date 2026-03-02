"""Runtime configuration contracts and load/save helpers."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from agent_runtime_lab.types import ExecutionMode


class ConfigBase(BaseModel):
    """Shared strict config base."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class RuntimeConfig(ConfigBase):
    max_steps: int = Field(default=12, ge=1)
    mode_default: ExecutionMode = "react"


class LLMConfig(ConfigBase):
    provider: str = "mock"
    model: str = "mock-gpt"
    mock_seed: int = 42
    endpoint: str | None = None
    api_key_env: str | None = None


class MemoryConfig(ConfigBase):
    summary_window: int = Field(default=5, ge=1)
    constraint_extractor: str = "keyword"


class RetrievalConfig(ConfigBase):
    top_k: int = Field(default=4, ge=1)
    chunk_size: int = Field(default=500, ge=1)


class ToolConfig(ConfigBase):
    timeout_ms: int = Field(default=4000, ge=1)
    retry: int = Field(default=1, ge=0)


class TraceConfig(ConfigBase):
    output_dir: str = "outputs/traces"
    sqlite_path: str = "outputs/traces/trace.db"
    redact_sensitive: bool = True
    redact_keys: list[str] = Field(
        default_factory=lambda: [
            "api_key",
            "token",
            "cookie",
            "password",
            "authorization",
            "secret",
        ]
    )


class EvalConfig(ConfigBase):
    dataset_path: str = "data/benchmarks/tasks.jsonl"
    metrics: list[str] = Field(
        default_factory=lambda: [
            "task_success_rate",
            "tool_call_success_rate",
            "avg_steps_per_task",
            "avg_latency_ms",
            "constraint_retention_rate",
        ]
    )


class AppConfig(ConfigBase):
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    tool: ToolConfig = Field(default_factory=ToolConfig)
    trace: TraceConfig = Field(default_factory=TraceConfig)
    eval: EvalConfig = Field(default_factory=EvalConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        """Build config from mapping data."""

        return cls.model_validate(data)

    @classmethod
    def from_yaml_file(
        cls,
        path: str | Path,
        profile: str | None = None,
        env_prefix: str | None = "ARL_",
    ) -> AppConfig:
        """Load config from YAML file with optional profile/env overrides."""

        payload = _read_yaml(path)
        resolved = resolve_config_payload(
            payload,
            profile=profile,
            env_prefix=env_prefix,
        )
        return cls.from_dict(resolved)


def _read_yaml(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"config root must be a mapping: {file_path}")
    return raw


def list_profiles(path: str | Path = "configs/default.yaml") -> list[str]:
    """List available profile names from config file."""

    payload = _read_yaml(path)
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict):
        return []
    return sorted(
        str(name) for name, value in profiles.items() if isinstance(value, dict)
    )


def resolve_config_payload(
    raw_payload: dict[str, Any],
    *,
    profile: str | None,
    env_prefix: str | None,
) -> dict[str, Any]:
    """Resolve base payload with optional profile patch and env overrides."""

    merged = _merge_profile(raw_payload, profile=profile)
    if not env_prefix:
        return merged
    return _apply_env_overrides(merged, env_prefix=env_prefix)


def _merge_profile(raw_payload: dict[str, Any], profile: str | None) -> dict[str, Any]:
    payload = deepcopy(raw_payload)
    raw_profiles = payload.pop("profiles", None)

    if profile is None:
        return payload

    if not isinstance(raw_profiles, dict):
        raise ValueError("profile requested but no profiles mapping found")

    patch = raw_profiles.get(profile)
    if patch is None:
        available = sorted(raw_profiles)
        raise ValueError(f"unknown profile: {profile}; available={available}")
    if not isinstance(patch, dict):
        raise ValueError(f"profile payload must be mapping: {profile}")

    return _deep_merge(payload, patch)


def _apply_env_overrides(payload: dict[str, Any], env_prefix: str) -> dict[str, Any]:
    updated = deepcopy(payload)
    prefix = env_prefix.upper()
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        suffix = key[len(prefix) :]
        parts = [part.strip().lower() for part in suffix.split("__") if part.strip()]
        if not parts:
            continue
        _set_nested_value(updated, parts, _parse_env_value(value))
    return updated


def _set_nested_value(mapping: dict[str, Any], path: list[str], value: Any) -> None:
    cursor = mapping
    for key in path[:-1]:
        child = cursor.get(key)
        if not isinstance(child, dict):
            child = {}
            cursor[key] = child
        cursor = child
    cursor[path[-1]] = value


def _parse_env_value(raw: str) -> Any:
    text = raw.strip()
    lowered = text.lower()

    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"none", "null"}:
        return None
    if text.startswith("{") or text.startswith("["):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    try:
        return int(text)
    except ValueError:
        pass

    try:
        return float(text)
    except ValueError:
        return text


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = deepcopy(value)
    return merged


def load_config(
    path: str | Path = "configs/default.yaml",
    profile: str | None = None,
    env_prefix: str | None = "ARL_",
) -> AppConfig:
    """Load application config from path/profile with env overrides."""

    return AppConfig.from_yaml_file(path, profile=profile, env_prefix=env_prefix)


def save_config(config: AppConfig, path: str | Path) -> None:
    """Persist config as YAML with stable key order."""

    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    payload = config.model_dump(mode="python")
    file_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


__all__ = [
    "AppConfig",
    "EvalConfig",
    "LLMConfig",
    "MemoryConfig",
    "RetrievalConfig",
    "RuntimeConfig",
    "ToolConfig",
    "TraceConfig",
    "list_profiles",
    "load_config",
    "resolve_config_payload",
    "save_config",
]
