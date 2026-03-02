# Agent Runtime Lab / Agent Runtime 实验室

Agent Runtime Lab 是一个 **governance-first** 的 Agent Runtime 训练场：先把工程治理（规范、门禁、可追踪）做好，再迭代 Planner / Executor / Critic 能力。

Agent Runtime Lab is a governance-first playground for building and evaluating an agent runtime with Planner/Executor/Critic layers and ReAct/Plan-Execute dual modes.

## Why / 为什么做

- 面向工程实践与评审协作：不仅能跑 demo，还能解释“为什么这样设计”。
- 解决 Agent 工程常见痛点：不可复现、难回归、上下文失控、指标缺失。
- 通过 Mock-first 与可观测优先，在无 API Key 环境也能稳定开发。

## Features / 特性

- 三层架构：Planner / Executor / Critic。
- 双执行范式：`react` 与 `plan_execute`。
- ReAct 多步执行（当前 mock 基线常见为“单 action + 汇总步”），Plan-Execute 节点状态推进。
- Tool Registry：支持 Local Function、HTTP API、MCP-style Adapter。
- 可靠性治理：timeout/retry/repeat-call guard。
- 上下文治理：retrieval 证据注入 + memory 摘要压缩 + output validator。
- 会话恢复：CLI 默认使用 JSON 持久化会话存储（`outputs/sessions`）。
- Trace：JSONL 明细 + SQLite 索引统计（默认敏感字段脱敏，可配置关闭）。
- Eval：20 条 benchmark（8/6/6）+ 核心指标 + 报告导出。

## Architecture / 架构概览

- 入口：`AgentRuntime.run(task, mode, session_id=None, resume=False)`
- 主链路：TaskSpec -> Planner -> Executor -> Critic -> RunResult
- 支撑模块：Tool Registry、Reliability、Memory、Retrieval、Trace、Eval

详细见：`docs/architecture.md`。

## Quick Start / 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]

# 本地门禁
scripts/ci_local.sh
```

## Example / 示例

```bash
# 运行单任务（支持会话恢复）
python3 -m agent_runtime_lab.cli run-task \
  --task-file examples/task_react.yaml \
  --mode react \
  --session-id demo-session \
  --resume

# 运行 benchmark（开启阈值硬校验）
python3 -m agent_runtime_lab.cli run-benchmark \
  --dataset data/benchmarks/tasks.jsonl \
  --out outputs/reports \
  --mode plan_execute \
  --strict-thresholds

# 检查 trace
python3 -m agent_runtime_lab.cli inspect-trace \
  --trace-file outputs/traces/demo-session.jsonl \
  --format json

# 查看工具注册
python3 -m agent_runtime_lab.cli list-tools

# MCP adapter 注入示例（不改 CLI 主链路）
python3 examples/mcp_adapter_demo.py
```

## Metrics / 指标

- `task_success_rate`
- `tool_call_success_rate`
- `avg_steps_per_task`
- `avg_latency_ms`
- `constraint_retention_rate`

评测协议见：`docs/eval_protocol.md`。

## Limitations / 当前限制

- 默认模型为 Mock，不代表真实大模型上限表现。
- `llm.provider/model/endpoint` 当前为配置预留字段，尚未接入 Planner/Executor 主执行链路。
- 首版不包含 FastAPI 服务接口，仅 CLI + Python API。
- Benchmark 为离线可复现实验集，需按业务场景扩展真实数据分布。

## Roadmap / 路线图

- G0：工程治理基线（已完成）
- V0.1：最小闭环 Runtime（双模式 + 三层 + trace）
- V0.2：可靠性与上下文治理增强
- V0.3：评测体系与报告自动化
- V0.4：生态兼容与展示增强

详见：`ROADMAP.md`。

## License

MIT，见 `LICENSE`。
