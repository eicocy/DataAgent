# Tool 调用与结果展示设计

## 核心原则

Tool Call Card 是可信分析的核心。它展示 Tool 名、结构化参数、状态、耗时和结果摘要，但不展示模型隐藏思维链、任意代码或敏感连接信息。

## 卡片字段

`tool_call_id`、`tool_name`、`parameters`、`status`、`started_at`、`finished_at`、`duration_ms`、`result_summary`、`error`。

## 状态

- validating：显示参数校验。
- running：显示 Tool 正在真实计算，不给伪百分比。
- succeeded：青绿色证据标识，允许查看结果。
- failed：显示可理解原因、影响和重试入口。
- partial：计算结果已保存，但模型总结不可用；原始计算结果仍可核对。

## 结果规则

表格和 ChartSpec 必须直接消费 Tool Result；AI Summary 只能引用该结果。大结果只传摘要和有限预览，完整数据通过分页接口查看。
