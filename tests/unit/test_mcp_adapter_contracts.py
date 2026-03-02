from __future__ import annotations

from agent_runtime_lab.tools import ToolRegistry, create_builtin_tools
from agent_runtime_lab.tools.mcp_adapter import (
    MCPAdapterLayer,
    MockMCPCompatibleTool,
    RegistryBackedMCPAdapter,
    ResolverBackedMCPAdapter,
)
from agent_runtime_lab.types import SessionState, TaskSpec


def _session() -> SessionState:
    task = TaskSpec(title="mcp", objective="obj")
    return SessionState(mode="react", task=task, goal=task.objective)


def test_mcp_adapter_layer_register_invoke_and_descriptors() -> None:
    layer = MCPAdapterLayer()
    tool = MockMCPCompatibleTool(name="mock_tool", fixed_response={"ok": True})

    layer.register(tool)
    descriptors = layer.list_descriptors()
    assert len(descriptors) == 1
    assert descriptors[0].name == "mock_tool"

    payload = layer.invoke("mock_tool", {"x": 1}, _session())
    assert payload["tool"] == "mock_tool"
    assert payload["response"] == {"ok": True}

    try:
        layer.register(tool)
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("expected duplicate registration error")

    try:
        layer.invoke("missing", {}, _session())
    except KeyError as exc:
        assert "not found" in str(exc)
    else:
        raise AssertionError("expected missing tool error")


def test_resolver_and_registry_backed_mcp_adapters() -> None:
    lookup = {
        "resolver_tool": MockMCPCompatibleTool(
            name="resolver_tool",
            fixed_response="ok",
        )
    }
    resolver_adapter = ResolverBackedMCPAdapter(lambda name: lookup.get(name))
    result = resolver_adapter.invoke("resolver_tool", {"k": "v"}, _session())
    assert result["response"] == "ok"

    try:
        resolver_adapter.invoke("missing", {}, _session())
    except KeyError as exc:
        assert "not found" in str(exc)
    else:
        raise AssertionError("expected missing resolver tool error")

    registry = ToolRegistry()
    registry.register_many(create_builtin_tools())
    registry_adapter = RegistryBackedMCPAdapter(registry)

    calc = registry_adapter.invoke("calculator", {"expression": "1+2"}, _session())
    assert calc["value"] == 3.0

    try:
        registry_adapter.invoke("unknown", {}, _session())
    except RuntimeError as exc:
        assert "tool not found" in str(exc)
    else:
        raise AssertionError("expected registry adapter error")
