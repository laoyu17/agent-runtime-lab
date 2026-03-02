from __future__ import annotations

from agent_runtime_lab.memory import (
    ConstraintExtractor,
    MemoryManager,
    ShortTermMemory,
)
from agent_runtime_lab.retrieval import (
    Retriever,
    SimpleVectorizer,
    chunk_text,
    inject_context,
)
from agent_runtime_lab.session import SessionStore
from agent_runtime_lab.tools.base import FunctionTool, HTTPTool, MCPAdapterTool
from agent_runtime_lab.tools.builtin import create_builtin_tools
from agent_runtime_lab.tools.registry import ToolRegistry
from agent_runtime_lab.types import (
    ExecutionStep,
    SessionState,
    TaskSpec,
    ToolCall,
    ToolSpec,
)


def _session() -> SessionState:
    task = TaskSpec(title="task", objective="obj", constraints=["must json"])
    return SessionState(
        mode="react",
        task=task,
        goal=task.objective,
        constraints=task.constraints,
    )


def test_function_tool_success_and_error() -> None:
    session = _session()
    tool = FunctionTool(
        spec=ToolSpec(name="echo", description="echo"),
        handler=lambda args, ctx: {"value": args["x"] + len(ctx.goal)},
    )

    result = tool.invoke(ToolCall(tool_name="echo", arguments={"x": 2}), session)
    assert result.success is True
    assert result.output == {"value": 5}

    bad_tool = FunctionTool(
        spec=ToolSpec(name="boom", description="boom"),
        handler=lambda args, ctx: (_ for _ in ()).throw(ValueError("bad")),
    )
    bad_result = bad_tool.invoke(ToolCall(tool_name="boom", arguments={}), session)
    assert bad_result.success is False
    assert bad_result.error == "bad"


def test_http_tool_and_mcp_adapter_tool() -> None:
    session = _session()

    http_tool = HTTPTool(
        spec=ToolSpec(name="http", description="http", kind="http", timeout_ms=1234),
        endpoint="https://default.local",
        requester=lambda url, payload, timeout_ms: {
            "url": url,
            "payload": payload,
            "timeout": timeout_ms,
        },
    )
    http_result = http_tool.invoke(
        ToolCall(tool_name="http", arguments={"q": "x"}),
        session,
    )
    assert http_result.success is True
    assert http_result.output == {
        "url": "https://default.local",
        "result": {
            "url": "https://default.local",
            "payload": {"q": "x"},
            "timeout": 1234,
        },
    }

    class _Adapter:
        def invoke(
            self,
            tool_name: str,
            arguments: dict[str, object],
            ctx: SessionState,
        ) -> object:
            return {"tool": tool_name, "args": arguments, "goal": ctx.goal}

    mcp_tool = MCPAdapterTool(
        spec=ToolSpec(name="mcp_tool", description="mcp", kind="mcp"),
        adapter=_Adapter(),
    )
    mcp_result = mcp_tool.invoke(
        ToolCall(tool_name="mcp_tool", arguments={"k": "v"}),
        session,
    )
    assert mcp_result.success is True
    assert mcp_result.output == {
        "tool": "mcp_tool",
        "args": {"k": "v"},
        "goal": "obj",
    }


def test_http_tool_default_requester_and_missing_url_error() -> None:
    session = _session()

    default_http = HTTPTool(
        spec=ToolSpec(name="http", description="http", kind="http"),
        endpoint="https://a",
    )
    default_result = default_http.invoke(
        ToolCall(tool_name="http", arguments={}),
        session,
    )
    assert default_result.success is False
    assert "HTTP requester is not configured" in (default_result.error or "")

    missing_url = HTTPTool(
        spec=ToolSpec(name="http2", description="http", kind="http"),
        endpoint="",
        requester=lambda url, payload, timeout_ms: None,
    )
    missing_result = missing_url.invoke(
        ToolCall(tool_name="http2", arguments={"url": ""}),
        session,
    )
    assert missing_result.success is False
    assert "non-empty url" in (missing_result.error or "")


def test_tool_registry_lifecycle_and_missing_tool() -> None:
    registry = ToolRegistry()
    registry.register_many(create_builtin_tools())

    assert registry.has("calculator") is True
    assert "search_docs" in registry.list_names()
    assert len(registry.list_specs()) == 3

    missing = registry.invoke(ToolCall(tool_name="missing", arguments={}), _session())
    assert missing.success is False
    assert "tool not found" in (missing.error or "")

    registry.unregister("calculator")
    assert registry.has("calculator") is False


def test_tool_registry_rejects_duplicate_registration() -> None:
    registry = ToolRegistry()
    tool = FunctionTool(
        spec=ToolSpec(name="dup", description="dup"),
        handler=lambda args, ctx: None,
    )
    registry.register(tool)

    try:
        registry.register(tool)
    except ValueError as exc:
        assert "tool already registered" in str(exc)
    else:
        raise AssertionError("expected ValueError for duplicate registration")


def test_builtin_tools_behaviors() -> None:
    registry = ToolRegistry()
    registry.register_many(create_builtin_tools())

    session = _session()
    session.task.context = ["alpha beta", "beta gamma", "delta"]

    search = registry.invoke(
        ToolCall(tool_name="search_docs", arguments={"query": "beta", "top_k": 2}),
        session,
    )
    assert search.success is True
    assert len(search.output["matches"]) == 2

    calc = registry.invoke(
        ToolCall(tool_name="calculator", arguments={"expression": "2*(3+4)"}),
        session,
    )
    assert calc.success is True
    assert calc.output["value"] == 14.0

    bad_calc = registry.invoke(ToolCall(tool_name="calculator", arguments={}), session)
    assert bad_calc.success is False

    fetch = registry.invoke(
        ToolCall(tool_name="web_fetch_mock", arguments={"url": "https://example.com"}),
        session,
    )
    assert fetch.success is True
    assert fetch.output["status_code"] == 200


def test_short_term_memory_and_memory_manager_sync() -> None:
    memory = ShortTermMemory(window_size=2)
    memory.add("a")
    memory.add("b")
    memory.add("c")
    assert memory.recent() == ["b", "c"]
    assert memory.summarize(max_chars=100) == "b | c"

    try:
        memory.summarize(max_chars=3)
    except ValueError as exc:
        assert "max_chars" in str(exc)
    else:
        raise AssertionError("expected ValueError for invalid max_chars")

    extractor = ConstraintExtractor()
    constraints = extractor.extract(
        ["must json", "hello", "必须 输出 yaml", "must json"]
    )
    assert constraints == ["must json", "必须 输出 yaml"]

    manager = MemoryManager(summary_window=3)
    session = _session()
    session.history.append(
        ExecutionStep(
            thought_summary="step one",
            observation='{"ok":true}',
            state_update="s1",
        )
    )
    session.interim_conclusions.extend(["must keep json", "other note"])

    snapshot = manager.sync(session)
    assert snapshot.summary
    assert "must keep json" in snapshot.retained_constraints
    assert session.memory_summary == snapshot.summary


def test_short_term_memory_window_validation() -> None:
    try:
        ShortTermMemory(window_size=0)
    except ValueError as exc:
        assert "window_size" in str(exc)
    else:
        raise AssertionError("expected ValueError for invalid window_size")


def test_session_store_lifecycle() -> None:
    store = SessionStore()
    task = TaskSpec(title="demo", objective="obj")
    store.create(task=task, mode="react", session_id="s1")

    assert store.get("s1") is not None
    assert store.list_session_ids() == ["s1"]

    step = ExecutionStep(thought_summary="do", state_update="done")
    store.append_step("s1", step)
    assert store.require("s1").history[0].thought_summary == "do"

    registry = ToolRegistry()
    registry.register_many(create_builtin_tools())
    call = ToolCall(tool_name="calculator", arguments={"expression": "1+1"})
    result = registry.invoke(call, store.require("s1"))
    store.append_tool_result("s1", result)
    store.append_conclusion("s1", "good")
    store.set_memory_summary("s1", "summary")

    dumped = store.dump("s1")
    assert dumped["session_id"] == "s1"
    assert dumped["memory_summary"] == "summary"

    store.append_error("s1", "bad")
    assert store.require("s1").status == "failed"

    try:
        store.require("unknown")
    except KeyError as exc:
        assert "session not found" in str(exc)
    else:
        raise AssertionError("expected KeyError for unknown session")


def test_retrieval_chunk_vector_search_and_inject() -> None:
    assert chunk_text("abcdefghij", chunk_size=4) == ["abcd", "efgh", "ij"]

    try:
        chunk_text("x", chunk_size=0)
    except ValueError as exc:
        assert "chunk_size" in str(exc)
    else:
        raise AssertionError("expected ValueError for invalid chunk size")

    vectorizer = SimpleVectorizer()
    vec = vectorizer.vectorize("alpha beta alpha")
    assert vec["alpha"] == 2.0
    assert vec["beta"] == 1.0

    retriever = Retriever(chunk_size=10, top_k=2)
    added = retriever.ingest(["alpha beta", "beta gamma", "delta"], source_prefix="ctx")
    assert added == 3

    hits = retriever.search("beta")
    assert len(hits) == 2
    assert all(hit.score > 0 for hit in hits)

    prompt = inject_context("question", hits)
    assert "[Retrieved Context]" in prompt
    assert "score=" in prompt

    retriever.clear()
    assert retriever.search("beta") == []


def test_retriever_top_k_validation() -> None:
    try:
        Retriever(top_k=0)
    except ValueError as exc:
        assert "top_k" in str(exc)
    else:
        raise AssertionError("expected ValueError for invalid top_k")
