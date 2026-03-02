# ROADMAP

## G0：仓库治理与工程基线（当前阶段）

目标：建立可持续开发基线（目录、规范、门禁、文档）。

退出条件：

- 新环境一条命令安装并可执行本地门禁。
- CI 覆盖 lint/type/test/coverage，且阈值 `>=80%`。
- README + AGENTS + 核心 docs 可指导新贡献者当天上手。

## V0.1：最小可闭环 Runtime

目标：三层架构 + 双范式 + tool/session/memory/RAG/trace 全链路。

退出条件：

- `run-task` 在 `react` 与 `plan_execute` 下均可跑通。
- 默认 Mock 模型可演示，无需 API Key。
- 至少 3 个 example task 可复现实验。

## V0.2：可靠性与上下文治理增强

目标：失败恢复、上下文压缩、约束保持与规则校验。

退出条件：

- 故障注入测试通过（timeout/empty/error/repeat）。
- 约束保持率有可量化提升。

## V0.3：评测体系与报告产出

目标：20 条基准任务 + 指标计算 + Markdown/HTML 报告自动生成。

退出条件：

- 一键运行 benchmark 并导出报告。
- 报告含总览、分场景、失败切片、改进建议。

## V0.4：生态兼容与展示增强

目标：增强 MCP 适配、配置 profile、trace 查看体验。

退出条件：

- MCPCompatibleTool 协议稳定。
- 至少一个可替换 adapter 示例可运行。
- 配置系统支持 profile + env override + schema 校验。
