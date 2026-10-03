# Backend

Python 3.12 / FastAPI。安装 requirements-lock.txt，复制 .env.example 为 .env，执行 alembic upgrade head，再运行 uvicorn app.main:app --port 8000。部署只能使用单实例、单 worker；开发重载会中断执行任务。

## 连接与授权

- DATABASE_URL：datalens_agent，业务 SELECT/INSERT/UPDATE/DELETE。
- MIGRATION_DATABASE_URL：独立迁移账号，业务库 DDL/DML。
- PROJECTION_DATABASE_URL：datalens_data，投影 CREATE/DROP/INSERT/SELECT。
- SQL_READONLY_DATABASE_URL：投影库 SELECT-only，无业务表读取权限。

服务器生成 dataset_<id> 表名，模型不能指定连接、用户或路径。旧投影应先备份、复制、核对类型与行数，再切换定位；不改写历史 Alembic 迁移。

升级旧投影前停止 API/任务执行并备份。`python scripts/migrate_projections.py` 默认干运行；确认后 `python scripts/migrate_projections.py --apply` 按反射字段类型分块复制，核对行数后更新定位，保留源表。目标已存在会拒绝覆盖；失败时先检查残留目标表，不要盲目重试或删除源表。

## 执行接口

API 根路径 /api/v1，Cookie JWT 使用 HttpOnly/SameSite=Lax，浏览器写请求校验准确 Origin。缺少 Key 返回明确错误。

- POST /analysis/runs 提交后台任务；GET /analysis/runs/{record_id} 查询。
- GET /analysis/runs/{record_id}/events 读取持久 SSE 事件，支持 `Last-Event-ID`；POST /analysis/runs/{record_id}/cancel 请求取消。
- GET /analysis/runs/{record_id}/trace 返回结构化步骤。
- GET /analysis/runs/{record_id}/results/{artifact_id} 授权分页，最多 100 行。
- GET /charts/{artifact_id} 返回授权 ChartSpec。
- POST /analysis/chat 保留同步返回格式，使用相同执行服务。
- /health 与 /health/live 是相同存活检查；/health/ready 验证数据库连接及当前 Alembic head（现为 0008），返回 model_configured 标志，不等同真实模型或投影连接可用验证。

Phase 3 的 `/analysis/runs` 支持无数据集一般聊天、同会话切换数据集、结构化意图路由及歧义澄清。分析固定 `dataset_version_id`，生成并校验 v2 `AnalysisPlan`，再按依赖调度步骤。任务详情同时返回旧字段与 `agent_response`、工件、Evidence、进度和当前步骤。图表追问复用同版本未过期的计算工件；过滤追问复用定义未变的上游步骤。服务端只允许 Registry 中的只读聊天 Tool，清洗请求仅进行质量分析及建议。取消运行中任务由单实例监督器终止子进程，保留已完成证据，不跨重启自动续跑。

模型通过同步 Provider 接口选择 `LLM_PROVIDER=deepseek` 或 `openai`；离线测试使用 Fake Provider。提示模板按用途和版本放在 `app/agent/prompt_templates/`。`llm_call_records` 仅记录提供方、模型、模板版本、Token、耗时与安全错误码，不保存原始提示或数据。

Pydantic 校验模型边界。完整中间结果、API 预览、模型摘要分别处理。Trace 展示参数和证据，不展示隐藏思维链。ARTIFACT_DIR 和 UPLOAD_DIR 是受控服务器目录；不执行模型 Python/Shell，不使用 pickle。

## 验证

python -m pytest -q。MySQL 集成测试需要 TEST_MYSQL_URL 指向 datalens_test_* 业务测试库，TEST_MYSQL_PROJECTION_URL 指向另一投影测试库，TEST_MYSQL_READONLY_URL 指向投影测试库 SELECT-only 账号。测试会执行0001→带已有记录→0003→head迁移，以及投影读取/写入拒绝/业务 users 读取拒绝。会创建/删除记录与随机表，未配置的跳过不能算真实 MySQL 验证。

历史0002/0003迁移保持原文件。在 MySQL 运行上下文中，强制重建 batch 的操作适配为原生 ALTER，避免临时表复制同名外键造成 schema 级名称冲突；SQLite 保留原重建路径。CI 从0001插入记录再升级到当前 head，核对记录和 Schema，验证此兼容适配。

根目录 Compose 在迁移成功后启动后端。日志不输出 Key、连接串、SQL 字面量或上传数据。v1.0.0 的数据库迁移版本为 `0008_agent_orchestration`；配置专用真实 MySQL 连接的完整后端回归为 **439 passed、0 skipped**。真实模型与浏览器验收、数字绑定、取消和 SSE 重连证据见 [Phase 3 验收](../docs/phase3-acceptance.md)。
