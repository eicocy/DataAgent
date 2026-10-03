# Intelligent Data Analysis Assistant Design Deliverables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付一套可直接指导后续开发的中文设计文档，以及覆盖全部用户功能模块、可通过本地浏览器查看的多页面静态 HTML 高保真原型。

**Architecture:** 设计资料按项目总览、产品原型、前端、后端、数据库和项目接口六个边界组织。HTML 原型采用无构建工具的共享 CSS/JavaScript 资产与多页面结构，通过统一入口导航；Markdown 文档以同一套术语、示例销售数据和标识符串联页面、API、数据表、Agent 与 Tool。

**Tech Stack:** Markdown、Mermaid、HTML5、CSS3、原生 JavaScript、内联 SVG；不使用 npm、外部 CDN、Vue 运行工程、FastAPI 运行工程或数据库运行环境。

**Spec:** `docs/superpowers/specs/2026-09-20-intelligent-data-analysis-assistant-design.md`

## Global Constraints

- 当前阶段只交付设计文档和静态 HTML 原型，不创建可运行的 Vue、FastAPI、LangChain 或 MySQL 工程。
- HTML 原型必须可通过 `file://` 直接打开，不依赖网络资源、npm、服务器或后端接口。
- 原型中的数据必须标注为“原型演示数据”，不得暗示真实计算或持久化已经实现。
- 产品采用现代、专业、简洁的浅色 SaaS 风格，清爽蓝色为主强调色，深蓝灰用于导航和文字层级。
- 主要展示宽度为 1440px，并保证 1024px 至 1439px 范围内可基本浏览；低于 1024px 时允许三栏工作台转为纵向分区。
- 所有核心页面必须设计正常、加载、空数据、成功、失败和无权限状态。
- 分析工作台必须呈现“用户问题 → Agent 意图 → Tool 与结构化参数 → 真实计算结果 → 图表 → AI 总结”的证据链。
- Agent 不生成或执行任意 Python 代码；SQL Tool 仅执行受控、只读、单条 SELECT 查询。
- 统一示例数据集使用销售订单语境，核心字段为 `order_date`、`region`、`product`、`sales` 和 `quantity`。
- API 统一前缀为 `/api/v1`，产品、前端、后端、数据库和接口文档中的名称必须一致。
- 不引入微服务、Kafka、Redis、Kubernetes、LangGraph 或复杂工作流平台。
- 不输出依赖安装命令、项目启动日志、真实接口响应或真实计算结果。

## Review Focus

- 直接双击 `产品原型/index.html`：所有页面、样式、脚本和返回入口均应通过相对路径工作；由 Task 2 和 Task 11 验证。
- 窄桌面窗口打开三栏分析工作台：不得出现关键操作不可达或横向内容完全溢出；由 Task 5 验证。
- 数据集为空、解析失败或字段不可用：页面必须给出可恢复操作，不能显示伪造结果；由 Task 4 和 Task 6 验证。
- Agent 或 Tool 执行失败：必须保留用户问题、显示失败步骤和重试入口，不得生成看似成功的 AI 总结；由 Task 5 验证。
- 页面、API、数据表和 Tool 标识符跨文档引用：同一对象只能使用一个规范名称；由 Task 10 和 Task 11 验证。

---

### Task 1: 建立交付目录与统一术语基线

**Files:**
- Create: `README.md`
- Create: `00-项目总览/01-项目开发设计总览.md`
- Create: `00-项目总览/02-系统总体架构.md`
- Create: `00-项目总览/03-核心业务流程.md`
- Create: `00-项目总览/04-前后端数据流.md`
- Create: `00-项目总览/05-项目目录设计.md`
- Create: `00-项目总览/06-开发阶段规划.md`
- Create: `00-项目总览/07-术语与标识符字典.md`

**Interfaces:**
- Consumes: 已确认规格中的范围、技术栈、业务模块和明确排除项。
- Produces: 后续任务共同使用的规范术语、实体名、页面名、Tool 名和销售数据示例字段。

- [ ] **Step 1: 创建六个交付板块及总览目录**

创建 `00-项目总览/`、`产品原型/`、`前端运行环境/`、`后端初始工程/`、`数据库/` 和 `项目接口/`，只放设计资料，不放运行工程。

- [ ] **Step 2: 编写根目录说明**

在 `README.md` 中写明项目定位、阅读顺序、六个板块用途、原型入口、设计边界和开发使用方式；明确 `产品原型/index.html` 是演示入口。

- [ ] **Step 3: 固化术语与标识符**

在 `07-术语与标识符字典.md` 中建立以下规范映射：

| 中文术语 | 英文标识符 | 用途 |
|---|---|---|
| 数据集 | Dataset | 用户上传并解析后的 CSV/Excel 数据资源 |
| 分析会话 | AnalysisSession | 围绕一个数据集进行的多轮分析 |
| 分析消息 | AnalysisMessage | 会话中的用户或助手消息 |
| 分析记录 | AnalysisRecord | 一次 Agent/Tool 执行及最终结果 |
| 工具调用 | ToolCall | Agent 选择 Tool 后形成的结构化调用 |

补充八个 Tool 名、主要 API 资源名和核心数据库表名，后续文件不得创建同义替代命名。

- [ ] **Step 4: 编写总体架构和核心流程**

用 Mermaid 绘制浏览器、Vue、FastAPI、Analysis Service、Agent、Tool、Pandas、MySQL 和 DeepSeek API 的容器关系；核心流程必须包含数据上传、数据集解析、自然语言分析、Tool 执行和历史回看。

- [ ] **Step 5: 编写数据流与开发阶段建议**

分别描述上传流、分析流和历史详情流；开发阶段按“基础骨架 → 用户与数据集 → Agent/Tool → 图表与历史 → 完整联调”排列，但不提供安装或运行命令。

- [ ] **Step 6: 校验总览文档覆盖**

逐项检查根 README 可导航到五个一级设计目录，总览文档明确项目是单体前后端分离系统，且没有将原型描述成已运行产品。

### Task 2: 建立 HTML 原型共享视觉系统与导航入口

**Files:**
- Create: `产品原型/README.md`
- Create: `产品原型/index.html`
- Create: `产品原型/assets/css/tokens.css`
- Create: `产品原型/assets/css/base.css`
- Create: `产品原型/assets/css/components.css`
- Create: `产品原型/assets/css/pages.css`
- Create: `产品原型/assets/js/mock-data.js`
- Create: `产品原型/assets/js/prototype.js`
- Create: `产品原型/docs/01-产品信息架构.md`
- Create: `产品原型/docs/02-全局页面框架.md`
- Create: `产品原型/docs/03-UI视觉规范.md`
- Create: `产品原型/docs/04-通用交互规范.md`
- Create: `产品原型/docs/05-页面状态规范.md`

**Interfaces:**
- Consumes: Task 1 的术语、页面模块、销售数据字段和架构边界。
- Produces: 全部 HTML 页面复用的视觉变量、布局、组件类、原型交互入口与模拟数据。

- [ ] **Step 1: 定义设计变量**

在 `tokens.css` 中集中定义颜色、字号、行高、间距、圆角、阴影、边框、侧边栏宽度、顶部栏高度和内容最大宽度。至少包含 brand、neutral、success、warning、danger、info 六类语义色及可见焦点样式。

- [ ] **Step 2: 定义基础与共享组件样式**

在 `base.css` 中处理字体栈、盒模型、页面背景、链接、按钮和无障碍辅助类；在 `components.css` 中定义侧边栏、顶部栏、卡片、指标、表格、表单、Tag、Toast、Dialog、Tabs、Timeline、Tool Call Card 和空状态。

- [ ] **Step 3: 定义页面布局与响应规则**

在 `pages.css` 中定义认证页、Dashboard、列表页、详情页、上传页和分析工作台布局。为工作台设置 1440px 三栏、1024px 至 1439px 压缩三栏、低于 1024px 纵向分区规则。

- [ ] **Step 4: 建立统一模拟数据**

在 `mock-data.js` 中定义 `prototypeDatasets`、`prototypeColumns`、`prototypeHistory` 和 `prototypeToolCall`；示例数据必须使用“2026 年销售订单”及规范字段，并带有 `isPrototypeData: true`。

- [ ] **Step 5: 建立无后端原型交互**

在 `prototype.js` 中只实现菜单激活、Tab 切换、折叠展开、Dialog 开关、Toast 演示、状态演示切换和图表/表格视图切换。所有按钮使用 `data-prototype-action` 显式标识，禁止发起网络请求。

- [ ] **Step 6: 创建原型总览入口**

`index.html` 按用户系统、Dashboard、数据集、智能分析、图表、会话和历史分组展示页面卡片；每张卡片说明页面目标、完成状态和入口，并显示“全部内容为原型演示数据”的固定提示。

- [ ] **Step 7: 编写产品与视觉设计文档**

信息架构文档提供一级/二级导航树；视觉规范记录色板、字体、密度、表格、表单、图表和状态语义；交互规范记录加载、确认、反馈、键盘焦点和错误恢复方式。

- [ ] **Step 8: 验证本地文件入口**

检查 `index.html` 只使用相对路径，所有 CSS 与 JavaScript 文件均存在，不包含 `http://`、`https://`、`fetch(`、`XMLHttpRequest` 或模块打包器引用。

### Task 3: 制作用户系统与 Dashboard 原型

**Files:**
- Create: `产品原型/pages/auth/login.html`
- Create: `产品原型/pages/auth/register.html`
- Create: `产品原型/pages/auth/profile.html`
- Create: `产品原型/pages/dashboard/dashboard.html`
- Create: `产品原型/docs/pages/01-用户系统页面设计.md`
- Create: `产品原型/docs/pages/02-Dashboard页面设计.md`

**Interfaces:**
- Consumes: Task 2 的 tokens、基础组件、页面布局和原型交互属性。
- Produces: 登录后全局应用框架、用户入口与 Dashboard 快捷入口的标准表现。

- [ ] **Step 1: 制作登录与注册页**

登录页包含品牌说明、用户名、密码、显示/隐藏密码、登录按钮和注册链接；注册页包含用户名、密码、确认密码、协议提示和返回登录。提交只演示加载、字段错误与成功跳转状态，不保存数据。

- [ ] **Step 2: 制作个人信息页**

展示头像占位、用户名、创建时间和账号安全说明；编辑动作打开原型 Dialog，并标明真实保存尚未接入。

- [ ] **Step 3: 制作 Dashboard**

包含数据集数量、分析次数、图表数量和最近分析次数四张卡片，以及最近数据集、最近分析和快速开始；上传数据和开始分析分别链接到数据上传页与分析工作台。

- [ ] **Step 4: 补齐页面状态**

为登录错误、Dashboard 首次使用空状态、列表局部加载失败和用户菜单无权限项提供可见示例状态与恢复动作。

- [ ] **Step 5: 编写对应页面文档**

每份文档包含目标、入口、布局、控件、状态、页面跳转、对应组件、API 映射、响应式规则和验收要点。

- [ ] **Step 6: 校验认证页与应用页边界**

确认认证页不显示应用侧边栏，登录后的三个页面使用同一侧边栏和顶部栏结构；密码字段默认遮罩且有可访问标签。

### Task 4: 制作数据集管理全流程原型

**Files:**
- Create: `产品原型/pages/datasets/dataset-list.html`
- Create: `产品原型/pages/datasets/dataset-upload.html`
- Create: `产品原型/pages/datasets/dataset-detail.html`
- Create: `产品原型/pages/datasets/dataset-preview.html`
- Create: `产品原型/pages/datasets/dataset-columns.html`
- Create: `产品原型/docs/pages/03-数据集管理页面设计.md`

**Interfaces:**
- Consumes: Task 2 的共享组件、模拟数据和原型交互；Task 1 的 Dataset 术语。
- Produces: 分析工作台所依赖的数据集选择、字段 Schema 和数据预览的产品表达。

- [ ] **Step 1: 制作数据集列表页**

表格展示文件名、类型、行数、列数、大小、上传时间和状态；提供搜索、格式筛选、分页、上传、查看、开始分析和删除入口。

- [ ] **Step 2: 制作数据上传页**

设计拖拽区、文件选择、CSV/XLSX 规则、大小限制说明、上传进度、解析进度、成功摘要和失败原因。失败状态提供重新选择与重试，不进入详情页。

- [ ] **Step 3: 制作数据集详情页**

包含数据集元信息、解析状态、数据质量摘要、预览与字段 Tab、开始分析按钮和删除确认 Dialog。

- [ ] **Step 4: 制作数据预览与字段页**

预览页展示前 N 行并固定说明“预览数据”；字段页展示字段名、类型、缺失值、唯一值数量和示例值。列很多时表格区域独立横向滚动。

- [ ] **Step 5: 补齐异常与空状态**

覆盖无数据集、搜索无结果、上传格式不支持、文件过大、解析失败、空文件、字段不可识别和无权限访问；禁止这些状态显示分析结果。

- [ ] **Step 6: 编写数据集页面文档**

明确上传状态机 `selected → validating → uploading → parsing → ready|failed`，并映射数据集 API、Dataset/DatasetColumn 实体和分析工作台入口。

- [ ] **Step 7: 校验操作可恢复性**

逐页确认错误状态都有返回、重试、重新选择或联系管理员中的至少一个合理动作，删除操作必须通过应用内 Dialog 确认。

### Task 5: 制作 Agent 智能分析工作台与执行证据链原型

**Files:**
- Create: `产品原型/pages/analysis/analysis-workspace.html`
- Create: `产品原型/pages/analysis/agent-process.html`
- Create: `产品原型/pages/analysis/tool-call-detail.html`
- Create: `产品原型/pages/analysis/analysis-result.html`
- Create: `产品原型/docs/pages/04-Agent智能分析页面设计.md`
- Create: `产品原型/docs/pages/05-Tool调用与结果展示设计.md`

**Interfaces:**
- Consumes: Task 4 的数据集与字段表达；Task 2 的 Timeline、Tool Call Card、表格、Tabs 和模拟 Tool 数据。
- Produces: 图表、会话、历史和 `POST /api/v1/analysis/chat` 设计所依赖的标准分析表现。

- [ ] **Step 1: 制作三栏分析工作台**

左栏显示选中数据集、字段和推荐问题；中栏显示对话、输入框、停止/发送动作和 Agent 时间线；右栏显示指标、表格、图表、Tool 结果和最终总结。用户问题使用“统计不同地区销售额并生成柱状图”。

- [ ] **Step 2: 展示完整执行链路**

按 `理解问题 → 选择 group_by_analysis → 校验参数 → 执行计算 → 选择 generate_chart → 生成总结` 展示时间线。`group_by_analysis` 参数固定示例为 `group_column: region`、`value_column: sales`、`aggregation: sum`。

- [ ] **Step 3: 制作 Tool 调用详情页**

展示 Tool 描述、结构化参数、校验状态、执行耗时、结果摘要、结果行数和关联消息；不得展示自由 Python 代码、数据库连接串或模型内部思维过程。

- [ ] **Step 4: 制作独立分析结果页**

将问题、数据集、关键指标、图表、明细表、AI 总结、Tool 证据和执行耗时组织为可回看的结果页面。

- [ ] **Step 5: 补齐执行状态**

通过原型状态切换演示等待、理解中、Tool 执行中、成功、Tool 参数错误、Tool 执行失败、模型总结失败和用户取消。失败时保留问题与已完成步骤，提供重试或修改问题入口；总结失败不得显示伪造结论。

- [ ] **Step 6: 编写工作台与 Tool 展示文档**

明确消息结构、执行状态机、自动滚动规则、停止行为、错误恢复、结果区信息优先级和 API 字段映射。

- [ ] **Step 7: 验证窄屏与长内容**

在 1440px、1280px 和 1024px 视口检查字段列表、对话、长 Tool 参数和结果表格；低于 1024px 时三栏顺序必须保持“数据上下文 → 对话过程 → 分析结果”，主要动作可访问。

### Task 6: 制作图表、会话、历史与全局状态原型

**Files:**
- Create: `产品原型/pages/charts/chart-view.html`
- Create: `产品原型/pages/charts/chart-config.html`
- Create: `产品原型/pages/sessions/session-list.html`
- Create: `产品原型/pages/history/history-list.html`
- Create: `产品原型/pages/history/history-detail.html`
- Create: `产品原型/pages/states/state-gallery.html`
- Create: `产品原型/docs/pages/06-图表分析页面设计.md`
- Create: `产品原型/docs/pages/07-分析会话页面设计.md`
- Create: `产品原型/docs/pages/08-分析历史页面设计.md`
- Create: `产品原型/docs/06-页面流程与跳转关系.md`

**Interfaces:**
- Consumes: Task 5 的分析结果、Tool 证据与共享图表容器；Task 2 的状态组件。
- Produces: 可复用的图表协议表达、会话/历史导航和全局状态样例库。

- [ ] **Step 1: 制作图表页**

使用内联 SVG 绘制柱状图、折线图和饼图示意；图表查看页提供指标说明、图例、数据表切换和来源 Tool；配置页只演示图表类型、X/Y 轴和聚合方式选择，不进行真实计算。

- [ ] **Step 2: 制作分析会话页**

展示会话标题、数据集、消息数、最近分析时间和状态；支持查看、继续分析、重命名和删除确认。删除后显示可撤销的原型反馈，不实现真实恢复。

- [ ] **Step 3: 制作历史列表与详情页**

历史列表展示问题、数据集、Tool、状态、执行时间和创建时间；详情页展示问题、数据集、Agent 判断、Tool 名称、参数、结果、图表、最终回答和耗时，并提供再次分析入口。

- [ ] **Step 4: 制作状态样例库**

集中展示空状态、加载状态、成功、失败、无权限、文件解析失败、Agent 失败和局部数据不可用，说明每种状态的推荐文案、主动作和次动作。

- [ ] **Step 5: 编写页面文档和流程图**

使用 Mermaid 描述“Dashboard → 数据集 → 工作台 → 历史详情 → 再次分析”主流程，以及认证失败、上传失败和分析失败的恢复路径。

- [ ] **Step 6: 更新原型入口**

将 Task 3 至 Task 6 的全部页面加入 `产品原型/index.html`，确保每个模块都有入口，每个页面都有返回原型总览的链接。

- [ ] **Step 7: 校验图表语义和失败边界**

图表必须标注单位、维度、指标和数据来源；无有效数据时显示空状态，不渲染误导性图形；分析失败记录不得显示成功徽标。

### Task 7: 编写前端工程设计文档

**Files:**
- Create: `前端运行环境/README.md`
- Create: `前端运行环境/01-前端总体架构.md`
- Create: `前端运行环境/02-前端目录结构.md`
- Create: `前端运行环境/03-路由与页面设计.md`
- Create: `前端运行环境/04-Pinia状态管理设计.md`
- Create: `前端运行环境/05-API请求层设计.md`
- Create: `前端运行环境/06-核心组件拆分.md`
- Create: `前端运行环境/07-分析工作台组件设计.md`
- Create: `前端运行环境/08-ECharts图表设计.md`
- Create: `前端运行环境/09-前端交互状态规范.md`
- Create: `前端运行环境/10-前端数据模型设计.md`
- Create: `前端运行环境/11-HTML原型迁移说明.md`

**Interfaces:**
- Consumes: Task 2 至 Task 6 的页面结构、交互、组件和状态；Task 1 的术语。
- Produces: 后端接口和数据库文档可引用的前端 DTO、页面路由、Store 边界和组件职责。

- [ ] **Step 1: 设计 Vue 3 工程边界**

给出 `src/api`、`components`、`views`、`layouts`、`router`、`stores`、`utils`、`types` 和 `assets` 目录树，并逐项说明职责；采用 Vue 3 Options API 作为新页面默认风格。

- [ ] **Step 2: 设计路由和导航**

列出登录、注册、Dashboard、数据集列表/详情、分析工作台、会话、历史和详情路由，说明认证守卫、数据集 ID、会话 ID 和分析记录 ID 的使用方式。

- [ ] **Step 3: 设计 Pinia 与请求层**

划分 `authStore`、`datasetStore`、`analysisStore` 和 `uiStore`；说明 token、当前数据集、会话消息、Agent 状态、结果和错误的所有权。Axios 层定义统一响应解包、401 处理、业务错误和请求取消。

- [ ] **Step 4: 设计组件与数据模型**

将 AnalysisView 拆为 DatasetPanel、ChatPanel、AgentProcessPanel、AnalysisResult、ChartPanel、DataTable、MessageInput 和 ToolCallCard，逐项列出 props、emits、状态来源和依赖。

- [ ] **Step 5: 设计图表和交互状态**

说明 ECharts option 由受控 ChartSpec 转换，禁止直接执行模型生成的 JavaScript；定义页面级与组件级 loading、empty、error、permission-denied 状态。

- [ ] **Step 6: 编写原型迁移说明**

为每个 HTML 页面标注目标 Vue View、共享 Layout、组件拆分和需替换的模拟数据，明确哪些原型交互仅用于演示。

- [ ] **Step 7: 校验前端设计完整性**

确认每个 HTML 页面都有目标路由和 View，每个 API 调用都有 Store 或服务层归属，每个长列表都有分页策略，每个异步流程都有取消或防重复提交策略。

### Task 8: 编写后端、Agent 与 Tool 设计文档

**Files:**
- Create: `后端初始工程/README.md`
- Create: `后端初始工程/01-后端总体架构.md`
- Create: `后端初始工程/02-后端目录结构.md`
- Create: `后端初始工程/03-模块职责与依赖.md`
- Create: `后端初始工程/04-Agent架构设计.md`
- Create: `后端初始工程/05-Tool体系设计.md`
- Create: `后端初始工程/06-分析任务执行流程.md`
- Create: `后端初始工程/07-文件上传与数据解析设计.md`
- Create: `后端初始工程/08-SQL查询安全设计.md`
- Create: `后端初始工程/09-认证与数据权限设计.md`
- Create: `后端初始工程/10-异常处理与日志设计.md`

**Interfaces:**
- Consumes: Task 1 的架构与术语、Task 7 的前端 DTO 和 Task 5 的执行状态。
- Produces: API 文档、数据库设计和页面映射需要引用的服务边界、Agent 状态、Tool Schema 与错误分类。

- [ ] **Step 1: 设计 FastAPI 单体分层目录**

设计 `app/api`、`models`、`schemas`、`services`、`repositories`、`agent`、`tools`、`core`、`database` 和 `utils`，说明允许的依赖方向；Controller 不包含 Pandas 分析逻辑，Tool 不直接处理 HTTP。

- [ ] **Step 2: 设计 Agent 编排**

定义 Schema 加载、Prompt 上下文、Tool 选择、参数校验、Tool 执行、结果裁剪、模型总结、记录持久化和响应组装的顺序；区分 Agent、LLM、Tool、Pandas 与 MySQL 职责。

- [ ] **Step 3: 设计八个 Tool**

分别为 `get_dataset_info`、`preview_data`、`filter_data`、`aggregate_data`、`group_by_analysis`、`sort_data`、`sql_query` 和 `generate_chart` 提供用途、结构化输入、字段类型、验证、输出、错误和示例调用。

- [ ] **Step 4: 设计上传和解析边界**

明确文件类型、大小、存储命名、解析状态、编码/工作表选择、字段推断、预览限制和失败清理；说明文件内容不得直接进入系统 Prompt。

- [ ] **Step 5: 设计 SQL 安全**

只允许单条 SELECT；定义 SQL AST 或等价结构化解析、表白名单、字段限制、禁止多语句与注释绕过、强制 LIMIT、超时、只读账号和安全错误映射。

- [ ] **Step 6: 设计认证、权限、异常和日志**

所有 Dataset、Session 和 Record 查询必须带 user_id 所有权条件；日志记录 request_id、record_id、Tool、耗时和状态，但不记录密码、Token、原始完整数据或 DeepSeek 密钥。

- [ ] **Step 7: 校验架构可实现性**

检查是否存在循环依赖、未定义的中间层、Tool 直接修改数据库、LLM 猜测结果或过度设计；确保本科生可以在单体项目内逐层实现。

### Task 9: 编写数据库与 ER 设计文档

**Files:**
- Create: `数据库/README.md`
- Create: `数据库/01-数据库总体设计.md`
- Create: `数据库/02-ER关系设计.md`
- Create: `数据库/03-数据表字段字典.md`
- Create: `数据库/04-索引与约束设计.md`
- Create: `数据库/05-数据生命周期设计.md`
- Create: `数据库/06-初始化SQL设计.md`

**Interfaces:**
- Consumes: Task 1 的实体术语、Task 8 的持久化与权限边界。
- Produces: API 响应字段、历史详情、会话和分析记录的规范数据来源。

- [ ] **Step 1: 绘制 ER 图**

用 Mermaid ER 图表达 users 一对多 datasets、datasets 一对多 dataset_columns、datasets 一对多 analysis_sessions、analysis_sessions 一对多 analysis_messages 和 analysis_records，以及 analysis_records 与用户消息/助手消息的关联。

- [ ] **Step 2: 编写六张核心表字段字典**

逐字段说明名称、MySQL 类型、是否可空、默认值、主外键、业务含义和示例。analysis_records 必须覆盖用户问题、Tool 名、Tool 参数 JSON、Tool 结果 JSON、最终回答、图表 JSON、执行耗时和状态。

- [ ] **Step 3: 设计索引和约束**

至少包含用户名唯一索引、用户与创建时间组合索引、数据集与会话索引、会话与消息时间索引、记录状态与创建时间索引；定义外键删除策略，避免删除数据集后留下不可解释的孤儿记录。

- [ ] **Step 4: 设计数据生命周期**

说明上传文件、解析元数据、会话、消息、记录和图表协议的创建、保留、删除与失败清理，不将大体量完整数据表直接复制进 analysis_records。

- [ ] **Step 5: 描述初始化 SQL 顺序**

只描述字符集、建表顺序、外键顺序、索引顺序和初始枚举/状态约束，不生成可执行的完整建表脚本。

- [ ] **Step 6: 校验关系与查询场景**

逐项验证“用户的数据集列表”“数据集的会话”“会话消息”“分析历史列表”“分析详情”都有明确关系和索引支持。

### Task 10: 编写 REST API、Agent 协议与跨层映射

**Files:**
- Create: `项目接口/README.md`
- Create: `项目接口/01-API总体规范.md`
- Create: `项目接口/02-认证接口.md`
- Create: `项目接口/03-数据集接口.md`
- Create: `项目接口/04-智能分析接口.md`
- Create: `项目接口/05-分析会话接口.md`
- Create: `项目接口/06-历史记录接口.md`
- Create: `项目接口/07-Agent与Tool数据协议.md`
- Create: `项目接口/08-图表数据协议.md`
- Create: `项目接口/09-统一响应与错误码.md`
- Create: `项目接口/10-接口调用时序.md`
- Create: `产品原型/docs/07-页面与API映射表.md`
- Create: `产品原型/docs/08-页面与数据表映射表.md`
- Create: `产品原型/docs/09-页面与前端组件映射表.md`

**Interfaces:**
- Consumes: Task 3 至 Task 6 的页面操作、Task 7 的前端模型、Task 8 的服务/Tool Schema、Task 9 的实体字段。
- Produces: 全项目唯一的请求、响应、错误、ToolCall、ChartSpec 和跨层追踪契约。

- [ ] **Step 1: 定义统一 API 规范**

统一 `/api/v1`、认证头、JSON 命名、时间格式、分页结构和 `{code, message, data}` 响应；区分 HTTP 状态码与业务错误码。

- [ ] **Step 2: 设计认证和数据集接口**

完整描述 `POST /auth/register`、`POST /auth/login`、`GET /auth/me`、`POST /datasets/upload`、`GET /datasets`、`GET /datasets/{id}`、`DELETE /datasets/{id}`、`GET /datasets/{id}/preview` 和 `GET /datasets/{id}/columns` 的请求、响应、字段和错误。

- [ ] **Step 3: 设计会话和历史接口**

完整描述会话创建、列表、详情、删除，以及历史列表和详情；定义分页、所有权校验、删除后的响应和再次分析所需字段。

- [ ] **Step 4: 详细设计智能分析接口**

`POST /analysis/chat` 请求至少包含 `session_id`、`dataset_id` 和 `question`；响应至少包含 `session_id`、`message_id`、`answer`、`tool_name`、`tool_parameters`、`tool_result`、`chart` 和 `execution_time`。补充状态、record_id、错误对象和可重试信息。

- [ ] **Step 5: 定义 Agent、Tool 与图表协议**

ToolCall 需要 `tool_call_id`、`tool_name`、`parameters`、`status`、`started_at`、`finished_at`、`duration_ms`、`result_summary` 和 `error`；ChartSpec 只允许受控类型、维度、指标、系列和数据，不允许可执行脚本。

- [ ] **Step 6: 编写错误码和接口时序**

覆盖认证失败、资源不存在、格式错误、解析失败、参数无效、Tool 失败、SQL 拒绝、模型不可用和服务内部错误；用 Mermaid 时序图描述上传、分析和历史详情。

- [ ] **Step 7: 建立三张跨层映射表**

逐页列出页面操作 → API → Store/组件 → 后端服务 → 数据表；Tool 页面展示必须能追踪到 ToolCall 协议和 analysis_records 字段。

- [ ] **Step 8: 校验标识符一致性**

对照 `00-项目总览/07-术语与标识符字典.md` 检查 Dataset、AnalysisSession、AnalysisMessage、AnalysisRecord、八个 Tool 和所有 URL，没有同义漂移或缺失映射。

### Task 11: 完整性、链接与视觉验收

**Files:**
- Modify: `README.md`
- Modify: `产品原型/index.html`
- Modify: `产品原型/docs/06-页面流程与跳转关系.md`
- Create: `00-项目总览/08-设计交付物索引.md`
- Create: `00-项目总览/09-设计验收清单.md`

**Interfaces:**
- Consumes: Task 1 至 Task 10 的全部交付物。
- Produces: 可导航、无缺页、无断链、术语一致且视觉可检查的最终设计包。

- [ ] **Step 1: 建立设计交付物索引**

按 PRD、信息架构、页面原型、交互、前端、后端、数据库、API、Agent、Tool、SQL 安全、数据流和目录设计列出对应文件，确保原需求的十二类重点输出均可定位。

- [ ] **Step 2: 执行文件与相对链接检查**

枚举所有 Markdown 与 HTML 相对链接，确认目标文件存在；重点检查从 `产品原型/index.html` 进入每个页面并返回总览的路径，CSS、JavaScript 和内联 SVG 不依赖网络。

- [ ] **Step 3: 执行内容完整性检查**

搜索未完成标记、空标题、无正文文件、错误的 `/analysis/chat` 前缀、旧 Tool 名和不一致字段；检查所有页面文档包含目标、路径、状态、组件、API、响应式和验收信息。

- [ ] **Step 4: 执行浏览器视觉检查**

通过本地文件入口依次查看登录、Dashboard、数据集列表、上传、详情、工作台、Tool 详情、图表、会话、历史和状态样例；检查 1440px、1280px、1024px 与窄屏布局、键盘焦点、Dialog、Tabs、长文本和表格滚动。

- [ ] **Step 5: 执行状态与安全边界检查**

确认空数据不显示伪造图表、Tool 失败不生成成功总结、SQL 页面明确只读限制、原型没有网络请求、敏感值没有出现在 URL、模拟数据均有原型标识。

- [ ] **Step 6: 完成最终验收清单**

在 `09-设计验收清单.md` 逐项记录设计文件是否存在、原型入口是否可达、页面是否覆盖、跨层映射是否完整，以及当前明确未实现的运行能力。

- [ ] **Step 7: 更新根 README 的最终导航**

将最终目录、推荐阅读顺序、HTML 原型入口和各设计索引写入根 README，使未参与设计过程的开发人员可以从一个入口开始工作。

