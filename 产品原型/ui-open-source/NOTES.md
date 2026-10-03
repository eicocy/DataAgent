# 开源项目启发的五种分析工作台 UI

打开 [五方案对比页](../ui-open-source-five.html)。顶部标签可切换 A–E；`?variant=A` 至 `?variant=E` 可直达。页面在本地 `file://` 下工作，CSS 和 JavaScript 都在仓库内，不依赖外部资源。键盘焦点不在链接或其他交互控件上时，左右方向键也可切换方案。

## 共同比较基准

- 问题：**各地区销售额分别是多少？哪个地区最高？**
- 来源：仓库根目录 `sample-data/sales_demo.csv`，10 条订单，字段 `order_date, region, product, sales, quantity`。
- 地区结果：华南 12,439 元（3 单）、华东 10,777 元（3 单）、西南 9,979 元（2 单）、华北 3,898 元（2 单）。合计 37,093 元；华南约占 33.5%。
- 演示链：识别问题和字段 → `group_by_analysis(group_column=region, value_column=sales, aggregation=sum)` → `generate_chart(type=bar, x=region, y=sales_sum)` → 引用 Tool 结果形成结论。展示的 482 ms、126 ms 和状态是示例执行记录；页面并未调用 Agent 或 Tool。
- 每套页面均可看到用户问题、Agent 阶段、Tool 参数、结果图表、结果表与结论。五个图表和表格由同一份前端样例常量生成，避免比较时数值漂移。

## 方案与开源参考

| 方案 | 视觉规范与版式 | 标志性信息组织 | 参考项目与借鉴点 | 取舍 |
|---|---|---|---|---|
| A 清晰对话 | 纸白 `#FFFFFF`、浅灰蓝 `#F7F9FC`、钴蓝 `#2255DE`、文字蓝灰 `#24324B`；Bahnschrift 标题、Segoe UI 中文正文、Cascadia Mono 数值；左导航加窄幅问答流 | 一条回答内按阶段、图表、展开表格、展开 Tool 参数递进 | [Vanna](https://github.com/vanna-ai/vanna) 的进度、表格、图表、自然语言总结组合。借鉴组件次序，不模拟真实流式 API | 连续追问很自然；专业用户需要展开才能看到全部参数 |
| B Agent 执行舱 | 深石墨 `#0C1821`、蓝黑 `#142833`、青绿 `#5FE0CE`、柔白 `#EAF8FA`；Bahnschrift 主标题、Consolas 轨迹；问题／结果／执行轨三栏 | 结果旁始终能定位对应 Tool 节点与参数 | [DB-GPT](https://github.com/eosphoros-ai/DB-GPT) 的多工具分析、图表和报告流程 | Agent 工作过程最鲜明；内容密度较高，手机端需要纵向阅读 |
| C 可信指标台 | 冰白 `#F3F7FB`、靛蓝 `#4857BC`、深蓝字 `#27375A`、浅蓝面 `#EAF0F8`；Segoe UI 标题与正文、等宽字段名；指标定义与结果并列 | 指标口径、数据源、Tool 结果和结论形成可追溯链 | [WrenAI](https://github.com/Canner/WrenAI) 的受治理指标与查询依据。当前主线侧重语义层；旧版聊天式 BI UI 已冻结在 `legacy/v1`，这里不把旧版当成当前产品界面 | 适合需要核对口径的业务分析；单次轻量问答显得较正式 |
| D 数据工坊 | 钢灰 `#DFE3E9`、面板白 `#FCFCFE`、代码紫 `#6049BD`、文字灰蓝 `#344057`；Segoe UI 界面与 Consolas 参数；字段／方法／结果三块工作区，桌面可调整前两块宽度 | 从字段选择到 Tool 参数再到表格结果顺序清楚 | [Chat2DB](https://github.com/OtterMind/Chat2DB) 的元数据浏览、SQL 工作区、结果与图表并置；本稿只展示只读 Tool 参数，不提供 SQL 编辑执行 | 最适合开发者或分析师；新用户需要理解较多专业字段 |
| E 分析审阅台 | 浅灰 `#F5F3F6`、紫红 `#963D77`、深紫灰 `#3F3545`、审阅面 `#F2E9F0`；Georgia／宋体标题、Segoe UI 正文、Cascadia Mono 记录值；结论主卡加结果／审阅双栏 | 成功数、失败数、示例耗时与参数记录集中可复查 | [Dataherald](https://github.com/Dataherald/dataherald) 的配置和可观测控制台思路 | 适合验收和复盘；实时继续提问的入口较弱 |

这些仓库是交互与信息架构参考，页面颜色、字体、形状和布局为 DataLens Agent 单独设计。原型没有复制开源项目的视觉素材或代码。

## 原型边界与检查点

本页只用于选择分析工作台方向，不提供登录、上传、模型调用、数据库查询、结果保存或真实监控。D 的宽度调整是浏览器原生 CSS `resize`，仅用于桌面对比；窄屏改为纵向顺序。与仓库的 `DESIGN.md`、`UX-CONTRACT.md` 相比，这五套是候选探索，不表示已经批准改动正式产品的设计系统。

验收时逐一检查 A–E 的桌面和手机宽度：能找到同一个问题、两项 Tool 参数、四地区图表／数据表与结论；数值一致；切换和直达链接可用；键盘焦点可见；降低动效设置下没有非必要动画。
