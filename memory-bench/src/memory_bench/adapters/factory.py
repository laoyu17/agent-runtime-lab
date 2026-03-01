from __future__ import annotations

from typing import Any

from memory_bench.adapters.base import ChatAdapter
from memory_bench.adapters.mock import MockAdapter
from memory_bench.adapters.openai import OpenAICompatibleAdapter
from memory_bench.adapters.runtime import RuntimeAdapter


def create_adapter(name: str, config: dict[str, Any] | None = None) -> ChatAdapter:
    cfg = config or {}
    if name == "mock":
        return MockAdapter()
    if name == "openai":
        return OpenAICompatibleAdapter.from_config(cfg)
    if name == "runtime":
        return RuntimeAdapter(cfg)
    raise ValueError(f"unsupported adapter: {name}")
