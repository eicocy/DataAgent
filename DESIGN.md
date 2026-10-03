---
version: alpha
name: "DataLens Agent"
description: "以可追溯计算证据为核心的中文智能数据分析工作台"
colors:
  ink: "#12213A"
  brand: "#2F6BFF"
  evidence: "#18A999"
  canvas: "#F3F6FA"
  surface: "#FFFFFF"
  danger: "#D9415D"
typography:
  display:
    fontFamily: "Bahnschrift, Segoe UI Variable Display, Microsoft YaHei UI, sans-serif"
  sans:
    fontFamily: "Segoe UI Variable Text, Microsoft YaHei UI, system-ui, sans-serif"
  data:
    fontFamily: "Cascadia Mono, Consolas, monospace"
rounded:
  DEFAULT: "0.625rem"
  sm: "0.375rem"
  md: "0.625rem"
  lg: "1rem"
spacing:
  compact: "0.5rem"
  control: "0.75rem"
  panel: "1.25rem"
  section: "2rem"
components:
  button: {}
  card: {}
  dialog: {}
  table: {}
  tool-call-card: {}
---

# DataLens Agent Design System

## Overview

### Creative North Star

界面借鉴“分析师工作台上的实验记录板”：结论旁边始终能看到数据来源、计算步骤和工具状态。产品不是聊天气泡的放大版，而是一张把数据上下文、推理动作与计算结果并列摆放的分析桌面。

### Product context and register

- **用户与主要任务：** 数据分析初学者、学生、运营和销售人员，通过自然语言完成可验证的数据分析。
- **目标市场：** 中文教学和求职展示场景；依据为已确认项目规格。
- **语言：** 首期简体中文，字段标识符和 Tool 名保留英文；时间按 `Asia/Shanghai` 展示。
- **使用场景：** 1024px 以上桌面浏览器为主，频繁查看表格、字段、工具参数和图表。
- **产品风格：** 任务型产品界面，效率和证据可读性优先。
- **记忆点：** “Evidence Rail（证据轨）”——一条青绿色执行轨把意图、Tool、参数、结果和总结串联起来。
- **克制：** 导航、表单、表格遵循熟悉后台模式；不使用无意义渐变、玻璃拟态和装饰动画。
- **反例：** 不做纯聊天机器人、不做黑色终端风、不做密集 BI 仪表盘拼贴。
- **Token 所有权：** 本文件是设计意图与语义 Token 源；`frontend/src/styles/tokens.css` 是正式 Vue 应用运行映射；`产品原型/assets/css/tokens.css` 保留静态原型映射。现有 Vue 控件与卡片圆角由运行映射定义，本次不重做视觉。

## Colors

`ink` 提供可信的深蓝灰文字与导航；`brand` 用于主操作和当前导航；`evidence` 专用于“由 Tool 验证”的证据节点；`canvas` 与 `surface` 形成安静的浅色层级；`danger` 仅用于不可继续或破坏性状态。图表以 brand、evidence、紫色、橙色和中性灰组成固定序列，不能用颜色作为唯一含义。

## Typography

标题使用 Bahnschrift/Segoe UI Variable Display，形成略带工程感的紧凑字面；正文使用 Segoe UI Variable Text 与 Microsoft YaHei UI；字段名、参数、耗时和数值使用 Cascadia Mono/Consolas。正文基线 14px，页面标题 24–30px，表格和参数保持数字等宽。

## Layout

后台使用 232px 固定侧栏与 68px 顶栏。内容区采用 24px 外边距，最大宽度不锁死以适应数据表。分析工作台在 1440px 使用 260px / minmax(420px, 1fr) / minmax(360px, 0.9fr) 三栏；1280px 压缩间距；低于 1024px 按数据上下文、对话、结果的顺序纵向排列。表格自身拥有水平滚动，不通过裁切隐藏字段。

## Elevation & Depth

层级主要依靠底色、边框和间距；普通卡片使用 1px 边框，不使用浮夸阴影。悬浮菜单与 Dialog 允许柔和阴影。Tool 执行节点通过 evidence 色左轨和状态点形成深度，不依赖阴影。

## Shapes

控件与普通卡片使用 10px 圆角，关键指标和空状态容器可使用 16px。Tag 使用完整圆角，但主按钮不做胶囊形。分隔线保持 1px，图标为 1.75px 圆角描边风格。

## Components

### Foundational visual states

所有控件定义默认、hover、focus-visible、active、disabled、busy、success、warning 和 error；焦点使用 3px 半透明 brand 环。加载区预留高度，错误信息不推动主要按钮跳动。

### Buttons and actions

按钮通过“强调程度 × 语义意图”组合。一个区域只有一个实心主按钮；删除在普通页面使用低强调 danger，在确认 Dialog 中使用实心 danger。忙碌状态保持按钮尺寸。

### Navigation and data display

侧栏当前项使用浅蓝底和左侧短标尺。数据表采用原生 `<table>`、粘性表头、可见滚动提示和分页。Evidence Rail 只用于真实分析过程，不作为通用装饰。

### Forms and overlays

表单由产品自行呈现校验；密码默认遮罩并提供显示按钮；上传区同时提供文件选择按钮；Dialog 拥有标题、说明、明确动词、取消动作和焦点恢复。

### Iconography

原型使用内联 SVG 或字符图标，不使用远程图标库。操作必须保留文字标签；仅对明显的关闭、展开和状态控件使用纯图标，并提供可访问名称。

### Motion

动效只表示状态：hover 120ms、面板/提示 180ms、Dialog 220ms。`prefers-reduced-motion: reduce` 下取消位移和缩放，只保留不超过 100ms 的透明度变化。

### Content and data visualization

文案从用户任务出发，使用“上传数据”“开始分析”“重新执行”等具体动词。数值使用中文千分位和明确单位。图表必须同时提供数据表，标出指标、维度、单位和来源 Tool。

## Do's and Don'ts

- **Do：** 让每个结论都能追溯到 Tool、参数和结果摘要。
- **Do：** 在所有页面复用统一导航、按钮、表格、状态和反馈词汇。
- **Don't：** 用模型“思考过程”冒充计算证据，只展示产品级执行阶段。
- **Don't：** 为了科技感堆叠渐变、霓虹、玻璃和持续动画。

