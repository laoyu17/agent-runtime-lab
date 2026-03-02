"""Step executor for runtime loops."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from agent_runtime_lab.reliability import ReliabilityManager, RetryPolicy
from agent_runtime_lab.tools import ToolRegistry, create_builtin_tools
from agent_runtime_lab.types import (
    ExecutionStep,
    PlanNode,
    SessionState,
    ToolCall,
    ToolResult,
)
from agent_runtime_lab.validators import ConstraintValidator

_MATH_PATTERN = re.compile(r"\d+(?:\.\d+)?\s*[+\-*/%]\s*\d+(?:\.\d+)?")
_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)


class Executor:
    """Executes one runtime step and updates session state."""

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        reliability_manager: ReliabilityManager | None = None,
    ) -> None:
        if tool_registry is None:
            registry = ToolRegistry()
            registry.register_many(create_builtin_tools())
            self.tool_registry = registry
        else:
            self.tool_registry = tool_registry
        self.reliability_manager = reliability_manager
        self._constraint_validator = ConstraintValidator()

    def bind_runtime_dependencies(
        self,
        *,
        tool_registry: ToolRegistry | None = None,
        reliability_manager: ReliabilityManager | None = None,
    ) -> None:
        if tool_registry is not None:
            self.tool_registry = tool_registry
        if reliability_manager is not None:
            self.reliability_manager = reliability_manager

    def execute(self, session: SessionState, node: PlanNode | None) -> ExecutionStep:
        started = perf_counter()
        thought = node.description.strip() if node else session.goal.strip()
        retrieval_hint = ""
        if node is not None:
            raw_hint = node.metadata.get("retrieval_hint")
            if isinstance(raw_hint, str):
                retrieval_hint = raw_hint.strip()
        reasoning_input = (
            thought if not retrieval_hint else f"{thought}\n{retrieval_hint}"
        )
        selected_tool = self._select_tool(session, node, reasoning_input)

        tool_call: ToolCall | None = None
        tool_result: ToolResult | None = None
        tool_meta: dict[str, Any] = {}
        policy_meta: dict[str, Any] | None = None
        success = True
        state_update = "step_completed"

        if selected_tool is not None:
            arguments = self._build_arguments(selected_tool, session, reasoning_input)
            if self._should_block_tool_call(session, selected_tool):
                success = False
                state_update = "policy_blocked_no_network"
                policy_meta = {
                    "blocked": True,
                    "policy": "no_network",
                    "tool_name": selected_tool,
                    "arguments": arguments,
                }
            else:
                tool_call = ToolCall(tool_name=selected_tool, arguments=arguments)
                tool_result, tool_meta = self._invoke_tool(tool_call, session)
                session.tool_results.append(tool_result)
                success = tool_result.success
                state_update = "tool_step_completed" if success else "tool_step_failed"

        if state_update == "policy_blocked_no_network":
            observation = self._build_policy_blocked_observation(thought, selected_tool)
        else:
            observation = self._build_observation(
                thought=thought,
                selected_tool=selected_tool,
                tool_result=tool_result,
            )
        latency_ms = max(0, int((perf_counter() - started) * 1000))
        token_estimate = self._estimate_tokens(thought, observation)

        metadata: dict[str, Any] = {}
        if tool_meta:
            metadata["tool_execution"] = tool_meta
        if policy_meta is not None:
            metadata["policy"] = policy_meta
        if retrieval_hint:
            metadata["retrieval_hint"] = retrieval_hint

        step = ExecutionStep(
            plan_step_id=node.step_id if node else None,
            thought_summary=thought,
            selected_tool=selected_tool,
            tool_call=tool_call,
            tool_result=tool_result,
            observation=observation,
            state_update=state_update,
            success=success,
            latency_ms=latency_ms,
            token_estimate=token_estimate,
            metadata=metadata,
        )

        session.current_step += 1
        session.history.append(step)
        session.interim_conclusions.append(
            self._build_conclusion(thought, selected_tool, tool_result)
        )
        session.updated_at = datetime.now(tz=UTC)
        return step

    def _should_block_tool_call(self, session: SessionState, tool_name: str) -> bool:
        if not self._constraint_validator.has_no_network_constraint(
            session.constraints
        ):
            return False
        return self._is_network_tool(tool_name)

    def _is_network_tool(self, tool_name: str) -> bool:
        tool = self.tool_registry.get(tool_name)
        if tool is not None:
            if tool.spec.allow_network or tool.spec.kind == "http":
                return True
            return tool_name == "web_fetch_mock"

        if tool_name == "web_fetch_mock":
            return True
        lowered = tool_name.lower()
        return ("web" in lowered and "fetch" in lowered) or "http" in lowered

    def _invoke_tool(
        self,
        tool_call: ToolCall,
        session: SessionState,
    ) -> tuple[ToolResult, dict[str, Any]]:
        if self.reliability_manager is None:
            return self.tool_registry.invoke(tool_call, session), {}

        tool = self.tool_registry.get(tool_call.tool_name)
        timeout_ms = tool.spec.timeout_ms if tool is not None else None

        retry_policy = None
        if tool is not None:
            base_policy = self.reliability_manager.retry_policy
            retry_policy = RetryPolicy(
                max_retries=max(0, tool.spec.retry),
                base_delay_ms=base_policy.base_delay_ms,
                backoff_factor=base_policy.backoff_factor,
                max_delay_ms=base_policy.max_delay_ms,
                timeout_ms=timeout_ms,
            )

        outcome = self.reliability_manager.execute(
            lambda: self.tool_registry.invoke(tool_call, session),
            timeout_ms=timeout_ms,
            retry_policy=retry_policy,
        )
        execution_meta = {
            "attempts": outcome.attempts,
            "used_fallback": outcome.used_fallback,
            "timed_out": outcome.timed_out,
        }

        if outcome.success and isinstance(outcome.value, ToolResult):
            result = outcome.value.model_copy(deep=True)
            result.metadata = {**result.metadata, **execution_meta}
            return result, execution_meta

        failed_result = ToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            success=False,
            output=None,
            error=outcome.error or "tool_execution_failed",
            metadata=execution_meta,
            latency_ms=0,
        )
        return failed_result, execution_meta

    def _select_tool(
        self,
        session: SessionState,
        node: PlanNode | None,
        thought: str,
    ) -> str | None:
        if node is None:
            # ReAct mode: keep global objective context for broad tool matching.
            text = " ".join([session.goal, session.task.objective, thought]).lower()
        else:
            # Plan-Execute mode: prioritize the current node semantics.
            text = " ".join([node.title, thought]).lower()

        if _URL_PATTERN.search(text) or any(
            keyword in text
            for keyword in ("fetch", "web", "url", "http", "网页", "网站")
        ):
            return "web_fetch_mock"

        if _MATH_PATTERN.search(text) or any(
            keyword in text
            for keyword in (
                "calculator",
                "calculate",
                "arithmetic",
                "math",
                "compute",
                "计算",
            )
        ):
            return "calculator"

        if session.task.context and any(
            keyword in text
            for keyword in (
                "search",
                "docs",
                "document",
                "context",
                "retrieve",
                "检索",
                "文档",
            )
        ):
            return "search_docs"

        return None

    def _build_arguments(
        self,
        tool_name: str,
        session: SessionState,
        thought: str,
    ) -> dict[str, Any]:
        if tool_name == "calculator":
            expression = self._extract_expression(thought)
            return {"expression": expression}

        if tool_name == "search_docs":
            return {
                "query": thought or session.task.objective,
                "docs": list(session.task.context),
                "top_k": 3,
            }

        if tool_name == "web_fetch_mock":
            match = _URL_PATTERN.search(thought)
            url = match.group(0) if match else "https://example.com"
            return {"url": url}

        return {}

    @staticmethod
    def _extract_expression(text: str) -> str:
        match = _MATH_PATTERN.search(text)
        if match:
            return match.group(0)
        return "1+1"

    @staticmethod
    def _build_observation(
        *,
        thought: str,
        selected_tool: str | None,
        tool_result: ToolResult | None,
    ) -> str:
        payload: dict[str, Any] = {
            "status": "ok",
            "thought": thought,
            "selected_tool": selected_tool,
        }

        if tool_result is not None:
            payload["status"] = "ok" if tool_result.success else "error"
            payload["tool_output"] = tool_result.output
            payload["tool_error"] = tool_result.error

        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _build_policy_blocked_observation(
        thought: str,
        selected_tool: str | None,
    ) -> str:
        _ = thought
        return json.dumps(
            {
                "status": "error",
                "message": "tool call blocked by policy",
                "selected_tool": selected_tool,
                "tool_error": "policy_blocked_no_network",
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _build_conclusion(
        thought: str,
        selected_tool: str | None,
        tool_result: ToolResult | None,
    ) -> str:
        if selected_tool is None:
            return thought

        if tool_result is None:
            return f"tool={selected_tool} no result"

        status = "ok" if tool_result.success else "error"
        detail = tool_result.error if tool_result.error else str(tool_result.output)
        return f"tool={selected_tool} status={status} detail={detail}"

    @staticmethod
    def _estimate_tokens(thought: str, observation: str) -> int:
        text = f"{thought} {observation}".strip()
        if not text:
            return 0
        return max(1, len(text) // 4)


__all__ = ["Executor"]
