# frontend

## Files

frontend/src/App.vue；router/；stores/auth.js；api/client.js
role: 路由、登录过期清理、Cookie API 与安全错误
depends: Vue Router、Pinia、Axios

frontend/src/views/AnalysisWorkspaceView.vue；stores/analysis.js；api/analysis.js
role: 提问、按会话持久提交 ID、任务轮询与服务端运行记录恢复；取消和旧请求隔离
depends: AgentSteps、AnalysisResult、ChartView

frontend/src/components/{AgentSteps,AnalysisResult,ChartView}.vue；utils/chartOption.js
role: 结构化执行证据、结果表、五类图表与 PNG 导出
depends: ECharts、Element Plus

## Flow

工作台 -> POST analysis/runs -> 轮询状态/Trace -> 表格/图表/报告 -> 历史；401 -> expireSession -> 登录

## Related

frontend/tests/；frontend/nginx.conf；backend/app/routers/analysis_runs.py；backend/app/routers/charts.py
