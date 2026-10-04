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

## Phase 2 — 2026-10-04

- 状态：已完成本阶段实现与验收，停止在 Phase 2，不进入 Phase 3。
- 用户已验收 Phase 1，并明确授权仅执行 Phase 2，完成后停止。基线 `7f1e0a5` / `V2.0.1`。
- Ruling: 继续使用现有 `codex/ai-native-workspace` 检出 — 用户已在此检出本地调试并要求继续升级，另建检出会脱离当前运行配置 — 保留本地 `backend/app/config.py` 和 `plan/`，不读取/展示凭据，不推进其他 Phase。
- 2.1 基础契约：版本化 Profile、保守语义候选/用户覆盖、Template Router、Plan 3.0、公共步骤去重、模型预算，已完成首批 RED→GREEN。
- 2.2 提交与恢复：所有输入固定授权版本、完整配置幂等、Session 语义修正 API、跨输入证据归属，已实现并通过针对性回归。
- 2.3 执行：沿用规范工具与结果校验；独立输入适配器；最多两个明确声明安全的只读计算并行；数据库与工件写入集中在主线程；DEEP 有界探索，已实现并通过针对性回归。
- 2.4 前端：沿用 Composer / Store / AgentSteps，开放深度与实际模型、增加多输入和字段语义修正，组件 RED→GREEN；不开放 Join、预测、自动报告或沙箱。
- 自检修复：语义 PATCH 锁定并刷新 Session，保留其他请求的映射；并行可靠性失败标为不可重试，独立节点继续。两项均观察到 RED→GREEN。
- 最终全后端回归：隔离临时 SQLite、文件目录和模型 Key 空值，516 passed / 5 skipped / 16 warnings，43.87 秒。跳过四项原有专用 MySQL 集成和一项未配置专库的新增 MySQL 迁移；警告均为已有 Alembic path_separator 提示。
- 额外真实 MySQL 验证：新建随机前缀 `datalens_test_phase2_` 隔离库，从 0009 升级至 0010；历史 Plan/Session/记录保留，Profile 两次初始化仍为 105。1 passed / 2 warnings，4.35 秒；完成后仅删除本次创建的测试库，此隔离测试未操作本地业务库。
- 最终前端 15 文件 / 56 测试通过；生产构建通过；3 个模拟 API 浏览器流程通过。新增流程覆盖模板/深度、多输入、字段修正、计划依赖及刷新；390px 关闭证据抽屉后输入/修正操作可用，等待导航动画结束再截图，桌面与窄屏图已检查。
- UI strict 审计 0 errors / 0 warnings，Git whitespace 检查通过；新增 `docs/phase2-workspace.md` 并同步索引与 UX 契约。
- 最终审查：第一次 Astra 调用立即因账号用量限制失败，没有产生审查；改用当前可用 Sol 完成同一次只读独立审查，不并行重复审查。无 Critical、五项 Important、无 Minor；五项全部进入一次修复，以下复现均 RED→GREEN，并运行最终全套回归。
- Final: fixed 完整数据根步骤误用筛选来源 — `test_dedup_never_reuses_filtered_source_for_a_dataset_root`；只登记真正无依赖的数据根，探索节点不去重。
- Final: fixed 去重丢失必需标记 — `test_dedup_preserves_required_completion_for_optional_first_duplicate`；保留 required 并取最高 priority。
- Final: fixed 重新规划无法保留探索来源 — `test_replanning_preserves_trusted_exploration_and_rejects_forged_provenance`；只允许服务器原计划已批准的来源，不接受模型伪造。
- Final: fixed 新 expected_outputs 未参与完成判定 — `test_replacement_expected_outputs_are_required_for_completion`；失败交付必须保持部分完成。
- Final: fixed 选择未绑定数据集后字段编辑器 403 — 前端 `binds a selected owned dataset` 回归；先串行保存授权附件，绑定失败保留原选择；后端所有权校验保留。
- 本阶段针对性后端测试现为 33 项；三种深度均验证了部分完成和真实计算+事实绑定的成功路径。历史 v1/v2 回归继续通过。
- 本地增量迁移：先保存 MySQL SQL 备份及旧表内容校验摘要，再执行 0009→0010。原有 15 张业务表逐表校验不变，两条历史分析记录保留。备份在忽略目录 `.superpowers/sdd/phase2/local-before-0010.sql`，不加入 Git。
- 本地服务：后端 8000、前端 3000 已重新启动；带本地测试会话令牌的实际代理 GET 验证 Profile 105、语义映射和 Phase 2 能力均返回 200。只读验收令牌未打印或持久化；未改用户凭据。浏览器打开本地项目登录页，正常登录由用户完成。
- 审查未判断的范围：用户本地配置/凭据保持原状；真实模型、业务库迁移和部署由单独验收记录说明，不把源代码审查当作运行证明。未进行正式部署、提交或新发行。
- 真实模型验收发现并修复：DATA_CLEANING 白名单遗漏规范只读 `dataset_overview` / `column_summary`，导致质量检查计划失败并消耗重试预算。新增复现测试 RED→GREEN；同步过滤 Planner 工具列表和旧契约测试，清洗写入仍禁用，不增加预算。
- 真实 DeepSeek 小样本验收：临时 SQLite 和独立文件目录，两行模拟 CSV，固定版本提交 FAST / general-quality；Plan 3.0、四项检查全部完成，事实绑定总结成功；15.5 秒、3 次模型调用、11,009 Token。数据为 2 行 / 2 列，缺失与重复均为 0，结论与计算一致。未使用用户上传文件；该样例不能代表所有模型输出和业务数据均已验收。
- 最终服务刷新：后端加载最新修改，8000 健康检查及前端 3000 均返回 200。验收证据保存在忽略目录 `.superpowers/sdd/phase2/`。本阶段未提交、打标签、推送或正式部署。

## Phase 3 — V2.0.3

用户批准按既有计划继续 Phase 3，基线 f8e8172/V2.0.2，分支 codex/phase3-v2.0.3。已实现文件来源/文档候选核对、质量评分、受限版本清洗/Join、Decimal 业务/周期/贡献、三折预测、Agent/Profile/语义和对应 Vue 入口。任务 1–6 已逐项实现与修复，Task 7 的隔离/本地运行验收通过。2026-10-05 整分支最终审查 Approved，全部发现已关闭，允许本地 V2.0.3 发行；本地提交与标签随后执行，尚不登记提交 ID。详见 [Phase 3 工作台](phase3-workspace.md) 与 [V2.0.3 验收](releases/v2.0.3.md)。

真实 MySQL 验收发现解析任务状态和上传优先会话身份缺陷，修复后 7 个监督任务全部成功；并发幂等、CAS、旧版本和两输入来源通过。另以已存储 Decimal 验证精确合计和结构性清洗精度；首次 CSV/旧投影精度限制仍保留。所有输入为模拟数据。

真实模型完成周期、贡献、预测及 overview，45.88 秒/3 次/27,039 Token；历史 PLAN_INVALID 与 30 秒阶段超时保留。成功样本旧摘要 MAPE 重复缩放已修复，使用相同真实工件重渲染证明正确，四个保存工件离线校验通过，未追加模型调用、未改写旧历史答案。最终隔离后端回归 824 passed / 12 skipped / 22 既有 Alembic warnings，59.84 秒，运行器耗时 65.52 秒、退出码 0。12 项跳过包括原 8 项环境门控测试和新增 4 项 MySQL 并发测试；后者另在真实隔离 MySQL 中 4 passed / 2.66 秒。814 与 823 次通过记录为历史检查点。

最终审查修复覆盖所有活动 Agent 输入的删除保护，包括固定版本的次要输入；受理与删除共用 User 行互斥和当前读，按发布锁顺序先检查活动 Job/右侧 ToolRecord，再锁 Dataset，仅排序读取所需固定版本，避免死锁与扫描完整版本历史。真实隔离 MySQL 四个用例覆盖旧 RR 事务的两种先后顺序及元数据发布锁序，针对性组合回归 125 passed / 4 skipped，18.94 秒；这是锁协议验证，不等同于真实 Worker 或多实例全流程验收。

本地业务库 0010→0011 已完成，SQL 备份保留；旧表计数、1 用户/1 数据集/2 记录、原投影/当前版本保持，登记 1 个旧文件来源。已确认的本地服务刷新后 API 2.0.3/readiness、四项认证 GET、Vue 3000/代理均通过；用户 30 秒模型配置/Origin 3000 保持。没有正式部署或远程发布。

前端最终 18 文件/77 单元测试通过，9.90 秒；构建通过，20.65 秒；6 个模拟 API 浏览器流程通过，15.5 秒；strict UI 审计 0 errors / 0 warnings。附件说明已与关联键 Join 能力一致。实际 Vue/隔离后端浏览器验证文档确认、质量、清洗、Join 与旧版本；原生历史详情复验真实保存结果，1 预测/2 业务面板正确，1440/390px 截图已查看、表格内滚动可用、无页面横向溢出或控制台错误。手动报告成为最新证据后遮蔽此前分析，以及报告任务摘要缺少完整 document 导致即时编辑器空白，单列为 Phase 4 已知限制；组件已有 document sections 回退，详情 API 的六段报告不受此摘要缺失影响。

## Phase 4/5

尚未实施。本轮停止于 Phase 3。

## V2.0.2 — Phase 2 发行收口

- 用户指定已完成 Phase 2 为 V2.0.2，并授权提交、依次推送 V2.0.0 / V2.0.1 / V2.0.2，随后明确要求合并到 main。
- 前端包、锁文件根包和后端 API 同步为 2.0.2；README、CHANGELOG 与 `docs/releases/v2.0.2.md` 同步本阶段真实范围，Phase 3—5 保持未实施。
- 发行前重新运行：后端隔离回归 516 passed / 5 skipped / 16 个已有 Alembic 警告，43.43 秒；前端 56 项单测通过，生产构建通过，3 项模拟 API 浏览器流程通过。没有重复调用付费模型，真实模型证据沿用本阶段单独验收记录。
- 发行检查：版本号一致、暂存 whitespace 检查通过；扫描待推送历史及索引共 456 个文件对象版本，未发现已配置模型 Key 或所检查凭据模式的匹配。该检查不等同于全面安全审计。
- 提交排除本地 `backend/app/config.py`、`plan/`、环境文件、上传数据、工件及数据库备份，保留其原始内容。只推送本次三个版本的相关引用，不推送其他本地分支。
- 合并策略：远程 main 为三个版本的共同祖先，使用快进合并保留现有提交历史；推送顺序为 V2.0.0 基线 `310e86b`、V2.0.1 `7f1e0a5`、V2.0.2 本次提交，各自保留标签。远程结果以推送后的 `git ls-remote` 核对为准。

## V2.0.1 — Phase 1 收口

- 版本号：前端包、锁文件根包和后端 API 同步为 2.0.1；发行标签 V2.0.1。
- 后续 UI 调整：统一文件/发送按钮；历史详情按分析、报告生成和导出区分展示，中文标题、状态、文件和时间分层，缺失耗时省略，结果卡片补齐留白；报告任务不再把内部操作标识作为分析问题重跑。
- 新增报告记录展示与导航、零耗时保留两项回归；前端现为 51 项测试，生产构建和 2 项模拟 API 浏览器流程通过。实际浏览器检查了用户已有的报告记录与首页、390px 窄屏；截图保存到忽略目录 `.superpowers/sdd/ui-polish/`。
- 发行前后端回归使用临时 SQLite、隔离文件目录和禁用真实模型的子进程配置：482 passed / 4 skipped / 14 warnings，37.82 秒；跳过专用 MySQL 集成，未触碰本地业务库。版本号一致性、Git whitespace 和 UI strict 检查通过。
- 本地调试已使用现有 MySQL 初始化两个空的项目数据库，迁移至 0009；API 存活、数据库就绪及前端代理检查通过。模型 Key 配置存在，此过程未调用真实模型；不等同于隔离 MySQL 集成、真实模型或部署验收。
- 本地 `.env`、凭据、上传数据不属于发行内容；原有 `plan/` 与本地模型配置改动保持原状，不纳入本次提交。
