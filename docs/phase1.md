# Phase 1：可信度修复与数据版本基础

复用现有 Planner、Executor、DatasetService、DatasetTools、ArtifactStore 和后台任务。本阶段不新增分析工具、清洗、多轮状态、SSE、取消恢复、报告导出或动态 Python；前端业务代码保持兼容。

## 结果与解释

工具在序列化、成功缓存和工件持久化前验证结果。无限值、计算溢出和超过 signed BIGINT 范围的整数合计失败，失败步骤不可供下游引用。合法缺失、无有效样本合计和样本不足的统计空值保留 null，并附结构化 ToolResult.warnings。SQL 读取保留 nullable integer，避免 NULL 造成大整数浮点舍入。

总结协议为 template、facts、evidence_refs。事实包含 key、成功 step_id、path、format(number/percent/text) 及可选 decimals。服务端只解析字典键和数组下标，不执行表达式；真实值由服务端填入，Decimal 负责百分比和四舍五入。含数字的标签、日期通过 text 引用填入；模板未绑定数字（含中文及 Unicode 数词）拒绝。事实引用保存于 report.findings，现有 answer/tables/charts/warnings 保持兼容；旧历史自由文本不重写。

原始 preview/filter/sort/非聚合 SQL 行和 sample_values 默认不进入报告、修复和重规划上下文。SQL 聚合指标及明确 GROUP BY 标签保留；完整计算与工件不裁剪。完整 Profile 和模型可见的无原始样例摘要分别构建。数值引用验证不验证模型解释中的因果关系或指标选择；总结失败保留真实结果并返回 partial。

## 版本与生命周期

0006_dataset_versions 追加 dataset_versions 及可空版本引用，不修改 0001—0005。成功解析发布初始版本，保存 Schema、Profile、来源、投影、变换记录、原文件状态和 SHA-256。分析提交固定版本，执行校验 Dataset 归属、状态和投影位置，模型元数据也使用固定版本。

本阶段只有初始版本；后续多版本写入需要另行实现投影隔离。尚未回填的旧数据继续读取现有投影。旧历史关联标记 legacy_association，不声称当时已存在版本快照。

解析记录 CSV 编码和数值推断、字段规范化、日期转换、工作表选择、空行处理。解析失败或任务中断保留已接受原文件，显式删除清理。发布和失败写入前检查租约，失效 worker 不更新 current_version。行列限制读取 Settings，默认 100000/200 且须为正。readiness 比较实际修订与当前 Alembic heads。

## 升级与回填

在 backend 目录、配置好迁移账号后执行：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe scripts/backfill_dataset_versions.py --batch-size 100
# 默认 dry-run，显式 apply 才写入：
.\.venv\Scripts\python.exe scripts/backfill_dataset_versions.py --batch-size 100 --apply
```

回填读取既有投影和列类型，不重新解析或覆盖原文件，不删除或覆盖源表。按 ID 分批，每个 Dataset 独立事务；已有版本跳过，失败回滚并打印安全错误码、返回非零退出码，修复后重复执行可重试。原文件缺失仍可建立兼容版本，original_available=false。

## 验证与限制（2026-10-02）

完整后端 pytest、前端测试及生产构建已执行。隔离 SQLite 覆盖空库迁移、已有 0005 数据升级、降级再升级、重复回填、缺原文件、类型保持、版本归属和固定、留存与租约失效。CSV/XLSX API 集成覆盖上传→解析→Profile/版本→工具计算→表格/图表工件→历史回看。

最终后端结果：122 passed、3 skipped、6 warnings（Alembic 既有弃用提示）；前端 Vitest：23 passed；Vite 生产构建成功。git diff --check 通过。0001—0005 和前端业务代码无差异，无文件删除。

核心流程使用受控模型替身，真实 DeepSeek 新总结协议未验收。环境未提供专用 TEST_MYSQL_URL 等配置，三个真实 MySQL 测试跳过；不能据此声称 MySQL 0006 部署通过。已有 Alembic path_separator 弃用提示仍存在。compose.yaml 用户已有改动保留。

## 文件清单

修改文件（16）：

- backend/app/agent/executor.py
- backend/app/agent/prompts.py
- backend/app/config.py
- backend/app/main.py
- backend/app/models.py
- backend/app/routers/datasets.py
- backend/app/services/analysis.py
- backend/app/services/analysis_agent.py
- backend/app/services/analysis_tools.py
- backend/app/services/datasets.py
- backend/app/services/jobs.py
- backend/app/tools/schemas.py
- backend/tests/integration/test_mysql.py
- backend/tests/test_datasets_api.py
- backend/tests/test_planner.py
- docs/architecture.md

新增文件（14）：

- backend/app/execution/__init__.py
- backend/app/execution/validators.py
- backend/app/execution/evidence.py
- backend/app/datasets/__init__.py
- backend/app/datasets/schemas.py
- backend/app/datasets/profiler.py
- backend/app/datasets/versions.py
- backend/migrations/versions/0006_dataset_versions.py
- backend/scripts/backfill_dataset_versions.py
- backend/tests/test_result_validation.py
- backend/tests/test_evidence.py
- backend/tests/test_dataset_foundation.py
- backend/tests/test_phase1_integration.py
- docs/phase1.md

删除文件：无。compose.yaml 不属于本阶段修改清单；其既有差异保留。
