"""Builtin tools for v0.1 runtime bootstrap."""

from __future__ import annotations

import ast
import operator
import re
from typing import Any

from agent_runtime_lab.tools.base import BaseTool, FunctionTool
from agent_runtime_lab.types import SessionState, ToolSpec

_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_\u4e00-\u9fff]+")


def _normalize_tokens(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN_PATTERN.findall(text)}


def _search_docs(arguments: dict[str, Any], ctx: SessionState) -> dict[str, Any]:
    query = str(arguments.get("query", "")).strip()
    if not query:
        return {"query": query, "matches": []}

    raw_docs = arguments.get("docs")
    docs: list[str]
    if isinstance(raw_docs, list):
        docs = [str(item) for item in raw_docs]
    else:
        docs = list(ctx.task.context)

    top_k_raw = arguments.get("top_k", 3)
    try:
        top_k = max(1, int(top_k_raw))
    except (TypeError, ValueError):
        top_k = 3

    query_terms = _normalize_tokens(query)
    scored: list[tuple[int, int, str]] = []
    for index, text in enumerate(docs):
        overlap = len(_normalize_tokens(text) & query_terms)
        if overlap > 0:
            scored.append((overlap, index, text))

    scored.sort(key=lambda item: (-item[0], item[1]))
    matches = [
        {
            "rank": rank,
            "doc_index": index,
            "score": score,
            "text": text,
        }
        for rank, (score, index, text) in enumerate(scored[:top_k], start=1)
    ]
    return {"query": query, "matches": matches}


_BINARY_OPS: dict[type[ast.operator], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS: dict[type[ast.unaryop], Any] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _eval_expr(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_expr(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp):
        fn = _UNARY_OPS.get(type(node.op))
        if fn is None:
            raise ValueError("unsupported unary operator")
        return float(fn(_eval_expr(node.operand)))
    if isinstance(node, ast.BinOp):
        fn = _BINARY_OPS.get(type(node.op))
        if fn is None:
            raise ValueError("unsupported binary operator")
        return float(fn(_eval_expr(node.left), _eval_expr(node.right)))
    raise ValueError("unsafe expression")


def _calculator(arguments: dict[str, Any], ctx: SessionState) -> dict[str, Any]:
    _ = ctx
    expression = str(arguments.get("expression") or arguments.get("expr") or "").strip()
    if not expression:
        raise ValueError("calculator requires expression")
    tree = ast.parse(expression, mode="eval")
    value = _eval_expr(tree)
    return {"expression": expression, "value": value}


def _web_fetch_mock(arguments: dict[str, Any], ctx: SessionState) -> dict[str, Any]:
    _ = ctx
    url = str(arguments.get("url", "")).strip()
    if not url:
        raise ValueError("web_fetch_mock requires url")

    raw_fixtures = arguments.get("fixtures")
    fixtures: dict[str, str]
    if isinstance(raw_fixtures, dict):
        fixtures = {str(key): str(value) for key, value in raw_fixtures.items()}
    else:
        fixtures = {
            "https://example.com": "<html><title>Example Domain</title></html>",
            "https://docs.local/runtime": "Runtime docs mock page",
        }

    content = fixtures.get(url)
    found = content is not None
    return {
        "url": url,
        "status_code": 200 if found else 404,
        "content": content or "",
        "found": found,
    }


def create_builtin_tools() -> list[BaseTool]:
    """Return v0.1 baseline builtin tools."""

    return [
        FunctionTool(
            spec=ToolSpec(
                name="search_docs",
                description="Search context documents by token overlap",
                kind="local",
            ),
            handler=_search_docs,
        ),
        FunctionTool(
            spec=ToolSpec(
                name="calculator",
                description="Evaluate basic arithmetic expressions",
                kind="local",
            ),
            handler=_calculator,
        ),
        FunctionTool(
            spec=ToolSpec(
                name="web_fetch_mock",
                description="Fetch pre-defined web content without real network access",
                kind="mock",
            ),
            handler=_web_fetch_mock,
        ),
    ]


__all__ = ["create_builtin_tools"]
