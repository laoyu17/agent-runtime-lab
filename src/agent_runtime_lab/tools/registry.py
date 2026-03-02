"""Registry and dispatch for runtime tools."""

from __future__ import annotations

from collections.abc import Iterable

from agent_runtime_lab.tools.base import BaseTool
from agent_runtime_lab.types import SessionState, ToolCall, ToolResult, ToolSpec


class ToolRegistry:
    """Manages tool lifecycle and invocation."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def register_many(self, tools: Iterable[BaseTool]) -> None:
        for tool in tools:
            self.register(tool)

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._tools

    def list_specs(self) -> list[ToolSpec]:
        return [self._tools[name].spec for name in sorted(self._tools)]

    def list_names(self) -> list[str]:
        return sorted(self._tools)

    def invoke(self, call: ToolCall, ctx: SessionState) -> ToolResult:
        tool = self.get(call.tool_name)
        if tool is None:
            return ToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                success=False,
                output=None,
                error=f"tool not found: {call.tool_name}",
                latency_ms=0,
            )
        return tool.invoke(call, ctx)


__all__ = ["ToolRegistry"]
