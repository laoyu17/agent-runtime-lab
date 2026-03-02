from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from agent_runtime_lab.app import AgentRuntime
from agent_runtime_lab.critic import Critic, CriticDecision
from agent_runtime_lab.executor import Executor
from agent_runtime_lab.planner import Planner
from agent_runtime_lab.reliability import ReliabilityManager, RepeatCallGuard
from agent_runtime_lab.runtime import PlanExecuteLoop, ReActLoop
from agent_runtime_lab.session import JsonSessionStore
from agent_runtime_lab.types import ExecutionStep, PlanNode, SessionState, TaskSpec


def _session(mode: str = "react", constraints: list[str] | None = None) -> SessionState:
    task = TaskSpec(title="demo", objective="solve", constraints=constraints or [])
    return SessionState(
        mode=mode,
        task=task,
        goal=task.objective,
        constraints=task.constraints,
    )


def test_planner_uses_subtasks_and_limit() -> None:
    task = TaskSpec(
        title="workflow",
        objective="finish",
        input_payload={"subtasks": ["first", " ", "second", "third"]},
    )

    nodes = Planner(max_plan_steps=2).plan(task)

    assert len(nodes) == 2
    assert nodes[0].description == "first"
    assert nodes[1].description == "second"


def test_planner_fallback_to_single_node() -> None:
    task = TaskSpec(title="fallback", objective="just do it")

    nodes = Planner().plan(task)

    assert len(nodes) == 1
    assert nodes[0].title == "fallback"
    assert nodes[0].description == "just do it"


def test_executor_updates_session_with_plan_node() -> None:
    session = _session()
    node = PlanNode(title="step-1", description="collect")

    step = Executor().execute(session, node)

    assert step.plan_step_id == node.step_id
    assert session.current_step == 1
    assert len(session.history) == 1
    assert session.interim_conclusions[-1] == "collect"


def test_executor_plan_node_prioritizes_node_semantics_over_global_goal() -> None:
    task = TaskSpec(
        title="plan",
        objective="Compute 9+9 with calculator",
    )
    session = SessionState(mode="plan_execute", task=task, goal=task.objective)
    node = PlanNode(title="step-1", description="parse request")

    step = Executor().execute(session, node)

    assert step.selected_tool is None
    assert step.tool_call is None
    assert step.state_update == "step_completed"


def test_critic_handles_failure_and_json_constraints() -> None:
    critic = Critic()

    failed_session = _session()
    failed_step = ExecutionStep(thought_summary="x", success=False, state_update="no")
    failed = critic.review(failed_session, failed_step)
    assert failed.proceed is False
    assert failed.reason == "step_failed"

    json_session = _session(constraints=["must json"])
    bad_step = ExecutionStep(
        thought_summary="x",
        success=True,
        observation="not-json",
        state_update="no",
    )
    bad = critic.review(json_session, bad_step)
    assert bad.proceed is False
    assert bad.reason == "constraint_json_violated"

    good_step = ExecutionStep(
        thought_summary="x",
        success=True,
        observation='{"ok":true}',
        state_update="yes",
    )
    good = critic.review(json_session, good_step)
    assert good.proceed is True


class StopCritic:
    def review(self, session: SessionState, step: ExecutionStep) -> CriticDecision:
        return CriticDecision(proceed=False, reason="forced_stop")


class NonJsonExecutor:
    def bind_runtime_dependencies(self, **kwargs: object) -> None:
        _ = kwargs

    def execute(self, session: SessionState, node: PlanNode | None) -> ExecutionStep:
        step = ExecutionStep(
            plan_step_id=node.step_id if node else None,
            thought_summary="bad",
            observation="plain-text",
            state_update="bad_output",
            success=True,
        )
        session.current_step += 1
        session.history.append(step)
        session.updated_at = datetime.now(tz=UTC)
        return step


def test_runtime_loops_react_and_plan_execute() -> None:
    executor = Executor()
    critic = Critic()

    react_session = _session(mode="react")
    react_steps = ReActLoop(executor, critic, max_steps=3).run(react_session)
    assert len(react_steps) == 2
    assert react_steps[0].state_update == "step_completed"
    assert react_steps[-1].state_update == "summary_completed"
    assert react_steps[-1].selected_tool is None

    plan_session = _session(mode="plan_execute")
    plan_session.plan = [
        PlanNode(title="s1", description="one"),
        PlanNode(title="s2", description="two"),
        PlanNode(title="s3", description="three"),
    ]
    plan_steps = PlanExecuteLoop(executor, critic, max_steps=2).run(plan_session)
    assert len(plan_steps) == 2
    assert all(step.success for step in plan_steps)
    assert plan_session.plan[0].status == "completed"
    assert plan_session.plan[1].status == "completed"
    assert plan_session.plan[2].status == "pending"


def test_runtime_loop_stops_when_critic_blocks() -> None:
    session = _session(mode="plan_execute")
    session.plan = [
        PlanNode(title="s1", description="one"),
        PlanNode(title="s2", description="two"),
    ]

    steps = PlanExecuteLoop(Executor(), StopCritic(), max_steps=5).run(session)

    assert len(steps) == 1
    assert session.status == "failed"


def test_agent_runtime_run_react_and_plan_execute() -> None:
    runtime = AgentRuntime(max_steps=2)

    react_task = TaskSpec(title="react", objective="answer")
    react_result = runtime.run(react_task, mode="react", session_id="react-session")
    assert react_result.session_id == "react-session"
    assert react_result.success is True
    assert react_result.metrics.steps == 2
    assert react_result.steps[-1].state_update == "summary_completed"

    plan_task = TaskSpec(
        title="plan",
        objective="finish",
        input_payload={"subtasks": ["a", "b", "c"]},
    )
    plan_result = runtime.run(plan_task, mode="plan_execute")
    assert plan_result.success is True
    assert plan_result.metrics.steps == 2


def test_agent_runtime_marks_failure_when_json_constraint_violated() -> None:
    runtime = AgentRuntime(executor=NonJsonExecutor(), max_steps=2)
    task = TaskSpec(
        title="json",
        objective="return json",
        constraints=["must json"],
    )

    result = runtime.run(task, mode="react")

    assert result.success is False
    assert result.final_state is not None
    assert result.final_state.status == "failed"
    assert result.error is not None
    assert (
        "constraint_json_violated" in result.error
        or "validation:constraint violated: must json" in result.error
    )


def test_agent_runtime_resume_reuses_session_history() -> None:
    runtime = AgentRuntime(max_steps=6)
    task = TaskSpec(title="resume", objective="answer")

    first = runtime.run(task, mode="react", session_id="resume-session", resume=False)
    second = runtime.run(task, mode="react", session_id="resume-session", resume=True)

    assert first.session_id == "resume-session"
    assert second.session_id == "resume-session"
    assert second.final_state is not None
    assert len(second.final_state.history) >= 4


def test_agent_runtime_resume_persists_across_runtime_instances(
    tmp_path: Path,
) -> None:
    task = TaskSpec(title="resume-json", objective="answer")
    runtime1 = AgentRuntime(
        max_steps=4,
        session_store=JsonSessionStore(tmp_path / "sessions"),
    )
    first = runtime1.run(task, mode="react", session_id="persist", resume=False)
    assert first.success is True

    runtime2 = AgentRuntime(
        max_steps=4,
        session_store=JsonSessionStore(tmp_path / "sessions"),
    )
    second = runtime2.run(task, mode="react", session_id="persist", resume=True)

    assert second.success is True
    assert second.final_state is not None
    assert len(second.final_state.history) >= 4
    assert second.final_state.current_step == 4


def test_runtime_injects_retrieval_memory_and_validation_metadata() -> None:
    runtime = AgentRuntime(max_steps=2)
    task = TaskSpec(
        title="rag",
        objective="retrieve runtime docs",
        constraints=["must json"],
        context=["retrieve runtime docs evidence", "planner executor critic"],
    )

    result = runtime.run(task, mode="react")

    assert result.success is True
    first = result.steps[0]
    assert "retrieval" in first.metadata
    assert first.metadata["retrieval"]["injected_hint"]
    assert first.metadata["retrieval"]["hits"][0]["excerpt"]
    assert "memory" in first.metadata
    assert "validation" in first.metadata
    assert first.metadata["validation"]["passed"] is True


def test_runtime_stops_on_repeat_tool_call_guard() -> None:
    runtime = AgentRuntime(
        max_steps=4,
        reliability_manager=ReliabilityManager(
            max_steps=4,
            repeat_guard=RepeatCallGuard(window_size=4, threshold=2),
        ),
    )
    task = TaskSpec(
        title="repeat",
        objective="compute 1+1",
        input_payload={"subtasks": ["compute 1+1", "compute 1+1", "compute 1+1"]},
    )

    result = runtime.run(task, mode="plan_execute")

    assert result.success is False
    assert result.error is not None
    assert "repeat_call_detected" in result.error
    assert result.steps[-1].state_update == "repeat_call_detected"


def test_react_loop_converges_without_repeat_for_simple_tool_task() -> None:
    runtime = AgentRuntime(max_steps=6)
    task = TaskSpec(
        title="react-tool",
        objective="Use calculator to compute 2+3 and return JSON status.",
        constraints=["must json"],
    )

    result = runtime.run(task, mode="react")

    assert result.success is True
    assert result.metrics.steps == 2
    assert result.steps[0].selected_tool == "calculator"
    assert result.steps[-1].state_update == "summary_completed"
    assert result.error is None


def test_runtime_blocks_network_tool_call_when_no_network_constraint() -> None:
    runtime = AgentRuntime(max_steps=4)
    task = TaskSpec(
        title="network",
        objective="Fetch https://example.com and return JSON status.",
        constraints=["must json", "no network"],
    )

    result = runtime.run(task, mode="plan_execute")

    assert result.success is False
    assert result.steps
    blocked = result.steps[0]
    assert blocked.state_update == "policy_blocked_no_network"
    assert blocked.selected_tool == "web_fetch_mock"
    assert blocked.tool_call is None
    assert blocked.tool_result is None
    assert blocked.metadata["policy"]["blocked"] is True
    assert result.metrics.tool_calls == 0
    assert result.final_state is not None
    assert result.final_state.tool_results == []
    assert result.error is not None
    assert "step_failed" in result.error
