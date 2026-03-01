# Memory Bench Roadmap

## v0.1 - Benchmark Core (Current)

- Status: ✅ implemented
- Dataset: 4 categories, 120 total samples
- Strategies: `full_context`, `sliding_window`, `summary_memory`, `structured_memory`
- Metrics: recall, constraint retention, contradiction, latency stats
- Deliverables: CLI, JSONL run outputs, Markdown + CSV reports, CI and tests

## v0.2 - Strategy Enhancements

- Add `retrieval_memory`
- Failure sample clustering
- Better metric explainability
- Hybrid judge (rule + LLM-as-judge) as optional extension

## v0.3 - Visualization & Integration

- HTML report and charts
- Integration with agent-runtime-lab memory manager
- Runtime adapter production integration
