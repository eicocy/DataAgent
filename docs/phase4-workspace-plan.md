# Phase 4 Artifact / Chart / Report Implementation Plan

> 执行：superpowers:executing-plans；用户已授权按 UPGRADE_PLAN 执行 Phase 4，完成后停止。

**Goal:** 在已有工作台、计算证据和导出服务上交付可恢复、可引用、长期留存的分析成果。

**Architecture:** ArtifactManager 统一 JSON/二进制授权、DTO、配额与留存，原存储保持职责。报告从固定输入和已验证结果构建不可变 document；自动交付直接调用底层报告服务，不提交子队列。工作区按 Session 恢复分析、报告、工件及选择。

**Tech Stack:** 现有 FastAPI/SQLAlchemy/Alembic/Pandas、ReportLab/python-docx/openpyxl、Vue Options API/Pinia/ECharts。

**Spec:** docs/UPGRADE_PLAN.md §§7–11 Phase 4。

## Global Constraints

- 仅 Phase 4；不实现沙箱、不增加执行任意 Python 的接口，不推进 Phase 5。
- 继续当前源码目录的独立功能分支；保护本地 config.py 原有配置和 plan/；不提交、推送、发布或部署。
- 最终成果及必要证据保存到用户删除；未引用中间成果七天；默认每用户 2 GiB 配额，不自动删除最终成果。
- 引用校验所有者、Session、类型、固定版本和可用性；预览不能作为计算输入。
- 原始明细来自固定 DatasetVersion；超出单文件限制分文件和清单，公式注入保持防护。
- 图表和结论消费计算结果；不造数、不把相关/贡献写成因果。

## Tasks

### Task 1: Artifact lifecycle and migration
- [x] 先新增留存/配额/过期/旧库迁移测试，观察失败。
- [x] models 与 0012 增加 session_id、retention_class、可空 expires_at、多输入报告快照；幂等回填，不恢复已清理内容。
- [x] manager 统一 DTO、授权、读取、依赖保护、配额；现有 JSON/报告/图表写入接入；维护只清理可过期中间成果。
- [x] 验证：pytest tests/test_upgrade_phase4_artifacts.py tests/test_upgrade_phase4_migration.py；PASS。

### Task 2: References, workspace and idempotent requests
- [x] 新增跨用户/Session/过期引用、过滤、刷新恢复、request_id 重放冲突测试，观察失败。
- [x] references.resolve_references(db,user_id,session_id,ids) 返回固定版本和完整来源；run 提交固定授权输入和引用快照。
- [x] 会话 workspace API 返回分页工件、报告与最近分析，PATCH 保存选择；再生成新 ID/来源关系；报告创建/导出可选稳定 request_id，兼容旧调用。
- [x] 验证：pytest tests/test_upgrade_phase4_api.py；PASS。

### Task 3: Report templates and complete exports
- [x] 新增模板差异、多输入、完整原始明细/分片、代码边界、多页中文/目录/证据测试，观察失败。
- [x] templates 支持自动/快速/详细/管理层/技术/质量/预测；builder 消费已计算事实，编辑文案标记为用户编辑。
- [x] Excel 提供 Summary/Raw Data/Cleaned Data/Data Quality/KPI/Analysis/Charts/Insights；多输入与原始版本标签、分片清单；Word/PDF 共用 document，封面/目录/页眉页脚/页码/重复表头/证据附录。
- [x] code_exporter 导出参数化固定计划 Python 和依赖说明，SQL 只含已验证 SELECT 与参数，不含凭据，不执行导出代码。
- [x] 验证：pytest tests/test_upgrade_phase4_reports.py tests/test_report_exporters.py；PASS。

### Task 4: Automatic delivery
- [x] 新增成功/部分失败/无子队列/同一来源测试，观察失败。
- [x] run 配置增加 report_template/output_formats；analysis 计算完成后直接 build/export，持久化交付事件与逐格式状态，交付失败保持 partial。
- [x] 保护计算成果和证据；不再次分析生成报告，不增加模型调用。
- [x] 验证：pytest tests/test_upgrade_phase4_delivery.py；PASS。

### Task 5: Workspace UI
- [x] 新增报告不遮蔽分析、会话竞态、恢复选择、引用、幂等重试和组件测试，观察失败。
- [x] ArtifactWorkspace/MentionPicker/workspace store 复用预览、报告编辑器和 ChartView；Composer 结构化引用与报告选项；文件库支持过滤；清晰展示 partial/expired/无数据状态。
- [x] 保持白/浅灰、既有字体/圆角/颜色；原工作区布局与窄屏抽屉；键盘与 IME 保护。
- [x] 验证：npm test；npm run build；Phase 4 浏览器流程。

### Task 6: Acceptance and documentation
- [x] 后端全套、前端全套/构建/相关浏览器流程、SQLite 空库及旧库迁移、隔离 MySQL（环境可用时）、真实 PDF/DOCX/XLSX 生成/读取/渲染。
- [x] 自检并修复实质问题；独立审查启动时因账号用量限制失败，已如实记录；更新 UPGRADE_PROGRESS、索引、能力/UX 文档和 Phase 4 证据。
- [x] 如实记录受限/未验证项；完成 Phase 4 后停止。

## Review Focus

引用来自已清理文件、同 Session 不同输入版本、多输入 Join 结果来源、创建或导出中断后重试、切换 Session 时迟到请求，均需明确状态/拒绝错误来源/保护旧版本。

## Pre-flight

Task 1 DTO/留存被 2/3/4/5 消费；Task 2 引用快照被 4 使用；Task 3 ReportDocument 被 4/5 复用。保持原 report API 与旧模板名兼容。旧 docs/phase4-implementation.md 是 v2.0.0 历史能力，本计划是 UPGRADE_PLAN 的增量 Phase 4。
