"""Runtime loop implementations."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from agent_runtime_lab.critic import Critic, CriticDecision
from agent_runtime_lab.executor import Executor
from agent_runtime_lab.memory import MemoryManager
from agent_runtime_lab.reliability import ReliabilityManager
from agent_runtime_lab.retrieval import Retriever
from agent_runtime_lab.types import ExecutionStep, PlanNode, SessionState
from agent_runtime_lab.validators import (
    ConstraintValidator,
    OutputValidator,
    ValidationResult,
)


class _BaseLoop:
    def __init__(
        self,
        executor: Executor,
        critic: Critic,
        max_steps: int,
        reliability_manager: ReliabilityManager | None = None,
        memory_manager: MemoryManager | None = None,
        retriever: Retriever | None = None,
        output_validator: OutputValidator | None = None,
    ) -> None:
        self.executor = executor
        self.critic = critic
        self.max_steps = max_steps
        self.reliability_manager = reliability_manager
        self.memory_manager = memory_manager
        self.retriever = retriever
        self.output_validator = output_validator
        self._constraint_validator = ConstraintValidator()

    def _execute_once(
        self,
        session: SessionState,
        steps: list[ExecutionStep],
        node: PlanNode | None,
    ) -> bool:
        if not self._guard_step_budget(session):
            if node is not None:
                node.status = "failed"
            return False

        if node is not None:
            node.status = "in_progress"

        query = node.description if node is not None else session.goal
        retrieval_evidence = self._collect_retrieval_evidence(query)

        step = self.executor.execute(session, node)
        steps.append(step)

        if retrieval_evidence:
            step.metadata["retrieval"] = {
                "query": query,
                "hits": retrieval_evidence,
            }

        if not self._guard_repeat_tool_call(session, step):
            if node is not None:
                node.status = "failed"
            return False

        validation_result = self._validate_output(session, step)
        step.metadata["validation"] = {
            "passed": validation_result.passed,
            "errors": list(validation_result.errors),
            "warnings": list(validation_result.warnings),
        }
        if not validation_result.passed:
            if node is not None:
                node.status = "failed"
            session.status = "failed"
            return False

        self._sync_memory(session, step)

        decision: CriticDecision = self.critic.review(session, step)
        success = step.success and decision.proceed
        if node is not None:
            node.status = "completed" if success else "failed"

        if not decision.proceed:
            session.status = "failed"
            return False
        return True

    def _append_summary_step(
        self,
        session: SessionState,
        steps: list[ExecutionStep],
    ) -> bool:
        if not self._guard_step_budget(session):
            return False

        summary_payload = {
            "status": "ok",
            "summary": session.interim_conclusions[-3:],
            "steps": session.current_step,
            "tool_results": len(session.tool_results),
            "memory": session.memory_summary,
        }
        observation = json.dumps(summary_payload, ensure_ascii=False)
        token_estimate = max(1, len(observation) // 4)

        step = ExecutionStep(
            thought_summary=(
                "Summarize prior execution and provide final JSON response."
            ),
            selected_tool=None,
            observation=observation,
            state_update="summary_completed",
            success=True,
            latency_ms=0,
            token_estimate=token_estimate,
        )

        session.current_step += 1
        session.history.append(step)
        session.interim_conclusions.append(step.thought_summary)
        session.updated_at = datetime.now(tz=UTC)
        steps.append(step)

        validation_result = self._validate_output(session, step)
        step.metadata["validation"] = {
            "passed": validation_result.passed,
            "errors": list(validation_result.errors),
            "warnings": list(validation_result.warnings),
        }
        if not validation_result.passed:
            session.status = "failed"
            return False

        self._sync_memory(session, step)

        decision = self.critic.review(session, step)
        if not decision.proceed:
            session.status = "failed"
            return False
        return True

    def _guard_step_budget(self, session: SessionState) -> bool:
        if self.reliability_manager is None:
            return True

        decision = self.reliability_manager.should_stop_for_steps(session.current_step)
        if decision.stop:
            session.error_log.append(decision.reason or "max_steps_exceeded")
            session.status = "failed"
            return False
        return True

    def _guard_repeat_tool_call(
        self,
        session: SessionState,
        step: ExecutionStep,
    ) -> bool:
        if self.reliability_manager is None or step.tool_call is None:
            return True

        decision = self.reliability_manager.should_stop_for_repeat_call(
            step.tool_call.tool_name,
            step.tool_call.arguments,
        )
        if not decision.stop:
            return True

        step.success = False
        step.state_update = "repeat_call_detected"
        step.metadata["reliability"] = {
            "repeat_call_detected": True,
            "reason": decision.reason or "repeat_call_detected",
        }
        session.error_log.append(decision.reason or "repeat_call_detected")
        session.status = "failed"
        return False

    def _validate_output(
        self,
        session: SessionState,
        step: ExecutionStep,
    ) -> ValidationResult:
        if self.output_validator is None:
            return ValidationResult(passed=True)

        text = (step.observation or "").strip()
        payload: Any = text
        if text:
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = text

        result = self.output_validator.validate(
            payload=payload,
            text=text,
            constraints=session.constraints,
        )
        if self._tool_call_violates_no_network(session, step):
            result.add_error("constraint violated: no network tool call")
        if result.passed:
            return result

        step.success = False
        step.state_update = f"{step.state_update}|validation_failed"
        for error in result.errors:
            self._append_error_once(session, f"validation:{error}")
        return result

    def _tool_call_violates_no_network(
        self,
        session: SessionState,
        step: ExecutionStep,
    ) -> bool:
        if step.tool_call is None:
            return False
        if not self._constraint_validator.has_no_network_constraint(
            session.constraints
        ):
            return False

        tool_name = step.tool_call.tool_name
        registry = getattr(self.executor, "tool_registry", None)
        if registry is not None and hasattr(registry, "get"):
            tool = registry.get(tool_name)
            if tool is not None:
                if tool.spec.allow_network or tool.spec.kind == "http":
                    return True
                return tool_name == "web_fetch_mock"

        if tool_name == "web_fetch_mock":
            return True
        lowered = tool_name.lower()
        return "web" in lowered and "fetch" in lowered

    @staticmethod
    def _append_error_once(session: SessionState, error: str) -> None:
        if error not in session.error_log:
            session.error_log.append(error)

    def _collect_retrieval_evidence(self, query: str) -> list[dict[str, Any]]:
        if self.retriever is None or not query.strip():
            return []

        hits = self.retriever.search(query)
        evidence: list[dict[str, Any]] = []
        for hit in hits:
            evidence.append(
                {
                    "chunk_id": hit.chunk_id,
                    "source": hit.source,
                    "score": round(hit.score, 6),
                }
            )
        return evidence

    def _sync_memory(self, session: SessionState, step: ExecutionStep) -> None:
        if self.memory_manager is None:
            return

        snapshot = self.memory_manager.sync(session)
        step.metadata["memory"] = {
            "summary": snapshot.summary,
            "retained_constraints": snapshot.retained_constraints,
            "compressed_history": snapshot.compressed_history,
            "compressed_tool_results": snapshot.compressed_tool_results,
        }


class ReActLoop(_BaseLoop):
    @staticmethod
    def _is_structured_json(text: str | None) -> bool:
        if not text:
            return False
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return False
        return isinstance(parsed, (dict, list))

    @classmethod
    def _should_finalize_after_step(cls, step: ExecutionStep) -> bool:
        if not step.success:
            return False
        validation_meta = step.metadata.get("validation")
        if isinstance(validation_meta, dict) and not bool(
            validation_meta.get("passed")
        ):
            return False
        if step.selected_tool is not None:
            return True
        return cls._is_structured_json(step.observation)

    def run(self, session: SessionState) -> list[ExecutionStep]:
        steps: list[ExecutionStep] = []
        action_budget = self.max_steps if self.max_steps <= 1 else self.max_steps - 1

        for index in range(action_budget):
            node = PlanNode(
                title=f"react-{index + 1}",
                description=(
                    session.goal if index == 0 else "Continue solving the task."
                ),
            )
            if not self._execute_once(session, steps, node):
                return steps
            if self._should_finalize_after_step(steps[-1]):
                break

        if self.max_steps > 1 and session.status != "failed":
            self._append_summary_step(session, steps)

        return steps


class PlanExecuteLoop(_BaseLoop):
    def run(self, session: SessionState) -> list[ExecutionStep]:
        steps: list[ExecutionStep] = []
        for node in session.plan[: self.max_steps]:
            if not self._execute_once(session, steps, node):
                break
        return steps


__all__ = ["PlanExecuteLoop", "ReActLoop"]
