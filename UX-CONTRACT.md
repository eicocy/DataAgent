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
| Upload Queue | `frontend/src/components/UploadQueue.vue` + Dataset Store | 上传 API | sequential | 分文件失败/重试/取消与解析恢复 |

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
- Agent: 通过 `POST /analysis/runs` 提交任务，使用持久 SSE 事件更新状态，断线后回到任务查询和 Trace。发送后锁定输入并显示实际执行步骤；刷新恢复当前会话任务。仅在 sessionStorage 保留 session_id、可为空的 dataset_id、question、request_id、record_id，不保存结果或凭据；退出和会话过期清除。网络状态不明时复用 request_id，明确再次分析使用新 request_id。离开页面只停止监听；“取消任务”才向服务端发取消请求。必需步骤未完成时显示部分完成和真实结果。

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
