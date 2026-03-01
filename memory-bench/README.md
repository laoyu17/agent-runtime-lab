# Memory Bench

Memory Bench is a lightweight and reproducible toolkit for evaluating multi-turn conversational memory in LLM/Agent systems.

## v0.1 Scope

- Offline and online evaluation flows
- Four baseline strategies:
  - `full_context`
  - `sliding_window`
  - `summary_memory`
  - `structured_memory`
- 120 benchmark samples (`4 categories x 30`)
- Rule-first judging for deterministic baselines
- Markdown + CSV reports

## Quick Start

```bash
cd memory-bench
python3 -m pip install -e .[dev]
```

Generate dataset:

```bash
memory-bench generate --config configs/benchmark.yaml --output-dir data/benchmark_sets
```

Run evaluation:

```bash
memory-bench eval --strategy full_context --adapter mock --config configs/benchmark.yaml
```

Create reports:

```bash
memory-bench report --run outputs/runs/<run_id>.jsonl --config configs/benchmark.yaml
memory-bench compare --runs outputs/runs/run_a.jsonl outputs/runs/run_b.jsonl --name baseline_compare
```

## CLI

```bash
memory-bench generate --config configs/benchmark.yaml
memory-bench eval --strategy <name> --adapter <mock|openai|runtime> --config configs/benchmark.yaml
memory-bench compare --runs outputs/runs/*.jsonl
memory-bench report --run <run_id>.jsonl
```

## Quality Gates

- Python versions: 3.11, 3.12
- Tests: unit + integration + CLI E2E
- Coverage gate: `>= 80%`

## Security

- API keys are loaded from environment variables only.
- Do not commit secrets.

## License

MIT
