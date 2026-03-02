from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(".codex_middleware")


class MiddlewareError(RuntimeError):
    """Raised when middleware policy checks fail."""


@dataclass
class PlanRef:
    plan_id: str
    version: str


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise MiddlewareError(f"file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MiddlewareError(f"invalid json: {path}") from exc


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _state_path(plan: PlanRef) -> Path:
    return ROOT / "plans" / plan.plan_id / plan.version / "state.json"


def _load_state(plan: PlanRef) -> dict[str, Any]:
    path = _state_path(plan)
    if not path.exists():
        raise MiddlewareError(
            f"plan not registered: plan_id={plan.plan_id} version={plan.version}"
        )
    return _load_json(path)


def _save_state(plan: PlanRef, data: dict[str, Any]) -> None:
    _save_json(_state_path(plan), data)


def _get_step(state: dict[str, Any], step_id: str) -> dict[str, Any]:
    for step in state["plan"]["steps"]:
        if step["id"] == step_id:
            return step
    raise MiddlewareError(f"step not found: {step_id}")


def register_plan(args: argparse.Namespace) -> None:
    plan_file = Path(args.plan_file)
    plan = _load_json(plan_file)
    required = {"plan_id", "version", "steps"}
    missing = required - set(plan)
    if missing:
        raise MiddlewareError(f"plan missing required fields: {sorted(missing)}")
    if not isinstance(plan["steps"], list) or not plan["steps"]:
        raise MiddlewareError("plan.steps must be a non-empty list")

    step_ids = set()
    for step in plan["steps"]:
        if "id" not in step or "title" not in step:
            raise MiddlewareError("each step requires id and title")
        if step["id"] in step_ids:
            raise MiddlewareError(f"duplicate step id: {step['id']}")
        step_ids.add(step["id"])

    plan_ref = PlanRef(plan_id=plan["plan_id"], version=plan["version"])
    state = {
        "plan": plan,
        "plan_file": str(plan_file),
        "approved": False,
        "active_step": None,
        "step_status": {step["id"]: "pending" for step in plan["steps"]},
        "verify": None,
        "handoff": None,
    }
    _save_state(plan_ref, state)
    print(json.dumps({"ok": True, "plan_id": plan_ref.plan_id, "version": plan_ref.version}))


def approve(args: argparse.Namespace) -> None:
    plan = PlanRef(args.plan_id, args.version)
    state = _load_state(plan)
    state["approved"] = True
    _save_state(plan, state)
    print(json.dumps({"ok": True, "approved": True, "plan_id": plan.plan_id, "version": plan.version}))


def start_step(args: argparse.Namespace) -> None:
    plan = PlanRef(args.plan_id, args.version)
    state = _load_state(plan)
    if not state["approved"]:
        raise MiddlewareError("plan is not approved")
    if state["active_step"] is not None:
        raise MiddlewareError(f"another step is active: {state['active_step']}")

    step = _get_step(state, args.step_id)
    status = state["step_status"][args.step_id]
    if status == "completed":
        raise MiddlewareError(f"step already completed: {args.step_id}")

    expected_modules = set(step.get("modules", []))
    provided_modules = {
        part.strip() for part in (args.modules or "").split(",") if part.strip()
    }
    if expected_modules and provided_modules and not provided_modules.issubset(expected_modules):
        raise MiddlewareError(
            f"modules out of scope for step {args.step_id}: {sorted(provided_modules - expected_modules)}"
        )

    state["active_step"] = args.step_id
    state["step_status"][args.step_id] = "in_progress"
    _save_state(plan, state)
    print(
        json.dumps(
            {
                "ok": True,
                "step_id": args.step_id,
                "status": "in_progress",
                "modules": sorted(provided_modules),
            }
        )
    )


def complete_step(args: argparse.Namespace) -> None:
    plan = PlanRef(args.plan_id, args.version)
    state = _load_state(plan)
    if state["active_step"] != args.step_id:
        raise MiddlewareError(
            f"step not active: expected {state['active_step']}, got {args.step_id}"
        )

    state["active_step"] = None
    state["step_status"][args.step_id] = "completed"
    _save_state(plan, state)
    print(json.dumps({"ok": True, "step_id": args.step_id, "status": "completed"}))


def verify(args: argparse.Namespace) -> None:
    plan = PlanRef(args.plan_id, args.version)
    state = _load_state(plan)
    if state["active_step"] is not None:
        raise MiddlewareError(f"cannot verify while step active: {state['active_step']}")

    incomplete = [k for k, v in state["step_status"].items() if v != "completed"]
    if incomplete:
        raise MiddlewareError(f"cannot verify; incomplete steps: {incomplete}")

    report_file = Path(args.report_file)
    if not report_file.exists():
        raise MiddlewareError(f"verify report not found: {report_file}")

    state["verify"] = {
        "status": args.status,
        "report_file": str(report_file),
    }
    _save_state(plan, state)
    print(
        json.dumps(
            {
                "ok": True,
                "verified": True,
                "status": args.status,
                "report_file": str(report_file),
            }
        )
    )


def handoff(args: argparse.Namespace) -> None:
    plan = PlanRef(args.plan_id, args.version)
    state = _load_state(plan)
    if not state.get("verify"):
        raise MiddlewareError("cannot handoff before verify")

    summary_file = Path(args.summary_file)
    if not summary_file.exists():
        raise MiddlewareError(f"handoff summary not found: {summary_file}")

    state["handoff"] = {
        "summary_file": str(summary_file),
    }
    _save_state(plan, state)
    print(
        json.dumps(
            {
                "ok": True,
                "handoff": True,
                "summary_file": str(summary_file),
            }
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex_middleware")
    sub = parser.add_subparsers(dest="cmd", required=True)

    reg = sub.add_parser("register-plan")
    reg.add_argument("--plan-file", required=True)
    reg.set_defaults(func=register_plan)

    app = sub.add_parser("approve")
    app.add_argument("--plan-id", required=True)
    app.add_argument("--version", required=True)
    app.set_defaults(func=approve)

    start = sub.add_parser("start-step")
    start.add_argument("--plan-id", required=True)
    start.add_argument("--version", required=True)
    start.add_argument("--step-id", required=True)
    start.add_argument("--modules", default="")
    start.set_defaults(func=start_step)

    complete = sub.add_parser("complete-step")
    complete.add_argument("--plan-id", required=True)
    complete.add_argument("--version", required=True)
    complete.add_argument("--step-id", required=True)
    complete.set_defaults(func=complete_step)

    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--plan-id", required=True)
    verify_parser.add_argument("--version", required=True)
    verify_parser.add_argument("--status", choices=["pass", "fail"], required=True)
    verify_parser.add_argument("--report-file", required=True)
    verify_parser.set_defaults(func=verify)

    hand = sub.add_parser("handoff")
    hand.add_argument("--plan-id", required=True)
    hand.add_argument("--version", required=True)
    hand.add_argument("--summary-file", required=True)
    hand.set_defaults(func=handoff)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except MiddlewareError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
