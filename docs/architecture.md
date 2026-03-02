# 架构设计（v0 系列）

## 1. 模块分层

```text
CLI / Python API
        |
        v
AgentRuntime.run(task, mode, session_id, resume)
        |
        +--> Planner
        |       |
        |       v
        |    PlanNode[]
        |
        +--> Runtime Loop (react / plan_execute)
                |
                +--> Executor ----> ToolRegistry ----> Builtin/MCP Tools
                |        |
                |        +--> ReliabilityManager(timeout/retry/fallback)
                |
                +--> OutputValidator (json/network/rules)
                |
                +--> Critic (continue / stop)
                |
                +--> MemoryManager.sync(session)
                |
                +--> Retriever.search(query)

Cross-cutting: SessionStore, TraceStore, EvalRunner
```

## 2. 双模式执行

### ReActLoop

- 采用多步循环执行（默认 `max_steps-1` 个 action 步 + 1 个 summary 步）。
- 在当前 mock baseline 下，常见收敛路径为“单 action 步 + summary 步”。
- 每轮执行“工具选择 -> 调用 -> 校验 -> memory sync -> critic 决策”。
- 适合探索型、步骤不确定任务。

### PlanExecuteLoop

- 先由 Planner 生成步骤列表，再逐步执行并更新 `PlanNode.status`。
- 每个节点经历 `pending -> in_progress -> completed/failed`。
- 适合结构化、可分解任务。

## 3. 数据流

1. 读取 `TaskSpec` + 配置。
2. 初始化/恢复 `SessionState`（`session_id + resume`）。
3. 预建检索索引（`Retriever.ingest(task.context)`）。
4. 执行 loop：
   - Executor 选择工具；命中 `no network` 策略时前置拦截并标记 `policy_blocked_no_network`；
   - 未命中策略时调用工具；
   - Reliability 检查 timeout/retry/repeat-call；
   - OutputValidator 校验 JSON/规则约束（并保留禁止联网的兜底校验）；
   - MemoryManager 压缩并写入 `session.memory_summary`；
   - Critic 统一决策是否继续。
5. 汇总 `RunResult` 指标（steps/tool_calls/tool_call_success/constraint_retained）。
6. 写入 `TraceEvent`（JSONL + SQLite）并供 EvalRunner 聚合。

## 4. 关键可替换点

- LLM provider（配置预留：mock/openai-compatible，当前默认运行链路仍为离线 mock 行为）。
- Tool adapter（local/http/mcp-style）。
- Retrieval vectorizer（默认轻量实现，可后续替换）。
- Critic 策略（rule-based 起步，后续可混合模型）。
- Output validator 规则集（可按业务扩展）。

## 5. v0.4 增强点

- MCP Adapter Layer：`MCPAdapterLayer` / `RegistryBackedMCPAdapter`。
- 配置治理：`load_config(path, profile, env_prefix)` 支持 profile patch + 环境变量覆盖（如 `ARL_RUNTIME__MAX_STEPS=20`）。
- Trace 检视增强：`inspect-trace` 支持 JSON 输出、tool 过滤、limit 限制、SQLite 直接读取。
