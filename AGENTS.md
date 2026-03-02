# AGENTS（项目级工程严格版）

## 1. 开发原则

- **治理优先**：先保证规范、门禁、可追踪，再增加功能复杂度。
- **KISS / YAGNI**：默认选择最小可行实现，不提前设计未确认需求。
- **向后兼容**：未经明确批准，不破坏已有 CLI/API/数据格式。
- **Mock-first**：默认可离线跑通；真实 LLM Provider 作为可选配置。

## 2. 分支与提交流程

- 分支策略：Trunk-based，直推 `main`，小步提交。
- 提交前必须通过本地门禁：`scripts/ci_local.sh`。
- 提交信息使用 Conventional Commits：`feat:`, `fix:`, `docs:`, `test:`, `chore:`。
- 回滚策略：优先 `git revert <commit>`，禁止改历史强推。

## 3. 质量门禁（Do Not Bypass）

必须通过：

```bash
ruff check src tests
black --check src tests
mypy src
pytest --cov=src --cov-report=term-missing --cov-fail-under=80
```

CI 与本地命令保持等价，不允许出现“本地过、CI 不过”的独立规则。

## 4. 测试矩阵

- 单元测试：types、tool registry、memory、retrieval、validator。
- 集成测试：`react` 与 `plan_execute` 的端到端闭环。
- 回归测试：golden trace 关键字段快照一致性。
- 评测测试：benchmark runner 与报告生成完整性。

关键场景必须覆盖：

1. ReAct 多步工具调用闭环。
2. Plan-Execute 分解执行 + critic 校验。
3. timeout/retry/fallback 可靠性链路。
4. 强约束保持（如“必须 JSON”“禁止联网”）。
5. 重复调用检测与安全终止。
6. trace/eval 字段完整性。

## 5. 回归策略

- 每个功能 PR（或提交批次）至少包含一个回归断言。
- 对非确定性行为使用固定 seed + Mock provider 控制波动。
- golden trace 只比关键字段，避免对自然语言全量逐字匹配。

## 6. 安全红线

- 严禁提交密钥、Token、私钥、个人敏感数据。
- 涉及外部网络调用时，必须提供可替换 mock 路径。
- 工具执行默认最小权限，禁止隐式执行高风险命令。

## 7. 文档与可追踪性

- 关键决策必须记录到 `docs/design_decisions.md`。
- Trace 字段变更必须同步 `docs/trace_schema.md`。
- 评测口径变更必须同步 `docs/eval_protocol.md`。

## 8. Definition of Done (DoD)

一个阶段/功能完成需同时满足：

- 代码、测试、文档三者一致。
- 本地门禁与 CI 全通过。
- 新能力可通过 CLI 或测试复现。
- 风险与限制已在文档明确标注。
