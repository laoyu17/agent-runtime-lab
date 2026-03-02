"""Task planner for plan-execute mode."""

from __future__ import annotations

from agent_runtime_lab.types import PlanNode, TaskSpec


class Planner:
    """Builds a compact plan from task input."""

    def __init__(self, max_plan_steps: int = 8) -> None:
        self.max_plan_steps = max_plan_steps

    def plan(self, task: TaskSpec) -> list[PlanNode]:
        raw = task.input_payload.get("subtasks")
        if isinstance(raw, list) and raw:
            nodes = [
                PlanNode(title=f"step-{i + 1}", description=str(item).strip())
                for i, item in enumerate(raw)
                if str(item).strip()
            ]
            return nodes[: self.max_plan_steps] or [
                PlanNode(title=task.title, description=task.objective)
            ]
        return [PlanNode(title=task.title, description=task.objective)]


__all__ = ["Planner"]
