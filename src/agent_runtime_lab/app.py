"""Public runtime API."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from agent_runtime_lab.critic import Critic
from agent_runtime_lab.executor import Executor
from agent_runtime_lab.memory import MemoryManager
from agent_runtime_lab.planner import Planner
from agent_runtime_lab.reliability import ReliabilityManager
from agent_runtime_lab.result import RunMetrics, RunResult
from agent_runtime_lab.retrieval import Retriever
from agent_runtime_lab.runtime import PlanExecuteLoop, ReActLoop
from agent_runtime_lab.session import SessionStore
from agent_runtime_lab.tools import ToolRegistry, create_builtin_tools
from agent_runtime_lab.types import ExecutionMode, SessionState, TaskSpec
from agent_runtime_lab.validators import OutputValidator


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


class AgentRuntime:
    """Facade runtime entrypoint for react / plan-execute execution."""

    def __init__(
        self,
        planner: Planner | None = None,
        executor: Executor | None = None,
        critic: Critic | None = None,
        max_steps: int = 12,
        tool_registry: ToolRegistry | None = None,
        session_store: SessionStore | None = None,
        memory_manager: MemoryManager | None = None,
        retriever: Retriever | None = None,
        reliability_manager: ReliabilityManager | None = None,
        output_validator: OutputValidator | None = None,
    ) -> None:
        self.planner = planner or Planner(max_plan_steps=max_steps)
        self.executor = executor or Executor()
        self.critic = critic or Critic()
        self.max_steps = max_steps

        registry = tool_registry or ToolRegistry()
        if tool_registry is None:
            registry.register_many(create_builtin_tools())
        self.tool_registry = registry

        self.session_store = session_store or SessionStore()
        self.memory_manager = memory_manager or MemoryManager()
        self.retriever = retriever or Retriever()
        self.reliability_manager = reliability_manager or ReliabilityManager(
            max_steps=max_steps
        )
        self.output_validator = output_validator or OutputValidator()
        self._bind_runtime_dependencies()

    def _bind_runtime_dependencies(self) -> None:
        self.executor.bind_runtime_dependencies(
            tool_registry=self.tool_registry,
            reliability_manager=self.reliability_manager,
        )

    def _load_or_create_session(
        self,
        *,
        task: TaskSpec,
        mode: ExecutionMode,
        session_id: str | None,
        resume: bool,
    ) -> SessionState:
        if resume and session_id:
            existing = self.session_store.get(session_id)
            if existing is not None:
                existing.mode = mode
                existing.task = task
                existing.goal = task.objective
                existing.status = "running"
                existing.error_log.clear()
                existing.plan = []

                merged_constraints: list[str] = []
                for item in [*existing.constraints, *task.constraints]:
                    text = item.strip()
                    if text and text not in merged_constraints:
                        merged_constraints.append(text)
                existing.constraints = merged_constraints
                existing.updated_at = _utc_now()
                return existing

        return self.session_store.create(
            task=task,
            mode=mode,
            session_id=session_id or uuid4().hex,
            goal=task.objective,
        )

    def _prepare_retrieval(self, session: SessionState) -> None:
        self.retriever.clear()
        indexed = self.retriever.ingest(
            session.task.context,
            source_prefix=f"session:{session.session_id}",
        )
        session.metadata["retrieval_chunks_indexed"] = indexed

    def _build_loop(
        self,
        mode: ExecutionMode,
    ) -> ReActLoop | PlanExecuteLoop:
        if mode == "plan_execute":
            return PlanExecuteLoop(
                self.executor,
                self.critic,
                self.max_steps,
                reliability_manager=self.reliability_manager,
                memory_manager=self.memory_manager,
                retriever=self.retriever,
                output_validator=self.output_validator,
            )
        return ReActLoop(
            self.executor,
            self.critic,
            self.max_steps,
            reliability_manager=self.reliability_manager,
            memory_manager=self.memory_manager,
            retriever=self.retriever,
            output_validator=self.output_validator,
        )

    def run(
        self,
        task: TaskSpec,
        mode: ExecutionMode,
        session_id: str | None = None,
        resume: bool = False,
    ) -> RunResult:
        started_at = _utc_now()
        session = self._load_or_create_session(
            task=task,
            mode=mode,
            session_id=session_id,
            resume=resume,
        )
        self._bind_runtime_dependencies()
        self.reliability_manager.reset_cycle()
        self._prepare_retrieval(session)

        if mode == "plan_execute":
            session.plan = self.planner.plan(task)

        loop = self._build_loop(mode)
        steps = loop.run(session)

        success = session.status != "failed" and all(step.success for step in steps)
        session.status = "completed" if success else "failed"

        tool_steps = [step for step in steps if step.tool_call is not None]
        tool_call_success = sum(
            1
            for step in tool_steps
            if step.tool_result is not None and step.tool_result.success
        )
        metrics = RunMetrics(
            steps=len(steps),
            tool_calls=len(tool_steps),
            tool_call_success=tool_call_success,
            total_latency_ms=sum(step.latency_ms or 0 for step in steps),
            token_estimate=sum(step.token_estimate or 0 for step in steps),
            constraint_retained=not session.error_log,
        )

        self.session_store.save(session)
        final_answer = (
            steps[-1].observation
            if steps
            else (session.history[-1].observation if session.history else None)
        )
        return RunResult(
            session_id=session.session_id,
            mode=mode,
            success=success,
            final_answer=final_answer,
            final_state=session,
            steps=steps,
            metrics=metrics,
            started_at=started_at,
            finished_at=_utc_now(),
            error=";".join(session.error_log) if session.error_log else None,
        )


__all__ = ["AgentRuntime"]
