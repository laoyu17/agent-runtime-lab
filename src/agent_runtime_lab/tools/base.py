"""Tool abstractions for local/http/mcp-style execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from time import perf_counter
from typing import Any, Protocol

from agent_runtime_lab.types import SessionState, ToolCall, ToolResult, ToolSpec

ToolHandler = Callable[[dict[str, Any], SessionState], Any]


class HTTPRequester(Protocol):
    """Callable contract for HTTP tool execution."""

    def __call__(self, url: str, payload: dict[str, Any], timeout_ms: int) -> Any: ...


class MCPAdapter(Protocol):
    """Minimal MCP-style adapter contract."""

    def invoke(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        ctx: SessionState,
    ) -> Any: ...


class ToolExecutionError(RuntimeError):
    """Raised when a tool cannot be executed with current configuration."""


class BaseTool(ABC):
    """Common tool lifecycle with consistent result envelope."""

    def __init__(self, spec: ToolSpec) -> None:
        self.spec = spec

    @property
    def name(self) -> str:
        return self.spec.name

    def invoke(self, call: ToolCall, ctx: SessionState) -> ToolResult:
        started = perf_counter()
        output: Any = None
        error: str | None = None
        success = True
        try:
            output = self._invoke(call.arguments, ctx)
        except Exception as exc:  # noqa: BLE001
            success = False
            error = str(exc)
        latency_ms = max(0, int((perf_counter() - started) * 1000))
        return ToolResult(
            call_id=call.call_id,
            tool_name=self.name,
            success=success,
            output=output,
            error=error,
            latency_ms=latency_ms,
            metadata={"kind": self.spec.kind},
        )

    @abstractmethod
    def _invoke(self, arguments: dict[str, Any], ctx: SessionState) -> Any:
        """Execute tool-specific logic and return raw output."""


class FunctionTool(BaseTool):
    """In-process function tool."""

    def __init__(self, spec: ToolSpec, handler: ToolHandler) -> None:
        super().__init__(spec)
        self._handler = handler

    def _invoke(self, arguments: dict[str, Any], ctx: SessionState) -> Any:
        return self._handler(arguments, ctx)


class HTTPTool(BaseTool):
    """HTTP-backed tool with injectable requester."""

    def __init__(
        self,
        spec: ToolSpec,
        endpoint: str,
        requester: HTTPRequester | None = None,
    ) -> None:
        super().__init__(spec)
        self.endpoint = endpoint
        self._requester = requester or self._default_requester

    @staticmethod
    def _default_requester(url: str, payload: dict[str, Any], timeout_ms: int) -> Any:
        raise ToolExecutionError(
            "HTTP requester is not configured; provide requester callable"
        )

    def _invoke(self, arguments: dict[str, Any], ctx: SessionState) -> Any:
        url = str(arguments.get("url") or self.endpoint).strip()
        if not url:
            raise ToolExecutionError("http tool requires non-empty url")
        payload = dict(arguments)
        payload.pop("url", None)
        result = self._requester(url, payload, self.spec.timeout_ms)
        return {"url": url, "result": result}


class MCPAdapterTool(BaseTool):
    """MCP-style adapter wrapper."""

    def __init__(self, spec: ToolSpec, adapter: MCPAdapter) -> None:
        super().__init__(spec)
        self._adapter = adapter

    def _invoke(self, arguments: dict[str, Any], ctx: SessionState) -> Any:
        return self._adapter.invoke(self.name, arguments, ctx)


__all__ = [
    "BaseTool",
    "FunctionTool",
    "HTTPRequester",
    "HTTPTool",
    "MCPAdapter",
    "MCPAdapterTool",
    "ToolExecutionError",
    "ToolHandler",
]
