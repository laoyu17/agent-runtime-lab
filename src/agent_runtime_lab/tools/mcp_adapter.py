"""MCP-compatible adapter layer with swappable backends."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from agent_runtime_lab.tools.registry import ToolRegistry
from agent_runtime_lab.types import SessionState, ToolCall


class MCPCompatibleTool(Protocol):
    """Protocol for MCP-compatible tool implementations."""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]

    def invoke(self, arguments: dict[str, Any], ctx: SessionState) -> Any:
        """Execute tool and return payload."""


@dataclass(slots=True)
class MCPToolDescriptor:
    """Lightweight descriptor exposed to MCP clients."""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


@dataclass(slots=True)
class MockMCPCompatibleTool:
    """Simple deterministic MCP-compatible mock tool."""

    name: str
    fixed_response: Any = field(default_factory=dict)
    description: str = "mock mcp tool"
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)

    def invoke(self, arguments: dict[str, Any], ctx: SessionState) -> Any:
        return {
            "tool": self.name,
            "session_id": ctx.session_id,
            "arguments": arguments,
            "response": self.fixed_response,
        }


class MCPAdapterLayer:
    """In-memory MCP adapter registry."""

    def __init__(self, tools: Iterable[MCPCompatibleTool] | None = None) -> None:
        self._tools: dict[str, MCPCompatibleTool] = {}
        if tools:
            self.register_many(tools)

    def register(self, tool: MCPCompatibleTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"mcp tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def register_many(self, tools: Iterable[MCPCompatibleTool]) -> None:
        for tool in tools:
            self.register(tool)

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def list_descriptors(self) -> list[MCPToolDescriptor]:
        return [
            MCPToolDescriptor(
                name=tool.name,
                description=tool.description,
                input_schema=dict(tool.input_schema),
                output_schema=dict(tool.output_schema),
            )
            for tool in self._tools.values()
        ]

    def invoke(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        ctx: SessionState,
    ) -> Any:
        tool = self._tools.get(tool_name)
        if tool is None:
            raise KeyError(f"mcp tool not found: {tool_name}")
        return tool.invoke(arguments, ctx)


class ResolverBackedMCPAdapter:
    """MCP adapter that resolves tool implementations at invocation time."""

    def __init__(
        self,
        resolver: Callable[[str], MCPCompatibleTool | None],
    ) -> None:
        self._resolver = resolver

    def invoke(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        ctx: SessionState,
    ) -> Any:
        tool = self._resolver(tool_name)
        if tool is None:
            raise KeyError(f"mcp tool not found: {tool_name}")
        return tool.invoke(arguments, ctx)


class RegistryBackedMCPAdapter:
    """MCP adapter that reuses existing ToolRegistry implementations."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def invoke(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        ctx: SessionState,
    ) -> Any:
        result = self._registry.invoke(
            ToolCall(tool_name=tool_name, arguments=arguments),
            ctx,
        )
        if not result.success:
            raise RuntimeError(result.error or "tool invocation failed")
        return result.output


__all__ = [
    "MCPAdapterLayer",
    "MCPCompatibleTool",
    "MCPToolDescriptor",
    "MockMCPCompatibleTool",
    "RegistryBackedMCPAdapter",
    "ResolverBackedMCPAdapter",
]
