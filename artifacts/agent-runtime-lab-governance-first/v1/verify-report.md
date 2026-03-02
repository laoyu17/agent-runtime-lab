# Verify Report

- plan_id: `agent-runtime-lab-governance-first`
- version: `v1`
- verified_at: `2026-03-02`
- status: `pass`

## Guardrail Step Status

All plan steps are marked `completed` in:
- `.codex_middleware/plans/agent-runtime-lab-governance-first/v1/state.json`

Completed steps:
- g0-repo-bootstrap
- g0-quality-ci
- g0-governance-docs
- v01-core-types
- v01-runtime-loops
- v01-tools-memory-rag
- v01-trace-cli
- v01-tests
- v02-reliability
- v03-eval-reporting
- v04-ecosystem-enhancements

## Quality Gates

Executed command:
- `scripts/ci_local.sh`

Result:
- ruff check: pass
- black --check: pass
- mypy src: pass
- pytest + coverage: pass (`69 passed`, `coverage 93.19%`)

## Strict Benchmark Acceptance (2026-03-02)

Executed commands:
- `python -m agent_runtime_lab.cli run-benchmark --dataset data/benchmarks/tasks.jsonl --out /tmp/arl-acceptance-2026-03-02/react --mode react --strict-thresholds`
- `python -m agent_runtime_lab.cli run-benchmark --dataset data/benchmarks/tasks.jsonl --out /tmp/arl-acceptance-2026-03-02/plan --mode plan_execute --strict-thresholds`

Result:
- react: pass (`task_success_rate=0.95`, `tool_call_success_rate=1.0`, `constraint_retention_rate=0.95`)
- plan_execute: pass (`task_success_rate=0.95`, `tool_call_success_rate=1.0`, `constraint_retention_rate=0.95`)
- Known failed sample (both modes): `constraint-03` (expected `search_docs`, actual `policy_blocked_no_network` on `web_fetch_mock`)

## Final Checks

- Benchmark dataset exists and matches 20-case split (8/6/6):
  - `data/benchmarks/tasks.jsonl`
- Reports generated:
  - `outputs/reports/benchmark_report.md`
  - `outputs/reports/benchmark_report.html`
- v0.4 enhancements landed:
  - MCP adapter layer
  - profile/env config overrides
  - enhanced trace inspection CLI
