# 评测协议（Eval Protocol）

## 1. 数据集构成

固定 20 条任务：

- 工具调用类：8
- RAG 问答类：6
- 约束保持类：6

数据文件：`data/benchmarks/tasks.jsonl`

约定：

- tool 类样本应补齐 `expected_tool_calls`。
- constraint 类至少包含“禁止联网触发样本”和“禁止联网反例样本”。

## 2. 指标定义

- `task_success_rate`：任务级成功比例。
- `tool_call_success_rate`：工具调用成功次数 / 总调用次数。
- `avg_steps_per_task`：每任务平均步骤数。
- `avg_latency_ms`：任务平均耗时（毫秒）。
- `constraint_retention_rate`：多轮中关键约束被保持的比例。

## 3. 统计口径

- 默认按任务等权平均。
- 多次运行报告均值与标准差（若启用重复实验）。
- 非确定性控制：固定 seed + Mock provider。
- 当样本 `metadata.expected_constraint_violation=true` 且运行轨迹出现 `policy_blocked_no_network` 时，记为通过（目标为验证策略拦截能力）。

## 4. 通过阈值（平衡档）

- `task_success_rate >= 0.60`
- `tool_call_success_rate >= 0.90`
- `constraint_retention_rate >= 0.90`

CLI 行为：

- 普通模式：`run-benchmark` 输出阈值检查结果，但默认返回 0。
- 严格模式：`run-benchmark --strict-thresholds` 任一阈值不达标即返回非 0。
- 推荐验收命令：`run-benchmark --mode plan_execute --strict-thresholds`。

## 5. 报告模板

报告输出：Markdown + HTML，至少包含：

1. 总体结果（核心指标总览）
2. 分场景结果（8/6/6）
3. 阈值检查结果（pass/fail）
4. 失败样本切片（含 trace 关键片段）
5. 问题归因与改进建议

## 6. 回归要求

- 每次核心行为变更后至少执行一次 benchmark smoke。
- 若指标显著下降，优先回滚或修复再合并。
