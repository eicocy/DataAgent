# Agent 与 Tool 数据协议

## ToolCall

```json
{
  "tool_call_id": "tc_01",
  "tool_name": "group_by_analysis",
  "schema_version": "1.0",
  "parameters": {},
  "status": "validating|running|succeeded|failed",
  "started_at": "2026-09-20T15:08:11.242+08:00",
  "finished_at": "2026-09-20T15:08:11.724+08:00",
  "duration_ms": 482,
  "result_summary": "按 region 分为 6 组",
  "error": null
}
```

## ToolError

`{code,message,retryable,parameter?,details?}`；details 只能包含安全上下文。模型内部错误、文件路径、连接信息和堆栈禁止返回。

## AgentExecution

`{status,current_step,steps,tool_calls,started_at,finished_at,duration_ms}`。首期通过同步接口一次性返回完成后的执行证据，不提供实时执行流或服务端取消。steps 是产品级阶段，不包含隐藏思维链。

## 兼容性

Tool 名和 schema_version 写入记录。字段新增优先保持向后兼容；破坏性参数变更提升版本，并让历史详情仍能解释旧版本。
