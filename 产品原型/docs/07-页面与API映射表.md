# 页面与 API 映射表

| 页面/操作 | API |
|---|---|
| 登录 | POST `/api/v1/auth/login` |
| 注册 | POST `/api/v1/auth/register` |
| 用户信息 | GET `/api/v1/auth/me` |
| Dashboard | GET `/api/v1/datasets`、GET `/api/v1/history`（摘要参数） |
| 数据集列表/上传 | GET/POST `/api/v1/datasets` |
| 数据集详情/删除 | GET/DELETE `/api/v1/datasets/{id}` |
| 数据预览 | GET `/api/v1/datasets/{id}/preview` |
| 字段信息 | GET `/api/v1/datasets/{id}/columns` |
| 分析工作台发送 | POST `/api/v1/analysis/chat` |
| 会话列表/创建 | GET/POST `/api/v1/analysis/sessions` |
| 会话详情/删除 | GET/DELETE `/api/v1/analysis/sessions/{id}` |
| 历史列表/详情 | GET `/api/v1/history`、GET `/api/v1/history/{id}` |

原型页面不发起这些请求；映射用于后续 Vue 开发。

