# frontend

V2.0.6 对话布局：AppShell.chat 隔离滚动与管理页样式，AnalysisWorkspace 默认单栏且不自动打开右侧。ChatMessage 绑定原 record_id；SafeMarkdown 使用 markdown-it@15.0.3（html/image 关闭、安全链接），LazyChart 管理视口挂载与释放。utils/chatResults 按 expected_outputs/图表来源/旧保存顺序选择去重结果；AnalysisResult.presentation 默认 full，chat 展示两图一表十行，ForecastResult/BusinessResult/DataQualityWorkbench 可选 compact 模式，必要单位/限制保留。

消息 preview/files/report/retry -> 工作台独立 previewSelection/AbortController/reportSource；表分页始终用原 record_id+artifact_id，Run 工件身份再经 reportsApi.artifact 读取授权文件详情。重新分析使用原公开配置、输入版本和新幂等请求；附件选择、多输入、字段/文档确认合并到附件设置。手机全屏预览的 inert/Tab/Escape 和焦点返回由工作台管理，原上传/任务订阅/中断/幂等 API 不变。详情与截图：docs/v2.0.6-chat-interface.md；回归：tests/chat-presentation.test.js、analysis-workspace.test.js 及既有 e2e。

V2.0.6: utils/errorInfo.js 归一化任务错误和安全复制；ErrorInfoPanel.vue Options API 展示原因/建议/详情/手动复制，业务页负责 retry；api/client.js 区分 HTTP_REQUEST_TIMEOUT 并保留 Error.info；AnalysisScope.vue 显示提交快照；AgentSteps 用中文操作名，工具与参数折叠。

诊断补修：ErrorInfoPanel 默认显示醒目类别、具体原因、如何处理与完成步骤，技术信息折叠且省略空项；api/client 和 taskError 优先 Error.info.reason；诊断副本支持实际数量/长度及离线复核来源标记，不复制原始数据。

## Files

frontend/src/App.vue；router/；stores/auth.js；api/client.js
role: 路由、登录过期清理、Cookie API 与安全错误
depends: Vue Router、Pinia、Axios

frontend/src/views/AnalysisWorkspaceView.vue；stores/analysis.js；api/analysis.js
role: 提问、按会话持久提交 ID、任务轮询与服务端运行记录恢复；取消和旧请求隔离
interrupt: PromptComposer 的 interrupt 事件与工件面板入口 -> cancelTask -> analysis store.cancel -> 既有 /analysis/runs/{id}/cancel；继续订阅至服务端终态，未受理时禁用，取消请求跟随会话 signal。
composer: PromptComposer.vue 负责输入自适应、单行工具栏、配置摘要和 attachments 命名插槽（兼容默认插槽）；ComposerSettingsPopover.vue Options API 管理五项即时设置、传送弹层与键盘焦点，仍通过 option-change/template-select 交回输入区与工作台。
depends: AgentSteps、AnalysisResult、ChartView

frontend/src/components/{AgentSteps,AnalysisResult,ChartView,ReportWorkbench}.vue；utils/chartOption.js
frontend/src/views/ArtifactsView.vue；frontend/src/api/{charts,reports}.js
role: 结构化执行证据、结果表、ECharts 交互图、300 DPI 图表工件、多格式报告编辑/导出及文件库预览
depends: ECharts 6、Element Plus；文件预览使用浏览器 PDF/HTML 能力

## Flow

默认 / 为 AnalysisWorkspace 空会话；/overview 保留旧概览，/templates 提供模板示例。PromptComposer / UploadQueue 复用 Dataset Store/API；仅发送或上传时建立 Session；附件绑定保存服务器 context_json，已绑定附件可选为额外分析输入。能力选项由 api/workspace.js 控制，未实现选项禁用。

SemanticMappingEditor.vue：按会话/数据集隔离请求、候选核对与版本化修正及币种/单位；analysis store 保存完整公开请求选项用于幂等重试和刷新；AgentSteps 显示 V3 依赖/输入/探索关系。模板、深度、模型及报告类型由服务端能力约束。

DocumentCandidatePreview、DataQualityWorkbench、CleaningWorkbench、JoinWorkbench、TransformationPreview：文件候选人工确认、公开质量、固定版本预览/发布、逐对组合键及旧版本；BusinessResult/ForecastResult/resultShape 显示 typed 信息或诚实 normalized-table 降级；api/files.js、utils/transformationFlow.js 复用 API/轮询幂等。

工作台 -> POST analysis/runs -> 轮询状态/Trace -> 表格/图表/报告 -> 历史；自动报告在原分析任务直接交付，手动报告经原队列；文件库读取授权工件；401 -> expireSession -> 登录

Phase 4：ArtifactWorkspace/MentionPicker/ArtifactPreview + stores/workspace.js。GET/PATCH workspace 恢复最新分析、成果、报告和选择，按顺序保存选择并隔离旧会话响应；共享预览由 ChartView/结构化 document/有界表/安全 HTML/PDF 承担。ReportWorkbench 打开已有报告、保存新版本并保持创建/导出请求 ID，报告记录不覆盖最新分析。详情见 docs/phase4-workspace.md。

## Related

frontend/tests/；frontend/nginx.conf；backend/app/routers/{analysis_runs,charts,reports}.py；backend/app/artifacts/
