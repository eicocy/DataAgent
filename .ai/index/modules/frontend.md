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

默认 / 为 AnalysisWorkspace 空会话；/overview 保留旧概览，/templates 提供模板示例。PromptComposer / UploadQueue 复用 Dataset Store/API；仅发送或上传时建立 Session；附件绑定保存服务器 context_json，已绑定附件可选为额外分析输入。能力选项由 api/workspace.js 控制，未实现选项禁用。

SemanticMappingEditor.vue：按会话/数据集隔离请求、候选核对与版本化修正及币种/单位；analysis store 保存完整公开请求选项用于幂等重试和刷新；AgentSteps 显示 V3 依赖/输入/探索关系。模板、深度、模型选择受服务端能力约束，自动报告待 Phase 4。

DocumentCandidatePreview、DataQualityWorkbench、CleaningWorkbench、JoinWorkbench、TransformationPreview：文件候选人工确认、公开质量、固定版本预览/发布、逐对组合键及旧版本；BusinessResult/ForecastResult/resultShape 显示 typed 信息或诚实 normalized-table 降级；api/files.js、utils/transformationFlow.js 复用 API/轮询幂等。

工作台 -> POST analysis/runs -> 轮询状态/Trace -> 表格/图表/报告 -> 历史；报告生成/导出经后台任务队列；文件库读取授权工件；401 -> expireSession -> 登录

## Related

frontend/tests/；frontend/nginx.conf；backend/app/routers/{analysis_runs,charts,reports}.py；backend/app/artifacts/
