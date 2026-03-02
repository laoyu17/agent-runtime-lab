"""Structured trace persistence (JSONL + SQLite)."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from agent_runtime_lab.result import RunResult
from agent_runtime_lab.types import TraceEvent

_DEFAULT_REDACT_KEYS = (
    "api_key",
    "token",
    "cookie",
    "password",
    "authorization",
    "secret",
)
_REDACTED_VALUE = "***REDACTED***"
_INLINE_SECRET_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|token|cookie|password|authorization|secret)\b(\s*[:=]\s*)([^\s,;]+)"
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]+")


class TraceStore:
    """Persist trace events to JSONL and SQLite index."""

    def __init__(
        self,
        output_dir: str,
        sqlite_path: str,
        redact_sensitive: bool = True,
        redact_match_mode: str = "exact",
        redact_keys: list[str] | None = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.sqlite_path = Path(sqlite_path)
        self.redact_sensitive = redact_sensitive
        normalized_mode = str(redact_match_mode).strip().lower()
        if normalized_mode not in {"exact", "contains"}:
            raise ValueError(
                "redact_match_mode must be 'exact' or 'contains', "
                f"got: {redact_match_mode}"
            )
        self.redact_match_mode = normalized_mode
        keys = redact_keys if redact_keys is not None else list(_DEFAULT_REDACT_KEYS)
        self.redact_keys = tuple(
            self._normalize_key(item) for item in keys if self._normalize_key(item)
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.sqlite_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trace_events (
                    session_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    selected_tool TEXT NOT NULL,
                    latency_ms INTEGER NOT NULL,
                    token_estimate INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trace_session "
                "ON trace_events(session_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trace_timestamp "
                "ON trace_events(timestamp)"
            )

    def append(self, event: TraceEvent, trace_file: str | Path | None = None) -> str:
        file_path = self._resolve_trace_file(event.session_id, trace_file)
        payload = event.model_dump(mode="json")
        payload = self._sanitize_payload(payload)

        with file_path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(payload, ensure_ascii=False) + "\n")

        with sqlite3.connect(self.sqlite_path) as conn:
            conn.execute(
                """
                INSERT INTO trace_events (
                    session_id, step_id, mode, selected_tool,
                    latency_ms, token_estimate, timestamp, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.session_id,
                    event.step_id,
                    event.mode,
                    event.selected_tool,
                    event.latency_ms,
                    event.token_estimate,
                    event.timestamp.isoformat(),
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
        return str(file_path)

    def append_many(
        self,
        events: Iterable[TraceEvent],
        trace_file: str | Path | None = None,
    ) -> str | None:
        last_path: str | None = None
        for event in events:
            last_path = self.append(event, trace_file=trace_file)
        return last_path

    @staticmethod
    def read_jsonl(
        trace_file: str | Path,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        file_path = Path(trace_file)
        rows: list[dict[str, Any]] = []
        if not file_path.exists():
            return rows
        for line in file_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if session_id is None or row.get("session_id") == session_id:
                rows.append(row)
        return rows

    def _resolve_trace_file(
        self,
        session_id: str,
        trace_file: str | Path | None,
    ) -> Path:
        if trace_file is None:
            return self.output_dir / f"{session_id}.jsonl"
        given = Path(trace_file)
        if not given.is_absolute():
            return given
        return given

    def _sanitize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.redact_sensitive:
            return payload
        sanitized = self._sanitize_value(payload)
        if isinstance(sanitized, dict):
            return sanitized
        return payload

    def _sanitize_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            sanitized: dict[str, Any] = {}
            for raw_key, item in value.items():
                key = str(raw_key)
                if self._is_sensitive_key(key):
                    sanitized[key] = _REDACTED_VALUE
                else:
                    sanitized[key] = self._sanitize_value(item)
            return sanitized
        if isinstance(value, list):
            return [self._sanitize_value(item) for item in value]
        if isinstance(value, str):
            return self._sanitize_text(value)
        return value

    def _sanitize_text(self, text: str) -> str:
        masked = _INLINE_SECRET_PATTERN.sub(
            lambda match: f"{match.group(1)}{match.group(2)}{_REDACTED_VALUE}",
            text,
        )
        return _BEARER_PATTERN.sub(f"Bearer {_REDACTED_VALUE}", masked)

    def _is_sensitive_key(self, key: str) -> bool:
        normalized = self._normalize_key(key)
        if self.redact_match_mode == "contains":
            return any(token in normalized for token in self.redact_keys)
        return normalized in self.redact_keys

    @staticmethod
    def _normalize_key(key: str) -> str:
        return "".join(char for char in key.lower() if char.isalnum())


def run_result_to_events(result: RunResult) -> list[TraceEvent]:
    """Convert runtime step records into trace events."""

    events: list[TraceEvent] = []
    for step in result.steps:
        tool_input = step.tool_call.arguments if step.tool_call else None
        tool_output = step.tool_result.output if step.tool_result else step.observation
        events.append(
            TraceEvent(
                session_id=result.session_id,
                step_id=step.step_id,
                mode=result.mode,
                thought_summary=step.thought_summary,
                selected_tool=step.selected_tool or "none",
                tool_input=tool_input,
                tool_output=tool_output,
                state_update=step.state_update,
                latency_ms=step.latency_ms or 0,
                token_estimate=step.token_estimate or 0,
                timestamp=step.timestamp,
            )
        )
    return events


__all__ = ["TraceStore", "run_result_to_events"]
