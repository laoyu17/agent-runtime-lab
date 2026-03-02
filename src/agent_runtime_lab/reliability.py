"""Reliability primitives for retries, timeout, fallback, and execution guards."""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from time import sleep
from typing import Any


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


class EmptyResultError(RuntimeError):
    """Raised when operation returns an empty payload."""


@dataclass(slots=True)
class RetryPolicy:
    """Retry and backoff policy configuration."""

    max_retries: int = 1
    base_delay_ms: int = 100
    backoff_factor: float = 2.0
    max_delay_ms: int = 2_000
    timeout_ms: int | None = None

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if self.base_delay_ms < 0:
            raise ValueError("base_delay_ms must be >= 0")
        if self.backoff_factor < 1.0:
            raise ValueError("backoff_factor must be >= 1.0")
        if self.max_delay_ms < 0:
            raise ValueError("max_delay_ms must be >= 0")
        if self.timeout_ms is not None and self.timeout_ms <= 0:
            raise ValueError("timeout_ms must be > 0")

    def delay_ms(self, attempt_index: int) -> int:
        delay = int(self.base_delay_ms * (self.backoff_factor**attempt_index))
        return min(delay, self.max_delay_ms)


@dataclass(slots=True)
class StepDecision:
    """Decision object for early-stop checks."""

    stop: bool
    reason: str | None = None


@dataclass(slots=True)
class ReliabilityOutcome:
    """Outcome envelope for guarded execution."""

    success: bool
    value: Any = None
    error: str | None = None
    attempts: int = 0
    used_fallback: bool = False
    timed_out: bool = False


class RepeatCallGuard:
    """Detect repeated call signatures in a sliding window."""

    def __init__(self, window_size: int = 8, threshold: int = 3) -> None:
        if window_size < 1:
            raise ValueError("window_size must be >= 1")
        if threshold < 2:
            raise ValueError("threshold must be >= 2")

        self.threshold = threshold
        self._window: deque[str] = deque(maxlen=window_size)

    def register(self, tool_name: str, arguments: dict[str, Any]) -> bool:
        signature = self._signature(tool_name, arguments)
        self._window.append(signature)
        repeat_count = sum(1 for value in self._window if value == signature)
        return repeat_count >= self.threshold

    def reset(self) -> None:
        self._window.clear()

    @staticmethod
    def _signature(tool_name: str, arguments: dict[str, Any]) -> str:
        encoded = json.dumps(arguments, sort_keys=True, ensure_ascii=False, default=str)
        return f"{tool_name}:{encoded}"


class ReliabilityManager:
    """Manager for retries, timeout/fallback, and loop guards."""

    def __init__(
        self,
        max_steps: int = 12,
        retry_policy: RetryPolicy | None = None,
        repeat_guard: RepeatCallGuard | None = None,
    ) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be >= 1")

        self.max_steps = max_steps
        self.retry_policy = retry_policy or RetryPolicy()
        self.repeat_guard = repeat_guard or RepeatCallGuard()

    def reset_cycle(self) -> None:
        self.repeat_guard.reset()

    def should_stop_for_steps(self, current_step: int) -> StepDecision:
        if current_step >= self.max_steps:
            return StepDecision(stop=True, reason="max_steps_exceeded")
        return StepDecision(stop=False)

    def should_stop_for_repeat_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> StepDecision:
        if self.repeat_guard.register(tool_name, arguments):
            return StepDecision(stop=True, reason="repeat_call_detected")
        return StepDecision(stop=False)

    def execute(
        self,
        operation: Callable[[], Any],
        *,
        fallback: Callable[[], Any] | Any | None = None,
        timeout_ms: int | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> ReliabilityOutcome:
        policy = retry_policy or self.retry_policy
        timeout = timeout_ms if timeout_ms is not None else policy.timeout_ms

        errors: list[str] = []
        saw_timeout = False
        attempts = 0

        for attempt_index in range(policy.max_retries + 1):
            attempts = attempt_index + 1
            try:
                value = self._run_with_timeout(operation, timeout)
                if _is_empty_value(value):
                    raise EmptyResultError("empty_result")
                return ReliabilityOutcome(success=True, value=value, attempts=attempts)
            except FutureTimeout:
                saw_timeout = True
                errors.append("timeout")
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))

            if attempt_index < policy.max_retries:
                delay = policy.delay_ms(attempt_index)
                if delay > 0:
                    sleep(delay / 1000)

        if fallback is not None:
            fallback_outcome = self._run_fallback(fallback)
            fallback_outcome.attempts = attempts
            fallback_outcome.error = fallback_outcome.error or (
                errors[-1] if errors else None
            )
            fallback_outcome.timed_out = saw_timeout
            return fallback_outcome

        return ReliabilityOutcome(
            success=False,
            error=errors[-1] if errors else "unknown_error",
            attempts=attempts,
            used_fallback=False,
            timed_out=saw_timeout,
        )

    def _run_fallback(self, fallback: Callable[[], Any] | Any) -> ReliabilityOutcome:
        try:
            fallback_value = fallback() if callable(fallback) else fallback
        except Exception as exc:  # noqa: BLE001
            return ReliabilityOutcome(
                success=False,
                error=f"fallback_failed:{exc}",
                used_fallback=True,
            )

        if _is_empty_value(fallback_value):
            return ReliabilityOutcome(
                success=False,
                error="fallback_empty_result",
                used_fallback=True,
            )

        return ReliabilityOutcome(
            success=True,
            value=fallback_value,
            used_fallback=True,
        )

    @staticmethod
    def _run_with_timeout(operation: Callable[[], Any], timeout_ms: int | None) -> Any:
        if timeout_ms is None:
            return operation()

        timeout_s = timeout_ms / 1000
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(operation)
        try:
            return future.result(timeout=timeout_s)
        except FutureTimeout:
            future.cancel()
            raise
        finally:
            # Avoid blocking on a timed-out worker; this keeps timeout behavior
            # aligned with caller expectations.
            executor.shutdown(wait=False, cancel_futures=True)


__all__ = [
    "EmptyResultError",
    "ReliabilityManager",
    "ReliabilityOutcome",
    "RepeatCallGuard",
    "RetryPolicy",
    "StepDecision",
]
