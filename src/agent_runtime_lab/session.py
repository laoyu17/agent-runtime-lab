"""Session state lifecycle helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from agent_runtime_lab.types import (
    ExecutionMode,
    ExecutionStep,
    SessionState,
    TaskSpec,
    ToolResult,
)


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


class SessionStore:
    """In-memory session store for runtime execution."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def create(
        self,
        task: TaskSpec,
        mode: ExecutionMode,
        session_id: str | None = None,
        goal: str | None = None,
    ) -> SessionState:
        sid = session_id or uuid4().hex
        session = SessionState(
            session_id=sid,
            mode=mode,
            task=task,
            goal=goal or task.objective,
            constraints=list(task.constraints),
        )
        self._sessions[sid] = session
        return session

    def get(self, session_id: str) -> SessionState | None:
        return self._sessions.get(session_id)

    def require(self, session_id: str) -> SessionState:
        session = self.get(session_id)
        if session is None:
            raise KeyError(f"session not found: {session_id}")
        return session

    def save(self, session: SessionState) -> None:
        session.updated_at = _utc_now()
        self._sessions[session.session_id] = session

    def list_session_ids(self) -> list[str]:
        return sorted(self._sessions)

    def append_step(self, session_id: str, step: ExecutionStep) -> None:
        session = self.require(session_id)
        session.history.append(step)
        session.current_step += 1
        session.updated_at = _utc_now()

    def append_tool_result(self, session_id: str, result: ToolResult) -> None:
        session = self.require(session_id)
        session.tool_results.append(result)
        session.updated_at = _utc_now()

    def append_conclusion(self, session_id: str, conclusion: str) -> None:
        session = self.require(session_id)
        if conclusion.strip():
            session.interim_conclusions.append(conclusion.strip())
        session.updated_at = _utc_now()

    def append_error(self, session_id: str, error: str) -> None:
        session = self.require(session_id)
        if error.strip():
            session.error_log.append(error.strip())
            session.status = "failed"
        session.updated_at = _utc_now()

    def set_memory_summary(self, session_id: str, summary: str | None) -> None:
        session = self.require(session_id)
        session.memory_summary = summary
        session.updated_at = _utc_now()

    def dump(self, session_id: str) -> dict[str, object]:
        session = self.require(session_id)
        return session.model_dump(mode="python")


class JsonSessionStore(SessionStore):
    """JSON-file backed session store with in-memory cache."""

    def __init__(self, root_dir: str | Path = "outputs/sessions") -> None:
        super().__init__()
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        task: TaskSpec,
        mode: ExecutionMode,
        session_id: str | None = None,
        goal: str | None = None,
    ) -> SessionState:
        session = super().create(task=task, mode=mode, session_id=session_id, goal=goal)
        self._write_session(session)
        return session

    def get(self, session_id: str) -> SessionState | None:
        cached = self._sessions.get(session_id)
        if cached is not None:
            return cached

        path = self._session_path(session_id)
        if not path.exists():
            return None

        payload = json.loads(path.read_text(encoding="utf-8"))
        session = SessionState.model_validate(payload)
        self._sessions[session_id] = session
        return session

    def save(self, session: SessionState) -> None:
        super().save(session)
        self._write_session(session)

    def list_session_ids(self) -> list[str]:
        disk_ids = {
            path.stem
            for path in self.root_dir.glob("*.json")
            if path.is_file() and path.stem
        }
        memory_ids = set(super().list_session_ids())
        return sorted(memory_ids | disk_ids)

    def _session_path(self, session_id: str) -> Path:
        return self.root_dir / f"{session_id}.json"

    def _write_session(self, session: SessionState) -> None:
        path = self._session_path(session.session_id)
        payload = session.model_dump(mode="json")
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


__all__ = ["JsonSessionStore", "SessionStore"]
