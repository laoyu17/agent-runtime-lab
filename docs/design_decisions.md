# 设计决策记录（Design Decisions）

## D-001：治理优先于功能扩展

- 决策：先做 G0 工程基线，再推进 V0.x 功能。
- 理由：避免早期功能堆叠导致不可回归、不可维护。

## D-002：三层分离（Planner/Executor/Critic）

- 决策：从 v0.1 就保持三层架构，而非单循环大函数。
- 理由：职责清晰，便于插拔与问题定位。

## D-003：双模式并存（ReAct + Plan-Execute）

- 决策：在统一入口 `AgentRuntime.run` 下通过 mode 切换。
- 理由：兼顾探索型与结构化任务，便于评测对比。

## D-004：默认 Mock Provider

- 决策：默认离线 Mock，真实模型通过 OpenAI-compatible 配置接入。
- 理由：保障无密钥开发、提升回归稳定性与可复现性。
- 现状：已提供配置字段与治理路径，真实 provider 尚未接入主执行链路，作为后续里程碑推进。

## D-005：Trace 采用 JSONL + SQLite

- 决策：JSONL 保存明细，SQLite 保存索引与统计。
- 理由：兼顾可读性、可检索性与后续分析效率。

## D-006：评测基准固定 20 条（8/6/6）

- 决策：工具调用 8、RAG 问答 6、多轮约束保持 6。
- 理由：小规模但覆盖核心能力，适合快速迭代与面试展示。

## D-007：Trunk-based + Revert-first

- 决策：小步直推 `main`，回归时优先 `git revert`。
- 理由：降低分支管理负担，保持历史可审计与恢复简单。

## D-008：v0.4 配置与生态兼容增强

- 决策：在不破坏默认行为的前提下，引入 profile 配置覆盖、环境变量覆盖、MCP 适配层与增强 Trace 检视。
- 理由：提升多环境可移植性与调试效率，同时保持 CLI/Python API 的兼容路径。

## D-009：Trace 默认脱敏并允许显式关闭

- 决策：Trace 落盘链路默认执行敏感字段脱敏，覆盖 JSONL 与 SQLite `raw_json`；通过配置可显式关闭。
- 补充：脱敏键匹配默认使用 `exact`（可切换 `contains`），避免误伤 `token_estimate` 等业务字段。
- 理由：满足合规最小暴露原则，同时保留受控调试场景下的可追溯性，并降低误脱敏风险。

## D-010：评测口径支持“预期违规且被策略拦截”通过

- 决策：当样本 `metadata.expected_constraint_violation=true` 且运行时出现 `policy_blocked_no_network` 时，按通过计分。
- 理由：该类样本目标是验证策略拦截能力，而非任务执行成功；按失败计分会系统性低估约束治理能力。

## D-011：CLI 默认会话恢复采用 JSON 持久化

- 决策：CLI 默认 `runtime.session_store_backend=json`，会话落盘到 `runtime.session_store_path`（默认 `outputs/sessions`）。
- 理由：保证 `--session-id + --resume` 在跨进程调用时语义一致，避免仅进程内可恢复。
