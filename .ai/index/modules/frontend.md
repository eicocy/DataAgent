# frontend

## Files

frontend/src/App.vue；router/；stores/auth.js；api/client.js
role: 路由、登录过期清理、Cookie API 与安全错误
depends: Vue Router、Pinia、Axios

frontend/src/views/AnalysisWorkspaceView.vue；stores/analysis.js；api/analysis.js
role: 提问、按会话持久提交 ID、任务轮询与服务端运行记录恢复；取消和旧请求隔离
depends: AgentSteps、AnalysisResult、ChartView

frontend/src/components/{AgentSteps,AnalysisResult,ChartView,ReportWorkbench}.vue；utils/chartOption.js
frontend/src/views/ArtifactsView.vue；frontend/src/api/{charts,reports}.js
role: 结构化执行证据、结果表、ECharts 交互图、300 DPI 图表工件、多格式报告编辑/导出及文件库预览
depends: ECharts 6、Element Plus；文件预览使用浏览器 PDF/HTML 能力

## Flow

默认 / 为 AnalysisWorkspace 空会话；/overview 保留旧概览，/templates 提供只读模板示例。PromptComposer / UploadQueue 复用 Dataset Store/API；仅发送或上传时建立 Session；附件绑定保存服务器 context_json，当前分析仍单数据集。能力选项由 api/workspace.js 控制，未实现选项禁用。

工作台 -> POST analysis/runs -> 轮询状态/Trace -> 表格/图表/报告 -> 历史；报告生成/导出经后台任务队列；文件库读取授权工件；401 -> expireSession -> 登录

## Related

frontend/tests/；frontend/nginx.conf；backend/app/routers/{analysis_runs,charts,reports}.py；backend/app/artifacts/
