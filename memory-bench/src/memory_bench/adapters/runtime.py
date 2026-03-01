from __future__ import annotations

from typing import Any

from memory_bench.adapters.base import ChatAdapter
from memory_bench.adapters.mock import MockAdapter
from memory_bench.strategies.base import Message


class RuntimeAdapter(ChatAdapter):
    """Runtime adapter placeholder for agent-runtime-lab integration.

    v0.1 uses deterministic fallback behavior to keep evaluation runnable.
    """

    name = "runtime"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        _ = config
        self._fallback = MockAdapter()

    def generate(self, messages: list[Message], *, metadata: dict[str, Any] | None = None) -> str:
        return self._fallback.generate(messages, metadata=metadata)
