"""Short-term memory and context-compression helpers."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field

from agent_runtime_lab.types import SessionState, ToolResult


def _is_constraint(text: str) -> bool:
    lowered = text.lower()
    keywords = (
        "must",
        "must not",
        "forbid",
        "forbidden",
        "only",
        "no ",
    )
    zh_keywords = ("必须", "禁止", "不得", "只能")
    has_en = any(word in lowered for word in keywords)
    has_zh = any(word in text for word in zh_keywords)
    return has_en or has_zh


def _truncate(text: str, max_chars: int) -> str:
    if max_chars < 8:
        raise ValueError("max_chars must be >= 8")
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3]}..."


class ConstraintExtractor:
    """Extract explicit constraint statements from text snippets."""

    def extract(self, snippets: Iterable[str]) -> list[str]:
        constraints: list[str] = []
        seen: set[str] = set()
        for snippet in snippets:
            text = snippet.strip()
            if not text or not _is_constraint(text):
                continue
            if text not in seen:
                seen.add(text)
                constraints.append(text)
        return constraints


@dataclass(slots=True)
class MemorySnapshot:
    """Compact memory output used for context injection."""

    summary: str
    recent_items: list[str]
    retained_constraints: list[str]
    compressed_history: list[str] = field(default_factory=list)
    compressed_tool_results: list[dict[str, str]] = field(default_factory=list)


class ShortTermMemory:
    """Fixed-size rolling memory window."""

    def __init__(self, window_size: int = 5) -> None:
        if window_size < 1:
            raise ValueError("window_size must be >= 1")
        self.window_size = window_size
        self._items: deque[str] = deque(maxlen=window_size)

    def add(self, item: str) -> None:
        text = item.strip()
        if text:
            self._items.append(text)

    def extend(self, items: Iterable[str]) -> None:
        for item in items:
            self.add(item)

    def clear(self) -> None:
        self._items.clear()

    def recent(self) -> list[str]:
        return list(self._items)

    def summarize(self, max_chars: int = 300) -> str:
        summary = " | ".join(self._items)
        return _truncate(summary, max_chars)


class MemoryManager:
    """Maintains short memory and context compression for one session."""

    def __init__(
        self,
        summary_window: int = 5,
        extractor: ConstraintExtractor | None = None,
        tool_result_keep: int = 4,
        summary_max_chars: int = 300,
    ) -> None:
        if tool_result_keep < 1:
            raise ValueError("tool_result_keep must be >= 1")
        if summary_max_chars < 8:
            raise ValueError("summary_max_chars must be >= 8")

        self._window_size = summary_window
        self._memory = ShortTermMemory(window_size=summary_window)
        self._extractor = extractor or ConstraintExtractor()
        self._tool_result_keep = tool_result_keep
        self._summary_max_chars = summary_max_chars

        self._tracked_session_fingerprint: tuple[str, str] | None = None
        self._history_index = 0
        self._conclusion_index = 0

    def sync(self, session: SessionState) -> MemorySnapshot:
        self._ensure_session_scope(session)
        self._ingest_new_items(session)
        self._retain_constraints(session)

        compressed_history = self._compress_history(session)
        compressed_tool_results = self._compress_tool_results(session.tool_results)
        summary = self._compose_summary(compressed_history, session.constraints)

        session.memory_summary = summary
        session.metadata["compressed_history"] = compressed_history
        session.metadata["compressed_tool_results"] = compressed_tool_results

        return MemorySnapshot(
            summary=summary,
            recent_items=self._memory.recent(),
            retained_constraints=list(session.constraints),
            compressed_history=compressed_history,
            compressed_tool_results=compressed_tool_results,
        )

    def _ensure_session_scope(self, session: SessionState) -> None:
        fingerprint = self._session_fingerprint(session)
        if self._tracked_session_fingerprint == fingerprint:
            return

        self._tracked_session_fingerprint = fingerprint
        self._history_index = 0
        self._conclusion_index = 0
        self._memory.clear()

    @staticmethod
    def _session_fingerprint(session: SessionState) -> tuple[str, str]:
        return (session.session_id, session.created_at.isoformat())

    def _ingest_new_items(self, session: SessionState) -> None:
        new_steps = session.history[self._history_index :]
        self._memory.extend(step.thought_summary for step in new_steps)
        self._history_index = len(session.history)

        new_conclusions = session.interim_conclusions[self._conclusion_index :]
        self._memory.extend(new_conclusions)
        self._conclusion_index = len(session.interim_conclusions)

    def _retain_constraints(self, session: SessionState) -> None:
        snippets = [
            *session.constraints,
            *session.interim_conclusions,
            *(step.thought_summary for step in session.history),
        ]
        extracted = self._extractor.extract(snippets)
        if not extracted and len(session.constraints) == len(set(session.constraints)):
            return

        retained: list[str] = []
        seen: set[str] = set()
        for item in [*session.constraints, *extracted]:
            if item in seen:
                continue
            seen.add(item)
            retained.append(item)
        session.constraints = retained

    def _compress_history(self, session: SessionState) -> list[str]:
        all_items = [
            *(step.thought_summary for step in session.history),
            *session.interim_conclusions,
        ]
        if len(all_items) <= self._window_size:
            return all_items

        if self._window_size == 1:
            return [all_items[-1]]

        tail_keep = self._window_size - 1
        return [all_items[0], "...", *all_items[-tail_keep:]]

    def _compress_tool_results(
        self,
        tool_results: list[ToolResult],
    ) -> list[dict[str, str]]:
        if not tool_results:
            return []

        failing = [result for result in tool_results if not result.success]
        ordered_candidates = [*reversed(failing), *reversed(tool_results)]

        selected: list[ToolResult] = []
        seen_call_ids: set[str] = set()
        for result in ordered_candidates:
            if result.call_id in seen_call_ids:
                continue
            seen_call_ids.add(result.call_id)
            selected.append(result)
            if len(selected) >= self._tool_result_keep:
                break

        return [self._render_tool_result(result) for result in selected]

    def _render_tool_result(self, result: ToolResult) -> dict[str, str]:
        detail_source = result.error if result.error else str(result.output)
        return {
            "tool": result.tool_name,
            "status": "ok" if result.success else "error",
            "detail": _truncate(detail_source, 120),
        }

    def _compose_summary(self, history: list[str], constraints: list[str]) -> str:
        base = self._memory.summarize(max_chars=self._summary_max_chars)
        if not base and history:
            base = _truncate(" | ".join(history), self._summary_max_chars)

        if constraints:
            pinned = "; ".join(constraints[-3:])
            if base:
                return _truncate(
                    f"{base} || constraints: {pinned}",
                    self._summary_max_chars,
                )
            return _truncate(f"constraints: {pinned}", self._summary_max_chars)

        return base


__all__ = [
    "ConstraintExtractor",
    "MemoryManager",
    "MemorySnapshot",
    "ShortTermMemory",
]
