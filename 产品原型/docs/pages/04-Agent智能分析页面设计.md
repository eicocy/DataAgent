# Agent 智能分析页面设计

## 页面目标

让用户在一个工作台中同时看到数据上下文、自然语言对话、执行证据和结果，使产品区别于普通 ChatBot。

## 三栏结构

- 左栏 DatasetPanel：数据集、字段、质量提示和推荐问题。
- 中栏 ChatPanel：消息、Evidence Rail、错误恢复和 MessageInput。
- 右栏 AnalysisResult：指标、图表、表格、证据和总结。

低于 1024px 时按左→中→右转为纵向，不能隐藏字段或结果入口。

## 执行状态机

首期页面状态为 `idle → submitting → succeeded|partial|failed`。`POST /api/v1/analysis/chat` 同步返回完成后的 ToolCall、ChartSpec 和总结，不展示实时步骤或取消控件。失败保留用户问题；Tool 成功而总结失败时展示真实 Tool Result 并标记 `partial`，不显示伪结论。

## 输入行为

Enter 发送、Shift+Enter 换行，IME 组合期间 Enter 不发送；同步请求期间禁用重复发送，浏览器连接中断不表示服务端任务已停止。用户手动向上滚动后不强制拉回底部。

## API

`POST /api/v1/analysis/chat`；前端按 status 和 tool_calls 渲染，不解析模型文本来构造图表。
