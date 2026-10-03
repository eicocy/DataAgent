# Phase 3 验收

## 执行链

`POST /analysis/runs` 校验用户与会话，固定本次数据集版本并入队。子进程读取有界 `ConversationContext`，依次经过 `IntentRouter → DatasetResolver → ContextBuilder → Planner → PlanValidator → WorkflowExecutor → ResultInterpreter`。工具只从真实 Registry 选择；执行结果写入工件，计划步骤保存状态和引用。解释器选择事实路径，服务端读取真实数值并渲染回答。Trace、任务详情和 SSE 从数据库读取，不依赖浏览器状态。

没有数据集的 `GENERAL_CHAT` 不产生计划；数据集含糊时返回 `waiting` 和候选 ID。`DATA_CLEANING` 只允许只读质量分析，并明确不能在聊天入口执行清洗或发布版本。单实例监督器负责运行、超时和取消；进程中断后明确终结任务，不自动续跑。

追问只复用同一固定版本、未过期且当前用户有权读取的工件。工件过期时重新计算受影响路径；原固定版本不可访问时返回 `waiting` 和恢复版本或重新选择数据集的提示。

## 本地离线验证

在 `backend` 目录运行 `./.venv/Scripts/python.exe -m pytest -q`。`test_phase3_scenarios.py` 覆盖 A/B/D/E；`test_phase3_plan.py` 覆盖 F/G/H；`test_phase3_api.py` 覆盖无数据集、歧义、自然语言切换、图表复用、跨用户隔离和模型元数据记录；`test_phase3_events.py` 覆盖取消及 SSE 重连；`test_phase3_storage.py` 覆盖空库和带旧记录的 0007→0008 升级。测试使用 Fake Provider，不调用真实模型。

在 `frontend` 目录运行 `npm test -- --run`、`npm run build`、`npm run test:e2e`。浏览器用例使用受控 API，覆盖注册、上传、预览、后台任务刷新恢复和历史结果。真实 MySQL 和真实模型应与离线测试分开验收。

## 人工流程

1. 执行 `alembic upgrade head`，启动单实例后端和 Vue 前端。上传包含地区、产品、日期和销售额的 CSV。
2. 新建无数据集会话，发送“你好”；确认没有 Plan 或 Tool 调用。
3. 上传第二个文件，问“汇总销售额”；确认收到待选择数据集的澄清。选择文件后发送问题，检查任务详情中的固定版本、v2 Plan、步骤状态、Artifact 与 Evidence。
4. 问“只看华南”；查看上下文继承与 Trace。问“换成柱状图”；确认汇总步骤标记 `reused`，只新增图表 Tool 调用。
5. 运行中点击“取消任务”，检查任务状态 `cancelled`、未完成步骤 `CANCELLED`、已完成工件仍可读取。断开 SSE 后用任务详情和 `Last-Event-ID` 重连。

真实模型的输出受数据和提供方影响；验收应核对实际计划、事实路径和执行结果，不把演示文案当固定断言。

## 2026-10-03 真实环境验收

验收环境使用独立 Compose 项目 `datalens-accept-eb86bed9`，前端在 `http://localhost:8088`。恢复时保留了原 MySQL 数据卷和根目录 `compose.yaml` 的用户修改；升级前另存数据库备份在本地私有验收目录。MySQL 最初退出码为 255，`OOMKilled=false`，当时的 MySQL 末尾日志只有正常 ready 记录，没有报错或关闭原因；能确定服务中断及原配置未自动重启，不能从保留日志确定 255 的精确原因。新增 [验收用 Compose 覆盖文件](../deploy/compose.acceptance.yaml) 将 MySQL 重启策略设为 `unless-stopped`。当前 MySQL、后端、前端均恢复运行，后端与前端镜像已按当前源码重建。

数据库验收使用三个独立 `datalens_test_*` schema：业务迁移库、投影库和空库；迁移、投影写入、投影只读账号分别连接。空库直升到 `0008_agent_orchestration`。业务迁移库从旧迁移开始，先写入旧用户、数据集、会话、分析记录及 `0007` 固定版本关联，再升级 `0008`，逐项检查保留情况，并写入无数据集会话、事件、模型调用记录。只读账号的写入拒绝和无业务库权限由 MySQL 集成测试检查。现有应用库升级至 `0008_agent_orchestration`，旧用户数据集原样保留；旧上传的数据集版本补齐后可读取。

`/health/ready` 的 `model_configured` 按当前 `llm_provider` 检查对应 Key 是否存在，只代表配置状态。DeepSeek 的有效性由真实文本和分析调用确认；OpenAI 曾在宿主机凭据下返回 401，缺少有效凭据，未计入本次真实模型通过项。

真实浏览器验收使用两名临时用户、两个 CSV。首个 CSV 的华南销售额为 `10+30=40`、华东为 `20+40=60`；第二个将华南第一条改为 `100`，预期华南为 `130`、华东为 `60`。测试通过真实 Vue、后端、MySQL、DeepSeek，不模拟 API；过期和不可用版本由仅能操作 `p3_live_*` 测试用户记录的 [受限控制脚本](../backend/tests/live_control.py) 注入。被拒绝的模型总结保留正确工件并返回明确部分成功；修复后的解释器仅在同一事实集上重试一次，不放宽数字绑定。

运行真实浏览器用例时，先启动独立验收服务，然后在 `frontend` 中设置 `LIVE_E2E_ORIGIN=http://localhost:8088` 和 `LIVE_E2E_CONTROL_CONTAINER=datalens-accept-eb86bed9-backend-1`，执行 `npx playwright test --config playwright.live.config.js`。完整自动化断言位于 [phase3.spec.js](../frontend/tests/live/phase3.spec.js)。测试库连接使用本地私有配置，不提交账号密码。

### 实测结果

| 范围 | 结果 | 证据要点 |
|---|---|---|
| 服务与迁移 | 通过 | MySQL healthy；前后端运行；`/health/ready` 为 HTTP 200，`model_configured=true`；应用库版本 `0008_agent_orchestration`。MySQL 重启策略为 `unless-stopped`。 |
| 真实 MySQL | 通过 | 空库直升 0008、带旧数据的 0007→0008、版本关联保留、事件与模型调用记录写入、投影只读账号拒写且不能读业务用户表；四项集成测试均执行。 |
| 真实 DeepSeek | 通过 | `deepseek-flash` 文本、意图路由、规划、实际工具调用及事实绑定总结完成；持久记录 provider、model、Prompt 版本、Token、耗时、状态和安全错误码，没有原始 Prompt 字段。 |
| 后端完整回归 | **439 passed，12 warnings，0 skipped** | 使用专用真实 MySQL 的迁移、投影写入和投影只读连接运行完整 pytest。 |
| 前端单测和构建 | **29 passed；构建通过** | `npm test -- --run`、`npm run build`。 |
| 模拟 API 浏览器 | **1 passed** | `npm run test:e2e`；Windows 当前保留端口 5175，测试默认端口改为 5275，可用 `PLAYWRIGHT_E2E_PORT` 覆盖。 |
| 真实服务浏览器 | **1 passed，15 项检查** | 完整流程执行 1.8 分钟，实际结果清单及模型调用元数据见 [机器结果](evidence/phase3-live-results-2026-10-03.json)，界面见 [浏览器截图](evidence/phase3-live-browser-2026-10-03.png)。 |

真实浏览器记录：无数据集聊天为 run 54；数据集歧义后选择第一个文件，run 56 返回华南 `40`、华东 `60`，并有 Evidence；run 57 “只看华南”保持版本 29 且返回 `40`；run 58 “换成柱状图”中两个计算步骤复用旧工件，只有 `generate_chart` 是新调用。工件过期后 run 59 在同一版本重算；临时标记原版本不可用时 run 60 返回 `waiting` 且没有 Tool 调用。切换至第二个文件后 run 61 的版本为 30、地区汇总为华南 `130` 与华东 `60`，会话过滤条件为空。run 62 排队取消，run 63 运行中取消，后者已完成步骤的工件可继续读取。SSE 断线期间任务查询恢复，以及通过 `Last-Event-ID` 重放剩余事件，均由真实 API 断言。第二个用户读取任务、Trace、事件、工件和执行取消均被拒绝。

真实模型偶尔返回协议外结构或未通过事实绑定。路由和解释各最多修复一次，并受整体模型调用预算约束；若仍未通过，任务明确请求澄清或保留正确计算工件为 `partial`。MySQL 曾退出 255 的精确宿主或引擎原因缺少当时的错误日志，未声称已查明。OpenAI 真实调用仍待有效凭据，可用后单独验收；本次主验收提供方是 DeepSeek。
