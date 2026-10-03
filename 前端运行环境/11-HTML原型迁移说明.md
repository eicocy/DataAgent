# HTML 原型迁移说明

| 原型 | Vue View | 主要组件 |
|---|---|---|
| auth/login.html | LoginView | AuthLayout/LoginForm/PasswordField |
| dashboard/dashboard.html | DashboardView | MetricCard/RecentDatasetTable |
| datasets/* | Dataset*View | DatasetTable/Uploader/Preview/ColumnTable |
| analysis/analysis-workspace.html | AnalysisView | DatasetPanel/ChatPanel/EvidenceRail/Result |
| charts/* | ChartView | ChartPanel/ChartConfigPanel |
| sessions/session-list.html | SessionListView | SessionTable/DeleteDialog |
| history/* | History*View | HistoryTable/RecordDetail |

迁移时保留信息架构、状态、文案和 Token 语义；用 Element Plus/自有组件替换原型 DOM；用 Pinia/API 替换 mock-data；用 ECharts 替换内联 SVG。原型中的 Toast、Dialog、Tab 交互只是行为示意，正式实现必须具备完整焦点管理、路由状态和错误恢复。
