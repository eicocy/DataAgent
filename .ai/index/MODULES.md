# Modules

Phase 4 v2.0.0 additions: see `docs/phase4-implementation.md` for session workspace, expanded data formats, chart rendering, report versions/export, artifact preview/download, and acceptance status.

V2.0.5 Phase 5: `backend/app/sandbox/` provides default-off restricted execution through `deploy/sandbox/broker.py` and fixed Docker images; `deploy/backup.py`, `compose.sandbox.yaml`, `docs/operations.md` provide backup and deployment preparation. No public arbitrary-code API; database head remains 0012. Scope and actual validation: `docs/phase5-workspace.md`.

## datasets
path: backend/app/services/datasets.py；backend/app/routers/datasets.py
role: 表格/文档上传、候选确认、类型/质量画像、固定版本投影与授权加载、清洗/Join 发布
entry: /api/v1/datasets；DatasetService
depends: models、database、config
index: modules/datasets.md

## analysis
path: backend/app/agent/；backend/app/analysis/；backend/app/tools/；backend/app/services/
role: 结构化计划、通用 Registry/Engine、类型化工具、中间工件、后台任务与执行证据
entry: backend/app/routers/analysis.py；analysis_runs.py
depends: datasets、models、model provider、database
index: modules/analysis.md

## frontend
path: frontend/src/
role: 认证、数据集、分析任务、结果与图表工作台
entry: frontend/src/main.js；App.vue；router/
depends: api/client.js、Pinia、ECharts
index: modules/frontend.md
