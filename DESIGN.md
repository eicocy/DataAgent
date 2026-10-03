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
  DEFAULT: "0.875rem"
  sm: "0.5rem"
  md: "0.875rem"
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

自然语言是入口，Prompt Composer 是首页视觉中心。空会话只显示欢迎语、输入、附件与少量示例；分析开始后展开执行证据与交付区。白色与浅灰构成安静的三栏工作台，沿用真实计算证据的来源标识。

### Product context and register

- **用户与主要任务：** 数据分析初学者、学生、运营和销售人员，通过自然语言完成可验证的数据分析。
- **目标市场：** 中文教学和求职展示场景；依据为已确认项目规格。
- **语言：** 首期简体中文，字段标识符和 Tool 名保留英文；时间按 `Asia/Shanghai` 展示。
- **使用场景：** 1024px 以上桌面浏览器为主，频繁查看表格、字段、工具参数和图表。
- **产品风格：** 任务型产品界面，效率和证据可读性优先。
- **记忆点：** “Evidence Rail（证据轨）”——一条青绿色执行轨把意图、Tool、参数、结果和总结串联起来。
- **克制：** 首页采用对话工作台，次级页面保留熟悉的数据管理控件；不使用无意义渐变、玻璃拟态和装饰动画。
- **反例：** 不做纯聊天机器人、不做黑色终端风、不做密集 BI 仪表盘拼贴。
- **Token 所有权：** 本文件是设计意图与语义 Token 源；`frontend/src/styles/tokens.css` 是正式 Vue 应用运行映射；历史静态原型不作为新工作台验收依据。卡片沿用 14px、Composer 为 16px 圆角。

## Colors

`ink` 提供可信的深蓝灰文字与导航；`brand` 用于主操作和当前导航；`evidence` 专用于“由 Tool 验证”的证据节点；`canvas` 与 `surface` 形成安静的浅色层级；`danger` 仅用于不可继续或破坏性状态。图表以 brand、evidence、紫色、橙色和中性灰组成固定序列，不能用颜色作为唯一含义。

## Typography

标题使用 Bahnschrift/Segoe UI Variable Display，形成略带工程感的紧凑字面；正文使用 Segoe UI Variable Text 与 Microsoft YaHei UI；字段名、参数、耗时和数值使用 Cascadia Mono/Consolas。正文基线 14px，页面标题 24–30px，表格和参数保持数字等宽。

## Layout

工作台复用 240px 侧栏与 68px 顶栏。首页中间 Prompt 最大 940px，空会话折叠右栏；有结果时为侧栏 / 弹性对话 / 420—720px 工件栏。窄屏导航与工件采用抽屉，输入框和主要内容单列排列。数据管理页继续复用已有布局，表格自身拥有水平滚动，不通过裁切隐藏字段。

## Elevation & Depth

层级主要依靠底色、边框和间距；普通卡片使用 1px 边框，不使用浮夸阴影。悬浮菜单与 Dialog 允许柔和阴影。Tool 执行节点通过 evidence 色左轨和状态点形成深度，不依赖阴影。

## Shapes

控件沿用 8px 圆角，卡片 14px，Composer 16px。Tag 使用完整圆角，但主按钮不做胶囊形。分隔线保持 1px，图标沿用现有 Element Plus 图标。

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

