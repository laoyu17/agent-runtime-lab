"""Critic validates runtime steps and stop conditions."""

from __future__ import annotations

from dataclasses import dataclass

from agent_runtime_lab.types import ExecutionStep, SessionState
from agent_runtime_lab.validators import ConstraintValidator


@dataclass(slots=True)
class CriticDecision:
    proceed: bool
    reason: str | None = None


class Critic:
    """Evaluates whether runtime should continue."""

    def __init__(self, constraint_validator: ConstraintValidator | None = None) -> None:
        self.constraint_validator = constraint_validator or ConstraintValidator()

    def review(self, session: SessionState, step: ExecutionStep) -> CriticDecision:
        if not step.success:
            session.error_log.append("step_failed")
            return CriticDecision(proceed=False, reason="step_failed")

        observation = (step.observation or "").strip()
        result = self.constraint_validator.validate(
            observation,
            constraints=session.constraints,
        )
        if not result.passed:
            reason = self._normalize_reason(result.errors[0])
            session.error_log.append(reason)
            return CriticDecision(proceed=False, reason=reason)

        return CriticDecision(proceed=True)

    @staticmethod
    def _normalize_reason(error: str) -> str:
        lowered = error.lower()
        if "must json" in lowered:
            return "constraint_json_violated"
        if "no network" in lowered:
            return "constraint_network_violated"
        return "constraint_violated"


__all__ = ["Critic", "CriticDecision"]
