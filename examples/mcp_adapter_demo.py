"""Minimal MCP adapter injection example.

Run:
    python3 examples/mcp_adapter_demo.py
"""

from __future__ import annotations

import json

from agent_runtime_lab.tools import (
    RegistryBackedMCPAdapter,
    ToolRegistry,
    create_builtin_tools,
)
from agent_runtime_lab.tools.base import MCPAdapterTool
from agent_runtime_lab.types import SessionState, TaskSpec, ToolCall, ToolSpec


class _CalculatorProxyAdapter:
    """Redirect an MCP tool name to the builtin calculator implementation."""

    def __init__(self, adapter: RegistryBackedMCPAdapter) -> None:
        self._adapter = adapter

    def invoke(
        self,
        tool_name: str,
        arguments: dict[str, object],
        ctx: SessionState,
    ) -> object:
        _ = tool_name
        return self._adapter.invoke("calculator", arguments, ctx)


def main() -> None:
    registry = ToolRegistry()
    registry.register_many(create_builtin_tools())

    proxy_tool = MCPAdapterTool(
        spec=ToolSpec(
            name="mcp_calc_proxy",
            description="Example MCP proxy tool backed by builtin calculator",
            kind="mcp",
        ),
        adapter=_CalculatorProxyAdapter(RegistryBackedMCPAdapter(registry)),
    )
    registry.register(proxy_tool)

    task = TaskSpec(title="mcp-demo", objective="demo")
    session = SessionState(mode="react", task=task, goal=task.objective)
    result = registry.invoke(
        ToolCall(tool_name="mcp_calc_proxy", arguments={"expression": "6*7"}),
        session,
    )
    print(json.dumps(result.model_dump(mode="python"), ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
