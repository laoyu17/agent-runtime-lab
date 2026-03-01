# Memory Bench AGENTS

## Goal

Ensure benchmark runs are reproducible, comparable, and explainable.

## Code Rules

- Keep implementation simple (KISS / YAGNI).
- Each function should have a single responsibility.
- Do not introduce implicit breaking changes to stable JSON formats.

## Data Rules

- JSONL schema is versioned.
- Any field-level schema change must update docs for metrics and dataset spec.

## Evaluation Rules

- Use rule-first judging in v0.1.
- LLM-as-judge is optional future extension and must not replace baseline rules.

## Test Rules

- Every new strategy requires unit tests.
- Every new strategy requires at least one integration test path.

## Documentation Rules

- `README.md` should stay English-facing.
- `docs/` should document design tradeoffs in Chinese.

## Security Rules

- API keys are loaded from environment variables only.
- Never commit secrets or credentials.

## Release Rules

- Each milestone update must include:
  - `ROADMAP.md` updates
  - at least one report sample update
