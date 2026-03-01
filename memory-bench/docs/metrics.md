# Metrics 与 Schema 规范（v0.1）

## JSONL Schema 版本

当前 `schema_version=1`，样本结构字段如下：

- `id`
- `category`
- `dialogue`
- `target_query`
- `memory_points`
- `hard_constraints`
- `expected_facts`
- `distractor_level`

> 任何字段级变更都必须：
> 1) 更新本文件；
> 2) 更新相关加载与校验逻辑；
> 3) 补充对应测试用例。

## EvalResult 输出字段

每条评测结果应包含：

- `run_id`
- `sample_id`
- `strategy`
- `adapter`
- `final_answer`
- `memory_hits`
- `constraint_violations`
- `contradictions`
- `latency_ms`

## MetricsSummary 输出字段

- `memory_recall_rate`
- `constraint_retention_rate`
- `contradiction_rate`
- `avg_latency_ms`
- `p50_latency_ms`
- `p95_latency_ms`

## 回归机制

- 固定 seed：`20260301`
- golden subset：每类默认 5 条
- 漂移阈值：`±0.03`
- 超阈值行为：报告中写入 warning，不阻断执行

## 规则判定优先原则

v0.1 默认使用规则判定，确保同输入下结果稳定、可追溯。LLM-as-judge 可在 v0.2 作为补充，但不能替代规则基线。
