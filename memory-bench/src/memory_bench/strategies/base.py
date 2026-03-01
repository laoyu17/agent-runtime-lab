from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping, MutableMapping

Message = dict[str, str]
MemoryState = dict[str, Any]
StrategyConfig = Mapping[str, Any]


class MemoryStrategy(ABC):
    """Base interface for memory strategies."""

    name: str

    @abstractmethod
    def build_context(
        self,
        history: list[Message],
        memory_state: MemoryState,
        config: StrategyConfig | None = None,
    ) -> list[Message]:
        """Build model input messages from history and memory state."""

    @abstractmethod
    def update_memory(
        self,
        turn: Message,
        response: str,
        memory_state: MemoryState,
    ) -> MemoryState:
        """Update memory state after one interaction turn."""


class StatelessStrategy(MemoryStrategy):
    """Helper for strategies that do not maintain additional memory state."""

    def update_memory(
        self,
        turn: Message,
        response: str,
        memory_state: MemoryState,
    ) -> MemoryState:
        _ = turn
        _ = response
        return dict(memory_state)


def copy_state(memory_state: MutableMapping[str, Any] | None) -> MemoryState:
    if memory_state is None:
        return {}
    return dict(memory_state)
