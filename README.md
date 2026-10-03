# DataLens Agent

**当前开发版本 v2.0.0（Phase 4）**：工作台布局、报告版本与高清图表开发中。进展和验收边界见 [Phase 4 开发记录](docs/phase4-implementation.md)。v1.0.0 发布说明及验收见 [v1.0.0](docs/releases/v1.0.0.md) 和 [Phase 3 验收](docs/phase3-acceptance.md)。

中文数据分析工作台：上传 CSV/XLSX，使用自然语言提出问题，核对受控工具的真实计算结果、执行步骤、数据质量说明和 ECharts 图表。模型生成计划和解释，白名单工具执行计算；面向单机小规模部署。

## 项目组成

- backend/：FastAPI、SQLAlchemy、Alembic、Pandas、SQLGlot 和 LangChain 模型适配层。
- frontend/：Vue 3、Pinia、Element Plus、ECharts；任务轮询、会话管理、报告预览及图表导出。
- compose.yaml：MySQL 8、独立迁移、单 worker 后端、Nginx 前端。
- .ai/index/：真实项目导航；docs/：架构、安全、演示与设计取舍。
- 产品原型/ 与中文设计目录是历史设计材料，不代表已运行能力。

## Docker 本机部署

需要 Docker Desktop Linux 引擎正在运行。复制根目录 .env.example 为 .env，替换所有 replace_* 密码为不同随机密码。密码限定 ASCII 字母、数字、下划线、连字符，16–128 字符。SECRET_KEY 用 Python secrets 生成，例如 python -c "import secrets; print(secrets.token_urlsafe(48))"。真实分析需要 DeepSeek Key；缺失 Key 明确失败，不生成模拟答案。

```powershell
Copy-Item .env.example .env
# 编辑 .env 后
 docker compose config --quiet
 docker compose up --build -d
 docker compose ps
```

打开 [工作台](http://localhost:8080)。若8080被占用，在.env设置FRONTEND_PORT（例如8088），端口和后端Origin会同时调整。MySQL 不向宿主暴露端口，前端仅绑定本机。mysql-data 卷保存数据库，app-data 保存上传文件及工件。停止用 docker compose down；down -v 会删除部署数据卷，仅在明确需要全部清除时使用。

初始化只在空 MySQL 卷执行。改 .env 不会自动轮换已有数据库密码；通过受控 MySQL 管理连接轮换账号。迁移账号有业务库 DDL，运行账号只有业务 DML，查询账号只能读取投影库。Compose 是本机开发 HTTP 部署；对外 HTTPS 需生产配置、Secure Cookie、准确 Origin、TLS 与随机凭据。只支持一个后端实例和一个 uvicorn worker。

## 本机开发

Python 3.12、Node.js 24、MySQL 8。复制 backend/.env.example 为 backend/.env，配置业务库、投影写入、只读及迁移连接。

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000
```

另一终端 cd frontend、npm ci、npm run dev，打开 [开发页面](http://localhost:5173)。凭据和用户数据不得提交到 Git。已有投影表升级应先备份、核对类型与行数后切换，不能重新猜测历史数据类型。

## 验证

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm test
npm run build
```

真实 MySQL 测试默认跳过。TEST_MYSQL_URL 指向预建且可丢弃的业务测试库；TEST_MYSQL_PROJECTION_URL 指向另一投影测试库写入账号，TEST_MYSQL_READONLY_URL 指向该投影库 SELECT-only 账号。三个数据库名都限 datalens_test_*。执行 python -m pytest tests/integration -q，测试验证原迁移到 head 的记录保留、投影读取、写入拒绝以及业务 users 读取拒绝。测试创建/删除记录和随机表，禁止指向业务部署库。CI 使用隔离 MySQL 8，不调用付费模型。

2026-10-03 的 v1.0.0 验收：当前数据库迁移为 `0008_agent_orchestration`；后端完整测试在专用真实 MySQL 连接下 **439 passed、0 skipped**；前端 **29 项单测、构建、模拟 API 浏览器与真实服务浏览器**均通过。真实 DeepSeek 流程覆盖上传、会话、数据集消歧、固定版本追问、计算工件复用、取消、SSE 重连、Evidence 与跨用户隔离。样例、运行结果及环境限制见 [验收记录](docs/phase3-acceptance.md)。

[架构](docs/architecture.md) · [安全](docs/security.md) · [演示](docs/demo.md) · [设计取舍](docs/interview-notes.md) · [后端](backend/README.md)
