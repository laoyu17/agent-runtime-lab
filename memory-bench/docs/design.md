# Memory Bench 设计说明（v0.1）

## 目标

Memory Bench 的目标是提供一套**轻量、可复现、可比较**的多轮对话记忆评测基线。
首版优先保证离线稳定性和结果可解释性，因此采用规则判定优先，不依赖 LLM-as-judge。

## 核心模块

- `datasets`：统一样本结构、配置加载、JSONL 读写与 120 条基准数据生成。
- `strategies`：实现 4 种记忆策略（full/sliding/summary/structured）。
- `adapters`：提供 `mock`、`openai`、`runtime` 三类推理接入。
- `evaluators`：执行逐样本评测，计算 recall/constraint/contradiction/latency。
- `reports`：产出单次 run 报告与多 run 对比报告（Markdown + CSV）。
- `cli`：封装 `generate/eval/compare/report` 命令。

## 数据集设计

- 四类任务：`preference_memory`、`constraint_memory`、`slot_memory`、`distractor_memory`。
- 每类 30 条，共 120 条。
- 样本流程：初始事实注入 -> 干扰轮次 -> 目标追问。
- 干扰强度分层：`low/medium/high`，用于考察抗干扰能力。

## 指标设计

- `memory_recall_rate`：基于 `expected_facts` 的命中率。
- `constraint_retention_rate`：硬约束无违例样本占比。
- `contradiction_rate`：最终答案与已确认事实冲突率。
- `avg/p50/p95 latency`：延迟统计，仅用于观察与横向比较，不做阻断。

## 版本边界

- v0.1：不引入数据库、向量库、消息队列等重型依赖。
- `retrieval_memory` 放在 v0.2。
- `runtime` 适配器当前为可运行占位，保证基准链路闭环，后续再接入真实 runtime。
