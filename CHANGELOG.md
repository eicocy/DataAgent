# Changelog

## [2.0.2] - 2026-10-04

- 新增版本化 AnalysisProfile、Template Router、字段语义候选及会话修正。
- 扩展 Plan 3.0：授权多输入固定版本、公共步骤去重、严格 DAG 校验、有限并行和 DEEP 有界探索。
- 增加服务端节点、时间、模型调用和 Token 预算；复用旧计算、结果校验、失败恢复和证据持久化。
- Composer 开放模板、深度、实际模型及多输入选择；执行详情和完整分析选项支持刷新恢复。
- 新增 `0010_analysis_profiles` 增量迁移；兼容旧请求及 Plan 1.0/2.0。
- 修复公共步骤去重、探索重新规划、必需结果判定、字段修正附件绑定和质量检查工具白名单。
- 前后端版本号同步为 2.0.2；本轮停止于新版 Phase 2，Phase 3—5 未实施；实际验证与限制见 [发行说明](docs/releases/v2.0.2.md)、`docs/phase2-workspace.md` 和进度记录。

## [2.0.1] - 2026-10-03

- 完成 AI-Native Workspace 升级 Phase 1：极简分析首页、统一 PromptComposer、多文件上传队列、会话附件恢复/删除及只读模板中心。
- 能力目录区分可用、受限和规划中；保留原有 Agent、工具、数据管理和报告接口。
- 补齐已有图表类型适配、PATCH 跨域及上传/附件异步状态恢复。
- 文件与发送按钮统一使用 Element Plus；优化历史详情标题、元数据、状态及结果卡片，报告任务返回所属会话。
- 前后端版本号同步为 2.0.1；数据库迁移头保持 0009，不新增升级迁移。
- 本轮新版 Phase 2—5 尚未实施；验收边界见 [发行说明](docs/releases/v2.0.1.md)。

## [2.0.0] - 开发中

- 新增 ChatGPT 式分析工作台布局、会话侧栏、文件与工件库。
- 扩展 Excel、TSV、JSON Lines、Parquet 上传和工作表选择。
- 增加多格式报告文档、版本化报告、PDF/DOCX/XLSX/HTML/Markdown/CSV/JSON 导出。
- 增加 300 DPI 图表渲染与 SVG、PNG、缩略图工件。
- 新增 Alembic `0009_workspace_reports`。
- 外部 MySQL、模型、真实浏览器和 Linux 字体验收仍待完成；当前不代表正式发行。

## [1.0.0]

See [v1.0.0 release notes](docs/releases/v1.0.0.md).
