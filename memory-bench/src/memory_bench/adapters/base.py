from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from memory_bench.strategies.base import Message


class ChatAdapter(ABC):
    """Adapter for different model backends."""

    name: str

    @abstractmethod
    def generate(self, messages: list[Message], *, metadata: dict[str, Any] | None = None) -> str:
        """Generate a final answer from prepared messages."""
