# DataLens Agent

type: 单体全栈数据分析工作台，单实例部署
stack: Python 3.12 / FastAPI / SQLAlchemy / Alembic / MySQL 8 / Pandas / SQLGlot / LangChain；Vue 3 / Vite / Pinia / ECharts 6
architecture: 用户认证 -> 固定 DatasetVersion -> DatasetContext -> Registry/AnalysisEngine -> 类型化结果验证 -> 工件/执行记录 -> Agent 与内部调用方
entry: backend/app/main.py；frontend/src/main.js；compose.yaml
modules: datasets；analysis（agent 编排与 analysis 通用工具包）；frontend；auth（backend/app/routers/auth.py + backend/app/security.py）
infrastructure: backend/app/config.py、database.py；backend/migrations/；deploy/mysql/init-users.sh；.github/workflows/ci.yml
navigation: MODULES.md；源码优先于索引；中文设计目录与产品原型是历史资料
phase2: docs/tool-development.md、analysis-capabilities.md、phase2.md；0007_analysis_engine；不开放通用工具执行 API
phase4-v2.0.0: docs/phase4-implementation.md；0009_workspace_reports；多格式上传、图表渲染与版本化报告；开发验收状态，不是正式发行
ai-workspace-upgrade: docs/UPGRADE_PLAN.md、UPGRADE_PROGRESS.md、phase2-workspace.md、phase3-workspace.md；Phase 1 对话入口/上传队列；Phase 2 版本化 Profile、语义、多输入 Plan 3.0/DAG/预算；Phase 3 文件确认/版本清洗/受限 Join/业务计算/预测，0011；工件留存/自动交付/沙箱待 Phase 4/5
