# AI Workspace 升级：Phase 1

本阶段让自然语言输入与数据附件成为默认入口，继续使用原 Agent、工具和报告服务。完整五阶段方案见 UPGRADE_PLAN.md，实际验证和限制见 UPGRADE_PROGRESS.md。

## 使用入口

- `/`：空会话工作台；打开不会创建 Session。发送问题或开始上传时才创建。
- `/analysis/:sessionId?`：兼容既有分析链接、数据集入口和历史会话。
- `/templates`：15 个方向，105 个策略模板；选择可用示例填入 Prompt，用户可修改。当前尚未将模板 ID 传给 Planner。
- `/overview`：保留原概览；数据、历史、会话、文件库继续可访问。

## 上传与附件

当前支持 CSV/TSV/JSON/XLS/XLSX/Parquet，限制取服务端能力目录。最多十个保留附件，单文件默认 20 MiB；文件逐项复用现有上传 API、Dataset Store 和后台解析，不新建解析系统。Excel 多工作表需选择后上传。

逐文件显示上传、解析、失败、停止等待和重试。停止等待仅取消客户端请求；已受理解析仍在后台，恢复已知 ID 不重复 POST。明确解析失败可重新提交。所有上传成功文件仍可在数据集页访问，即使会话绑定失败。

Session 通过 `PATCH /api/v1/analysis/sessions/{id}` 的 `attached_dataset_ids` 保存附件。写入检查所有者、就绪状态、上限、会话互斥；读回过滤删除/越权/非就绪数据。字段通过 ConversationContext 传递，不在后续序列化时丢失。前端附件增删同一序列执行，防止完整列表覆盖竞争。

当前分析明确使用所选的一个数据集；附件集合不代表跨表执行已开放。

## 新 API

- `GET /api/v1/workspace/capabilities`：认证用户读取当前格式、资源限制、模型配置存在性、报告格式和功能开关，不返回密钥/地址。
- `GET /api/v1/analysis/profiles?category=general`：认证策略目录；availability 同时检查实际 Registry。
- `GET /api/v1/analysis/profiles/{id}`：单模板 Schema、用途、示例、推荐数据与限制。
- `PATCH /api/v1/analysis/sessions/{id}`：扩展可选附件字段，title/is_pinned 旧调用保持兼容。

深度、自动报告和模型切换尚未生效，界面禁用并说明；预测和专业口径在后续阶段开放。

## 图表与兼容

前端同一适配器读取旧 data 和规范 points，覆盖后端已有 bar/line/pie/scatter/histogram/area/donut/boxplot/box/heatmap/funnel/waterfall。缺失值不补零，热力图空相关系数不回退到坐标，瀑布按有符号变化计算实际起止位置。高清生成在参数切换与卸载时取消失效请求。

## 验证

后端 482 通过、4 MySQL 跳过；前端 49 通过；生产构建通过；2 条受控 API 浏览器流程通过；静态 UI 审计无发现。真实 MySQL、Docker 和真实模型未验收，不将替身流程当作实际计算证明。没有数据库迁移。
