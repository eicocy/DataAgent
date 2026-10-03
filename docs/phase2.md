# Phase 2 Summary

2026-10-02。范围为 Reusable Analysis Tool System + Python Analysis Engine；保留本轮开始前的 Phase 1 工作区成果及 compose.yaml 用户修改。实现完成，真实 MySQL 与真实模型验收状态单独标记，不以替身测试替代实测结论。

## Completed

- 通用 Context、显式 Registry、类型化输入/结果、安全错误、共享计算与 AnalysisEngine。
- 51 个规范工具和 11 个旧接口 Adapter；九个清洗工具仅允许可信内部显式调用。
- 内部工具任务、幂等执行记录、Agent attempt 记录、双归属工件、阶段预算及 0007 迁移。
- 隔离版本投影、固定版本加载/SQL、锁定源版本发布与持久暂存补偿；原文件及旧版本保留。
- 注册工具组合 EDA、规则图表推荐、内部 ChartSpec 2.0 八类图表；旧前端继续使用 ChartSpec 1.0。
- 工具开发指南、自动生成能力目录、架构及项目索引。

## Reused Existing Components

Planner、WorkflowExecutor、DatasetService、Phase 1 ResultValidator/事实渲染/Schema/Profile/版本基础、ArtifactStore、BackgroundJob、TaskSupervisor、固定可信子进程入口和 CleanupTask。使用现有 Pandas/NumPy，不引入新服务或动态执行环境。

## Architecture Changes

`授权 DatasetVersion → DatasetContext → Registry → 输入/权限校验 → 工具计算 → 类型化结果 → ResultValidator → 工件与 ToolExecutionRecord → Agent / 内部调用方`。

旧 DatasetTools 是 Context/Registry/Engine 的兼容门面；旧算法集中于兼容计算模块并复用共享聚合/过滤/排序与通用 GroupBy。计算不再集中在 FastAPI 服务文件。SQL Adapter 保留已授权只读连接的基础设施边界。

清洗使用独立工作数据。发布在 Dataset 锁内检查所有者、租约和 source_version=current，创建父子版本及新投影，不覆盖旧表。版本旧 Schema 的 storage_type 缺失时，从旧版本自己的 dtype/语义恢复。SQL AST 把逻辑 dataset_ID 映射到固定版本物理投影。

## New Tools

实际注册目录由 [analysis-capabilities.md](analysis-capabilities.md) 展示并可重新生成。

| 分组 | 数量 | 实现 |
|---|---:|---|
| 数据 | 8 | overview、column summary、select/filter/sort/sample、unique/value counts |
| 聚合 | 10 | aggregate/groupby/multi、pivot/crosstab、rank/top/bottom、share/weighted average |
| 有序统计 | 4 | cumulative sum、percentage change、growth rate、rolling statistics |
| 基础统计 | 9 | descriptive、percentile/quantile、variance/std、skewness/kurtosis、covariance/correlation |
| 质量 | 8 | missing、duplicates、constant、cardinality、invalid numeric/datetime、infinite、outliers |
| 清洗 | 9 | fill/drop missing、deduplicate、convert/parse datetime、replace/normalize/rename、outlier treatment |
| EDA/图表 | 3 | eda、chart_recommendations、chart_spec |

## Refactored Tools

旧 get_dataset_info、preview_data、filter_data、aggregate_data、group_by_analysis、sort_data、sql_query、generate_chart、describe_data、time_group_analysis、growth_analysis 的名称、参数及输出字段保留。avg/count_distinct 只在兼容边界映射为 mean/nunique。Planner 白名单与工具发现来自 Registry；聊天工具按可信权限过滤。

## New Models

DatasetContext、ExecutionContext、ToolMetadata/AnalysisTool Protocol、ToolExecutionRequest、AnalysisResult、Table/Aggregation/Statistics/Correlation/Quality/Cleaning/Overview/EDA/Chart/Recommendation 结果及其类型化子结构、ToolError 层级、持久 ToolExecutionRecord。Schema 增加可兼容旧版本的 storage_type；工件增加互斥的聊天记录或独立执行归属。

## Files Created

本轮新增 35 个交付文件。此前 Phase 1 新建但尚未跟踪的文件不重复算作 Phase 2 新增。

```text
backend/app/analysis/__init__.py
backend/app/analysis/aggregation_tools.py
backend/app/analysis/catalog.py
backend/app/analysis/chart_tools.py
backend/app/analysis/cleaning_tools.py
backend/app/analysis/context.py
backend/app/analysis/data_tools.py
backend/app/analysis/eda.py
backend/app/analysis/engine.py
backend/app/analysis/errors.py
backend/app/analysis/inputs.py
backend/app/analysis/legacy_adapters.py
backend/app/analysis/legacy_calculations.py
backend/app/analysis/legacy_inputs.py
backend/app/analysis/models.py
backend/app/analysis/operations.py
backend/app/analysis/quality_tools.py
backend/app/analysis/registry.py
backend/app/analysis/serialization.py
backend/app/analysis/sql_safety.py
backend/app/analysis/statistics_tools.py
backend/app/services/tool_execution.py
backend/migrations/versions/0007_analysis_engine.py
backend/scripts/generate_tool_catalog.py
backend/tests/test_analysis_engine.py
backend/tests/test_eda_charts.py
backend/tests/test_phase2_boundaries.py
backend/tests/test_phase2_runtime.py
backend/tests/test_quality_cleaning.py
backend/tests/test_tool_catalog_contracts.py
backend/tests/test_tool_system.py
backend/tests/test_version_transform.py
docs/analysis-capabilities.md
docs/phase2.md
docs/tool-development.md
```

## Files Modified

本轮修改 25 个已有文件；包括此前 Phase 1 已在工作区的 Schema/Profile 文件。其他已有 Phase 1 差异仍保留。

```text
.ai/index/MODULES.md
.ai/index/PROJECT.md
.ai/index/modules/analysis.md
.ai/index/modules/datasets.md
backend/.env.example
backend/README.md
backend/app/agent/executor.py
backend/app/agent/planner.py
backend/app/agent/schemas.py
backend/app/config.py
backend/app/datasets/profiler.py
backend/app/datasets/schemas.py
backend/app/models.py
backend/app/routers/datasets.py
backend/app/services/analysis.py
backend/app/services/analysis_agent.py
backend/app/services/analysis_tools.py
backend/app/services/artifacts.py
backend/app/services/datasets.py
backend/app/services/jobs.py
backend/app/task_runner.py
backend/app/tools/registry.py
backend/requirements.txt
backend/tests/integration/test_mysql.py
docs/architecture.md
```

删除文件：无。未修改 0001—0006、前端业务代码或用户 compose.yaml 差异。

## Tests Added

八个 Phase 2 测试文件如上。所有 51 个规范工具都有真实计算、输入不变、非法字段/参数、错误类型、必需参数、空表与缺失输入的契约检查；该目录测试共 205 项。额外检查 BIGINT 精度/溢出、窗口、逐对相关性、矩阵预算、类型/范围不变量、权限 manifest、幂等冲突、版本 CAS、租约、中断、写工件后超时回滚、多版本删除与工件授权。

新增 opt-in 真实 MySQL 双连接竞争发布测试，并将已有真实迁移测试的 head 从常量改为当前 Alembic head。测试未配置专用数据库时跳过，不将 SQLite CAS 测试宣称为真实 MySQL 并发结果。

## Test Results

2026-10-03 收尾验证结果如下。后端全套使用隔离 SQLite；真实 MySQL 测试另用随机命名的临时测试库，执行后已删除。

| 验证 | 执行方式/环境 | 结果 |
|---|---|---|
| 后端全套 | pytest -q -rs -o addopts=''，隔离 SQLite 与临时目录，模型 Key 清空 | 379 passed、4 skipped、7 warnings；4 项均需专用 MySQL 测试库 |
| 真实 MySQL | MySQL 8.0.46、专用临时 datalens_test_* 库，tests/integration/test_mysql.py | 3 passed、1 skipped；0007 迁移、DATE/DECIMAL/JSON 与双连接竞争发布通过；只读账号权限测试缺专用投影库/账号配置而跳过 |
| 前端单元/组件 | npm test | 23 passed |
| 前端生产构建 | npm run build | 成功，2256 modules transformed |
| 前端浏览器契约 | npm run test:e2e，受控 API | 1 passed |
| 服务启动/健康 | 实际 uvicorn 子进程，临时 SQLite 升级 head，HTTP live/ready | 通过，ready 且 model_configured=false |
| 工具可信子进程 | 实际 app.task_runner 入口、持久队列与工件 | 通过，aggregate 实值 30，任务成功 |
| 迁移/回填 | 空库→0007；已有 0005→head；降级/再升级；dry-run/apply/replay | 隔离 SQLite 通过 |
| CSV/XLSX 核心流程 | 现有 API＋实际解析/计算/工件，受控模型输出 | 上传→Profile/版本→分析→旧表格/图表→历史通过 |
| 数值可信度 | 999999 非绑定总结、非法引用、总结失败、整数/浮点溢出 | 阻止错误成功；保留真实结果与合法缺失 |
| 原文件生命周期 | 解析失败留存、租约中断、显式删除与多版本清理 | 通过 |
| Git diff | diff --check；删除列表；前端/compose/迁移检查 | 无空白错误，无删除；前端业务与旧迁移未改，compose 原差异保留 |

后端全套的七个告警及真实 MySQL 单独测试的一个告警，均为已有 Alembic path_separator 弃用提示。没有引入全仓 lint/type-check 工程。

### 用户 A—E 验收

| 场景 | 证据 |
|---|---|
| A：通用 GroupBy 与重命名字段 | test_registry_generic_groupby_and_immutable_context：中文字段与 department/revenue 使用同一工具，合计 30 |
| B：相关性结构化返回 | test_ratios_sequences_and_pairwise_correlations：Pearson/Spearman、逐对样本数与系数；常量/样本不足原因及警告 |
| C：EDA 注册组合 | test_eda_composes_registered_tools：拦截 Registry.calculate，验证实际调用概况/质量/统计/相关性/建议；时间字段与类别频次也由注册工具处理 |
| D：清洗 V2、保留 V1 | test_internal_transform_keeps_original_and_is_idempotent；test_old_schema_queued_analysis_sql_and_history_survive_rename：V1 BIGINT/日期、SQL、排队分析和历史保持固定 |
| E：预览/完整工件 | test_large_preview_keeps_full_artifact：125 行只返回 100 行、真实总量与 truncated；工件仍有 125 行 |

## Performance Notes

每个执行按固定版本加载；已发布 Profile 复用，工作流按来源缓存 Context。派生表、矩阵、图表与工件受独立预算。整数滚动 sum 采用线性窗口累加，防止 float64 中转。整数 min/max/median 窗口仍按窗口计算，大窗口受阶段超时限制；本轮未做大规模性能压测，也未新增缓存平台。

## Security Notes

所有权位于基础设施服务；可信身份与权限不从请求参数获取。SQL additionally requires READ_DATABASE，只读账号与 AST 双重约束。清洗不在聊天 manifest 中，没有公共通用执行 API。新版图表 options 只有显式白名单。原始样例不进入模型上下文；保持 Phase 1 服务端事实取值、比例显示与舍入。错误与日志不输出连接信息或原始异常。

## Known Limitations

- 真实 MySQL 0007、类型及双连接竞争发布已在临时测试库通过；专用投影库的只读账号权限测试尚未执行，不能由 SQLite 测试或既有业务库状态代替。
- 本轮真实 DeepSeek 未调用。核心工作流使用受控模型输出；新工具发现与总结在真实模型下仍需验收。
- In-process Engine 能检查期限，不能强制抢占正在执行的 Pandas；生产任务必须走现有受监督子进程。
- 继续使用浮点统计和 Numeric(24,8) 投影约定；mean/quantile 等可能近似，整数 sum、min/max 与整数窗口 sum 保持精确并检查范围。
- ChartSpec 2.0 只供内部消费；前端继续渲染既有协议。单实例任务架构保持不变。
- 代码保留在现有工作区；本轮没有更新实际业务数据库、远程推送或部署。

## Decisions Made

- 在现有 feature checkout 实施，保留 Phase 1 与 compose 输入。代价：阶段差异与已有未提交工作同处一个工作区，完整清单须按来源区分。
- 旧版本类型兼容只读其自己的 Schema，不借用当前 DatasetColumns。代价：不支持的历史 dtype 会显式失败，避免解释成新类型。
- 历史未知工具的 Trace 允许留存，tool_version 标记 legacy，不注册伪能力。代价：此类历史 Trace 没有可执行的 Registry 元数据。

## Deferred to Phase 2.5

Kendall、正态检验、t 检验、卡方与 ANOVA；没有以 Available 注册。

## Deferred to Phase 3

复杂 Planner、多轮持久状态、SSE、取消/恢复等，需先确认下一阶段范围；本轮不实现。

## Deferred to Future

动态 Python、Sandbox、报告导出、缓存平台、机器学习与新基础设施。

## Phase 3 Readiness

Context/Registry/Engine、固定版本、结构化结果与执行记录已经提供扩展接口。进入下一阶段前建议补验专用投影库只读账号权限，并用真实模型验收只读 manifest/事实总结；再按审批范围推进 Phase 2.5 或 Phase 3。

部署到实际环境前，以现有迁移账号执行 `python -m alembic upgrade head`；如需旧数据回填，`python scripts/backfill_dataset_versions.py` 默认为 dry-run，显式 `--apply` 才写入。此记录不声称实际数据库已经升级。
