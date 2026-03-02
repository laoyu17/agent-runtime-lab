# Trace Schema 规范

## 1. 目标

Trace 用于记录每一步执行证据，支持：

- 调试（定位失败点）
- 回归（golden trace 比对）
- 评测（统计 steps/latency/tool success）

## 2. 必填字段

每条 `TraceEvent` 至少包含：

- `session_id`: 会话标识
- `step_id`: 步骤 ID
- `mode`: `react` | `plan_execute`
- `thought_summary`: 当前轮思考摘要（不记录敏感原文）
- `selected_tool`: 选择的工具名（无工具为 `none`）
- `tool_input`: 工具输入（来自 `step.tool_call.arguments`）
- `tool_output`: 工具输出（优先 `step.tool_result.output`，否则 `step.observation`）
- `state_update`: 状态更新摘要（如 `tool_step_completed`、`summary_completed`）
- `latency_ms`: 本步耗时
- `token_estimate`: token 估算
- `timestamp`: ISO8601 时间戳

## 3. JSONL 示例

```json
{"session_id":"s1","step_id":"step-1","mode":"react","thought_summary":"compute 2+2","selected_tool":"calculator","tool_input":{"expression":"2+2"},"tool_output":{"expression":"2+2","value":4.0},"state_update":"tool_step_completed","latency_ms":12,"token_estimate":31,"timestamp":"2026-03-02T12:00:00Z"}
```

## 4. SQLite 落盘列

当前 `trace_events` 表包含：

- `session_id`（index）
- `step_id`
- `mode`
- `selected_tool`
- `latency_ms`
- `token_estimate`
- `timestamp`（index）
- `raw_json`

## 5. 隐私与合规边界

- Trace 默认开启敏感信息脱敏：`TraceConfig.redact_sensitive=true`。
- 默认脱敏键：`api_key`、`token`、`cookie`、`password`、`authorization`、`secret`（支持嵌套结构）。
- 默认键匹配模式：`TraceConfig.redact_match_mode=exact`（可选 `contains`）。
- JSONL 与 SQLite(`raw_json`) 使用同一脱敏结果，避免双轨不一致。
- 可通过 `TraceConfig.redact_sensitive=false` 显式关闭（仅用于受控调试场景）。
