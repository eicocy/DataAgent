# Pinia 状态管理设计

## authStore

`user`、`authStatus`；动作 register/login/loadMe/logout。访问令牌建议由 HttpOnly Cookie 管理；若后端采用 Bearer token，应采用明确的安全方案而非随意持久化。

## datasetStore

`items`、`currentDataset`、`columns`、`preview`、`query`、`pagination`、`uploadJobs`。列表查询以 URL 为真源，Store 缓存结果；切换用户或删除数据集时清理相关缓存。

## 分析工作区状态

首期由 `AnalysisWorkspaceView` 持有当前会话、消息、输入、同步提交状态、ToolCalls、真实结果和错误；会话与证据从服务端恢复，不写入浏览器持久存储。`/analysis/chat` 同步返回完成后的结果，首期没有流式执行、服务端取消或 `cancelled` 状态。请求中离开页面只会终止浏览器等待，不代表服务端停止；`request_id` 用于去重。

## uiStore

只保存全局 Toast 队列、侧栏折叠和全局 Dialog 引用；页面表单字段和 Tab 选择留在组件/URL，避免 Store 膨胀。

## 生命周期

退出登录清空全部业务 Store。进入不同 dataset/session 时停止旧页面更新，再替换上下文。失败保留问题和安全的执行证据，不保留密码、认证密钥和原始文件对象到持久存储。
