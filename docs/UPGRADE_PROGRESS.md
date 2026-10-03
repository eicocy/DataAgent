# SDD ledger — plan: docs/UPGRADE_PLAN.md

基线 310e86b；分支 codex/ai-native-workspace；用户批准五阶段渐进实施。

Ruling: 在用户确认的 v2 根目录使用独立功能分支 — 当前检出 detached HEAD，旧 Phase 4 worktree 属于其他工作，当前 app 空目录不能创建该仓库原生 worktree — 成本是当前目录可见实施改动，保护 plan/，不触碰旧工作树。

Ruling: 原计划按五次独立交付分阶段执行，先完成 Phase 1 验收再推进 — 用户禁止一次性重写全部功能 — 后续阶段的能力不会提前声明可用。

Pre-flight: Composer 上传复用 Dataset API/Store；附件存 Session JSON，需要 ConversationContext 显式字段避免解析后丢失；模板目录先只读，不作为 Phase 1 固定 Workflow；图表规范与旧系列通过同一前端适配器兼容。

## Phase 1

- 状态：已完成本阶段实现与本机验收，后续阶段尚未实施。
- 本机安装项目锁定依赖到 .venv 与 frontend/node_modules，不修改全局环境。
- 已交付：极简 / 首页；旧概览保留 /overview；/templates；PromptComposer；逐文件 UploadQueue；延迟创建 Session；授权附件绑定/恢复/删除；能力目录；完整已有图表类型；PATCH 跨域；异步请求失效修复。
- 目录覆盖 15 方向 / 105 模板。available/limited/planned 反映真实工具条件；未开放 Profile 执行、深度选择、多数据集执行、模型切换、自动报告、文档解析和沙箱。
- 数据库无迁移，源码 head 保持 0009；附件复用 context_json，旧 dataset_id 与 run/chat 契约保留。
- 后端：`cd backend; ../.venv/Scripts/python.exe -m pytest -o addopts= -q` → 482 passed / 4 skipped / 14 warnings，38.02 秒。4 个真实 MySQL 测试因未提供隔离环境跳过；警告为现有 Alembic path_separator 配置弃用提示。
- 前端：`npm test` → 13 文件 / 49 测试通过；`npm run build` 通过；`npm run test:e2e` → 2 流程通过，API 为受控替身，非真实模型/数据库验收。
- 浏览器：注册—独立上传—预览—分析—刷新—历史；首页无空 Session；模板填入可修改问题；多文件部分失败/重试；附件绑定/刷新/删除；390px 无横向溢出；规划模板禁用。实际检查桌面/手机截图。
- UI 静态审计 strict：0 errors / 0 warnings；`git diff --check` 通过。截图和审计 JSON 位于忽略的 `.superpowers/sdd/upgrade-plan/`。

### 一次独立代码审查与修复

- Final: fixed 上传时切换会话后 busy 残留 — workspace replacement 回归 RED→GREEN；先停止旧队列并重置状态。
- Final: fixed 已受理解析网络失败后重复 POST — accepted polling failure 回归 RED→GREEN；保留 ID，仅明确解析失败/记录不存在才重新上传。
- Final: fixed 附件添加/删除覆盖竞争 — deferred add/remove 回归 RED→GREEN；所有附件修改同链序列化，提交等待全部绑定结束。
- Final: fixed 缺失相关系数伪装数字 — canonical heatmap null cell 回归 RED→GREEN；缺失保持缺失，合法零值保留。
- Final: Ruling: 将恢复后附件无删除入口提升为必须修复 — 用户明确要求附件删除，十个附件上限使缺失入口阻断正常使用 — 增加恢复附件删除与容量回归，均 RED→GREEN，最终前端 49/49。
- Ruling: 审计扫描正式 frontend/src — 历史静态原型不是当前交付，原配置只扫原型会漏实际 Vue — premium-ui.json 同步真实入口。
- Final review: no Critical; 四项 Important 全修复，无保留未修复发现。后续 Profile/预测/沙箱等超出 Phase 1 项按能力声明禁用；真实 MySQL/Docker/模型仍待对应阶段验收。

### 留存与限制

- 所有改动在 `codex/ai-native-workspace`，用户 `plan/` 与旧工作树未改。
- Ruling: 保留本地功能分支交付 — 用户批准本地渐进实施，未要求合并、推送或发布 — 不改变其他分支或部署。
- 未连接运行 MySQL，未执行线上迁移、Docker 部署或付费模型；现有七天工件策略本阶段沿用，Phase 4 再迁移。
- 浏览器默认系统 Select 弹层；新 Composer 不定制其系统外观。

## Phase 2—5

待依次实施，范围、文件、验收与风险见计划。

## V2.0.1 — Phase 1 收口

- 版本号：前端包、锁文件根包和后端 API 同步为 2.0.1；发行标签 V2.0.1。
- 后续 UI 调整：统一文件/发送按钮；历史详情按分析、报告生成和导出区分展示，中文标题、状态、文件和时间分层，缺失耗时省略，结果卡片补齐留白；报告任务不再把内部操作标识作为分析问题重跑。
- 新增报告记录展示与导航、零耗时保留两项回归；前端现为 51 项测试，生产构建和 2 项模拟 API 浏览器流程通过。实际浏览器检查了用户已有的报告记录与首页、390px 窄屏；截图保存到忽略目录 `.superpowers/sdd/ui-polish/`。
- 发行前后端回归使用临时 SQLite、隔离文件目录和禁用真实模型的子进程配置：482 passed / 4 skipped / 14 warnings，37.82 秒；跳过专用 MySQL 集成，未触碰本地业务库。版本号一致性、Git whitespace 和 UI strict 检查通过。
- 本地调试已使用现有 MySQL 初始化两个空的项目数据库，迁移至 0009；API 存活、数据库就绪及前端代理检查通过。模型 Key 配置存在，此过程未调用真实模型；不等同于隔离 MySQL 集成、真实模型或部署验收。
- 本地 `.env`、凭据、上传数据不属于发行内容；原有 `plan/` 与本地模型配置改动保持原状，不纳入本次提交。
