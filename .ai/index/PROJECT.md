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
