# analysis

## Files

backend/app/analysis/{context,models,inputs,errors,registry,catalog,engine}.py
role: DatasetContext、Protocol、类型化输入结果、显式注册、权限校验与确定性 Engine
depends: Pandas、NumPy、Pydantic、datasets schemas/profiler、execution validators；不依赖 FastAPI/Vue/LangChain

backend/app/analysis/{operations,data_tools,aggregation_tools,statistics_tools,quality_tools,cleaning_tools,eda,chart_tools}.py
role: 共享计算、规范工具目录、注册工具组合 EDA、规则图表推荐与 ChartSpec 2.0；Phase 3 工具路径见下方
depends: Context、typed models、Registry；清洗内部显式授权

backend/app/analysis/{legacy_inputs,legacy_adapters,legacy_calculations,sql_safety,serialization}.py
role: 11 个旧参数/结果兼容 Adapter；共享聚合与过滤；只读 SQL 基础设施边界
depends: 旧 ChartSpec 1.0、SQLGlot、授权只读连接；不注册未实现能力

backend/app/services/tool_execution.py
role: 内部工具提交/幂等/授权、固定版本、工具任务、工件读取、原子版本发布与暂存补偿
symbols: ToolExecutionService、context_for
depends: AnalysisEngine、DatasetService、ArtifactStore、BackgroundJob、CleanupTask；无公开通用路由

backend/app/agent/{schemas,prompts,model_adapter,planner,executor}.py
role: AgentState、ExecutionPlan、报告；模型边界、计划校验、依赖执行与完成判定
depends: tools、services/datasets.py、LangChain

backend/app/tools/{schemas,registry,pandas_tools,sql_tool,chart_tool}.py
role: 工具协议与白名单；确定性 Pandas、受限 SQL、ChartSpec
depends: Pydantic、DatasetService、SQLGlot

backend/app/services/analysis_agent.py；analysis_tools.py
role: 原有导入和调用契约兼容入口
depends: agent、tools

backend/app/services/analysis.py
role: 提交幂等、授权/并发互斥、逐步持久化与旧投影定位
symbols: submit_analysis、execute_record、select_projection_bind
depends: models、ArtifactStore、DatasetTools、resource_lock

backend/app/services/jobs.py；backend/app/task_runner.py
role: 持久队列、租约、期限监督、过期终结、清理与孤儿进程退出
symbols: TaskSupervisor、claim_job、terminate_job、recover_expired_jobs、watch_owner
depends: BackgroundJob、SessionLocal、固定模块子进程

backend/app/routers/analysis_runs.py；charts.py；backend/app/services/artifacts.py
role: 响应Schema、授权任务/Trace/分页/图表与带类型JSON工件
symbols: RunData、TraceData、ResultPage、owned_record、owned_artifact、ArtifactStore
depends: current_user、AnalysisRecord、AnalysisArtifact

## Flow

分析请求 -> 授权/幂等记录与固定版本 -> 后台任务 -> Planner -> Executor -> DatasetContext/Registry/Engine -> 类型化结果验证 -> 完整工件/ToolExecutionRecord/Trace -> 事实渲染 -> 历史

内部清洗提交 -> 独立工作数据 -> 暂存投影与补偿引用 -> Dataset 锁/租约/source_version CAS -> 新版本与当前列元数据；旧版本保留。

## Related

backend/app/profiles/{schemas,catalog,service}.py、catalog.json；routers/{profiles,workspace}.py：版本化领域策略目录、持久化与真实能力声明，策略参与 Planner 上下文，不作为固定 Workflow。

backend/app/semantic/{detectors,mappings}.py；routers/sessions.py：保守业务语义候选、按版本隔离的用户修正；Session JSON 保存映射与授权附件。

backend/app/agent/{template_router,task_graph,graph_executor,budget}.py；services/{run_configuration,input_workspace}.py：多输入固定版本、完整配置幂等、Plan 3.0 校验、只读工具有限并行、DEEP 有界探索、模型与执行预算；兼容旧协议。

docs/phase2-workspace.md；migrations/versions/0010_analysis_profiles.py：新版 Workspace Phase 2，区别于旧版工具阶段。

analysis/{business_tools,forecast_tools,join_tools,quality_tools}.py、semantic/business_validation.py：新版 Phase 3 的 Decimal KPI/周期/贡献、三折预测、关系校验 Join、公开质量分；graph_executor/plan_validator 维护输入来源/语义/并行预算，execution/evidence.py 区分比例与百分数事实。

docs/phase3-workspace.md：Phase 3 契约和精度/预测/提取限制；Artifact 升级与 Python 沙箱待 Phase 4/5。

docs/tool-development.md；docs/analysis-capabilities.md；docs/phase2.md；backend/migrations/versions/0007_analysis_engine.py

backend/app/routers/analysis.py；backend/app/routers/analysis_runs.py；backend/app/services/jobs.py；backend/app/services/artifacts.py；backend/app/task_runner.py；backend/tests/test_planner.py
