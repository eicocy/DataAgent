# UX Contract

## Product context

- Audience: 数据分析初学者、学生、运营、销售和小型企业工作人员。
- Primary jobs: 上传数据、理解字段、自然语言分析、验证计算证据、回看历史。
- Target market(s): 中文教学与求职展示场景。
- Active locales: `zh-CN`。
- Language/content register: 简洁、直接、解释下一步；Tool/字段标识保留英文。
- Timezone/calendar policy: `Asia/Shanghai`，公历，ISO 8601 接口时间。
- Accessibility target: WCAG 2.2 AA。

## Business-context sources

| 范围 | 权威来源 | 类型 | 复核日期 |
|---|---|---|---|
| 产品范围与用户场景 | `docs/superpowers/specs/2026-09-20-intelligent-data-analysis-assistant-design.md` | 已确认规格 | 2026-09-20 |
| AI Workspace 升级范围 | `docs/UPGRADE_PLAN.md`、`docs/UPGRADE_PROGRESS.md` | 已批准计划与实际交付 | 2026-10-03 |
| 数据与 Agent 安全 | `后端初始工程/04-Agent架构设计.md`、`08-SQL查询安全设计.md` | 架构/安全设计 | 交付时复核 |
| 数据生命周期 | `数据库/05-数据生命周期设计.md` | 数据设计 | 交付时复核 |
| 删除与权限 | `后端初始工程/09-认证与数据权限设计.md` | 权限设计 | 交付时复核 |
| 付费与法律 | 不在首期范围 | 排除项 | 2026-09-20 |

## Visual contract

- Project `DESIGN.md`: `DESIGN.md`。
- Token ownership: `DESIGN.md` 定义，正式应用由 `frontend/src/styles/tokens.css` 映射，静态原型由 `产品原型/assets/css/tokens.css` 映射。
- Supported themes: 首期浅色主题；高对比模式遵循系统色。
- Design-context owner: 后续前端负责人修改全局 Token 时同步维护两处。

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
|---|---|---|---|---|
| Table | `.data-table` | 本合同 + DESIGN.md | comfortable | HTML 语义与窄屏检查 |
| Select/Listbox | 现有数据选择复用 Element Plus；Composer/工作表/模板筛选 native select | 前端设计 | native / authored | Composer 接受系统弹层外观，真实浏览器检查键盘与窄屏 |
| Form | `.field` + 产品校验区 | 本合同 | auth / upload | 标签、错误和焦点检查 |
| Scrollbar | `base.css` 全局基线 | DESIGN.md | stable gutter | 浏览器检查 |
| Toast | `#toast-region` | 本合同 | success / warning / error | live region |
| Dialog | `[data-dialog]` | 本合同 | confirm / info | Escape 与焦点恢复 |
| CRUD | 页面与 API 映射 | 接口设计 | return / stay | 完整流程检查 |
| Prompt Composer | `frontend/src/components/PromptComposer.vue` | 已批准升级计划 | landing / conversation | IME、附件、选项能力声明、重复发送 |
| Button | Element Plus `ElButton`，Composer 复用同一组件 | DESIGN.md | primary / neutral / text | native-type、禁用、busy、键盘焦点与尺寸 |
| Upload Queue | `frontend/src/components/UploadQueue.vue` + Dataset Store | 上传 API | sequential | 分文件失败/重试/取消与解析恢复 |
| Semantic Mapping | `frontend/src/components/SemanticMappingEditor.vue` | Session 映射 API | native input/select + ElButton | 请求失效、保留错误输入、保存与刷新恢复 |
| Analysis Input Selection | AnalysisWorkspaceView 会话附件 | 已授权附件/固定版本 | checkbox | 选择、去除、提交版本绑定与刷新 |

## Component behavior

| Component | Default | Hover | Focus | Disabled | Busy | Error |
|---|---|---|---|---|---|---|
| Button | 明确动词 | 加深底色 | 3px focus ring | 降低对比且不响应 | 尺寸不变、显示进度 | 保留重试入口 |
| Input | 标签+帮助 | 边框加深 | brand ring | 显示原因 | 保留值 | 文本说明并关联字段 |
| Search | 内置清除按钮 | 同输入 | 焦点回输入 | 无 | 预留状态位 | 保留查询词 |
| Table | 表头+总数 | 行轻底色 | 行内操作可见 | 操作禁用 | 容器稳定 | 表内错误区 |

## Dataset navigation

- Admin tables: 服务端分页，默认每页 10 条，候选 10/20/50。
- URL state: 搜索、筛选、排序、页码和 page_size 进入查询参数。
- Empty/no-results/error/loading: 使用不同文案和动作，表格容器高度稳定。
- Back restoration: 返回列表恢复查询参数与滚动位置。
- Selection: 首期无跨页批量选择；删除为单条确认。

## Flow ledger

| Operation | Trigger | Pending | Success destination | Success feedback | Failure recovery | Focus outcome |
|---|---|---|---|---|---|---|
| 上传 | 上传数据 | 进度与阶段 | 数据集详情 | 上传并解析完成 | 保留文件、重试/重选 | 详情标题 |
| 分析 | 发送问题 | Evidence Rail | 留在工作台 | 展示结果并保存记录 | 保留问题与已完成步骤 | 重试或输入框 |
| 删除 | 删除 | Dialog 内忙碌 | 所属列表 | 已删除提示 | Dialog 内错误、重试 | 下一行或列表标题 |
| 搜索 | 搜索框 | 表内加载 | 同路由查询参数 | 结果数量 | 清除/重试 | 搜索框或结果标题 |
| 再次分析 | 再次分析 | 页面导航 | 工作台 | 带入原问题 | 返回详情 | 问题输入框 |

历史详情按实际任务区分“数据分析”“报告生成”“报告导出”。报告操作标识仅供内部使用，页面展示用户可读标题和状态；未记录耗时时省略耗时。报告任务提供返回所属会话入口，不将内部操作字符串重新提交为分析问题，也不展示空的分析工具区。总结区域保留服务器真实结果，分别标为“分析结论”或报告操作结果。

## Navigation and responsive behavior

- Document title: `{页面} — DataLens Agent`。
- 403: 说明权限边界并返回 Dashboard；404: 说明资源不存在。
- Sidebar: 桌面固定，窄屏转抽屉；当前页面有 `aria-current="page"`。
- Tables: 保持表格语义并水平滚动，不静默隐藏字段。
- Focus: 路由后聚焦主标题；Dialog 关闭后回到触发按钮。

## Overlays and feedback

- Dialog: 应用内 Dialog，不使用浏览器 alert/confirm/prompt。
- Delete: 数据集与历史记录按首期设计为不可恢复删除，明确后果并使用 danger 确认。
- Toast: 右上角，成功 4 秒；错误保持到关闭；最多 3 条。
- Layer order: dropdown 200、popover 300、backdrop 500、dialog 600、drawer 700、toast 900。

## Async and resilience

- Mutation default: 悲观更新，服务器确认后再宣告成功。
- Duplicate-submit: 按钮 busy 并阻止重复触发。
- Retry: 查询可重试；删除超时先刷新状态再允许再次提交。
- Session expiry: 保存非敏感输入，重新登录后回原任务。
- Stale requests: 搜索和列表请求取消或通过 request_id 忽略旧响应。
- Agent: 通过 `POST /analysis/runs` 提交任务，使用持久 SSE 事件更新状态，断线后回到任务查询和 Trace。发送后锁定输入并显示实际执行步骤；刷新恢复当前会话任务。在 sessionStorage 保留 session_id、可为空的 dataset_id、question、request_id、record_id 和公开分析选项（深度、模板、模型 ID、输入绑定），不保存结果或凭据；退出和会话过期清除。网络状态不明时复用完整配置和 request_id，明确再次分析使用新 request_id。离开页面只停止监听；“取消任务”才向服务端发取消请求。必需步骤未完成时显示部分完成和真实结果。

## Validation

- 所有产品表单使用 `novalidate`，应用负责错误文案。
- 首次提交后再对错误字段进行 change/blur 校验。
- 错误使用 `aria-invalid` 和 `aria-describedby`；长表单聚焦首个错误。
- 密码默认遮罩、允许粘贴和密码管理器。

## Permission

- 不相关功能隐藏；可见但无权操作的功能禁用并解释；直接访问返回 403。
- 前端显示不能代替后端基于 user_id 的所有权校验。

## Verification

- 静态检查：断链、无网络依赖、无原生对话框、表单标签、页面 title、Token 映射。
- 浏览器矩阵：1440、1280、1024 和窄屏；成功、加载、空、失败、无权限；键盘与 reduced motion。
- 原型不承诺真实 API、数据持久化或 Agent 运行能力。

## 2026-10-02 正式应用能力所有权

- 会话过期：auth store `expireSession()`，在路由跳转前清除用户、数据集和分析状态。
- 任务提交与恢复：analysis store；工作台负责轮询清理和消息展示。
- 步骤证据：AgentSteps；表格、分页、警告与历史兼容：AnalysisResult。
- 图表：ChartView / chartOption；缺失值保持缺失，多系列分类对齐，PNG 导出。
- 数值和结论来自服务端，浏览器状态不替代服务端授权与完成判定。

## 2026-10-03 Agent 编排适配

- 会话允许无数据集开始；工作台选择的数据集随下一次分析请求提交，服务端固定该条记录的版本。切换后旧结果继续按原版本展示。
- 数据集歧义以 `waiting` 和候选数据集返回；用户选择并重新发送原问题。工作台不自行猜测数据集。
- 任务状态以服务端记录为准。SSE 使用浏览器自动重连的事件 ID；连接失败回到现有状态查询。刷新或路由离开不取消任务。
- 用户明确点击“取消任务”调用取消接口。取消后已完成的工件仍可查阅，未执行步骤显示已取消。


## 2026-10-04 Phase 3 文档和固定版本工作台

- API 来源：files router + transformations router；候选表内容和预览摘要由服务器维护。DocumentCandidatePreview 为文件页/会话共用确认入口，展示原文位置、可能表头、完整行数与最多20行样例，人工核对后才能创建数据集。未确认文档不进入 Agent 的数据集输入。
- 文档上传沿用 UploadQueue + Dataset store，已受理 file ID 在重试中继续查询，不重复上传。会话文件由 GET files(session_id) 恢复；原始文件列表每页20个 UploadedFile，同一源文件只显示一次。文档格式来自 document_formats，表格格式来自 file_formats。
- “收起附件预览”仅关闭当前界面，不解绑或删除文件。现有 SessionPatch 没有文档解绑接口；刷新后可重新打开会话文件。此限制由当前 Task 6 控制器明确决定，不伪造永久移除行为。
- DatasetDetailView 的版本选择绑定 GET versions 与带 dataset_version_id 的 preview；发布成功刷新版本列表但保留旧版本选择。DataQualityWorkbench 显示 quality-score-v1 的规则、完整问题数量、有限样例及建议；它是描述性评分，不是行业标准。
- CleaningWorkbench/JoinWorkbench 共用 transformationFlow 的预览失效、幂等提交与任务状态查询。编辑配置使预览失效。确认使用现有 ElMessageBox，中文“保存为新版本 / 返回核对”；保留原版本，网络重试保留 request_id，路由离开停止轮询，409显示版本冲突。
- 这些表单使用 native input/select（接受系统弹层外观），有标签和可见焦点；读表沿用 .data-table 和内部横向滚动；操作按钮沿用 ElButton。不引入新导航、全局配色或 UI 库。
- 结构化结果所有权：AnalysisResult 分派到 ForecastResult/BusinessResult/DataQualityWorkbench；ChartView 仍拥有 ECharts。业务数值保留 Decimal 字符串，百分比仅移动十进制字符位置；空值展示服务端原因。预测展示基准/所选模型误差、MAPE覆盖、三次回测、实际预测点和经验上下界，明确“经验误差范围，未经校准”。
- 验证证据：frontend/tests/upgrade-phase3.test.js、frontend/tests/e2e/phase3-workspace.spec.js。静态审计不替代真实 MySQL/模型/浏览器验收；真实后端由父控制器顺序验收。

### Task 6 review round 1: 真实 DTO 与预览边界

- AnalysisResult 只在存在完整类型化字段时进入 ForecastResult/BusinessResult/DataQualityWorkbench；仅有 kind/columns/rows 的 normalized report table 不构成完整证据。成功 call 记录只有摘要和来源，不读取不存在的 call.result。
- 当前 raw tool_result 使用明确 artifact/已知步骤来源，或计划最终成功计算的 result_ref 与完整载荷匹配关联结果表；没有计划时仅采用唯一完整载荷匹配，不按并行 call 完成顺序或 kind 猜测。来源歧义时保留结果；dataset/primary 是输入上下文，不能作为步骤身份。旧 normalized-only 表仅在单一成功计算来源且逐值投影相符时关联；同一来源只展示一次，其他来源的表格保留。缺少完整 typed 数据时明确显示“当前仅提供结果表，完整计算信息未提供”，只展示实际表行及已提供单位/区间/限制；表行数不当作数据集行数，空结果表不当作空数据或无质量问题。
- Join 使用最多10行显式左右键对，每行逐一配对并在预览前显示映射；提交顺序由键对行顺序决定，与源 Schema/下拉选项顺序无关。重复键/未选完整键对禁止预览。
- DatasetDetail 保存 loadedPreviewVersion；版本切换马上隐藏上一版行，加载或失败时不借用旧行；成功且响应版本仍被选中时才展示，失败保留选择并提供版本预览重试。
- kind quality 单项检查与 quality_score 评分结果分开。旧结果显示实际 count/rate/status/lower/upper/row_refs，不虚构 issue/severity/suggestion/score；只有 quality_score.status=empty 才标为空数据评分未定义。
- 覆盖：frontend/tests/upgrade-phase3-review.test.js、frontend/tests/e2e/phase3-workspace.spec.js 的真实 normalized-only 与 raw+normalized fixture、反序复合键、慢/失败/过期版本响应和 legacy quality 分支。

- 预测 MAPE 列明确标注 (%)，直接展示后端百分数值，不再次乘以 100。
