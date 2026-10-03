# API 请求层设计

## 模块

`authApi`、`datasetApi`、`analysisApi`、`sessionApi`、`historyApi`。每个方法返回解包后的 `data`，但保留 request_id 供日志与错误展示。

## Axios client

- `baseURL=/api/v1`，JSON 超时与上传超时分开配置。
- 请求拦截只添加认证和 request_id，不改变业务参数。
- 响应拦截识别 `{code,message,data}`；401 进入单一重认证流程，避免并发重定向。
- AbortController 用于搜索、列表切换和分析取消。
- 错误转换为 `AppError { kind, code, message, fieldErrors, retryable, requestId }`。

## 错误归属

- 400/422 字段错误映射表单。
- 401 重新登录并返回原任务。
- 403 显示权限边界。
- 404 区分路由/资源。
- 409 用于状态冲突。
- 429 说明稍后重试。
- 5xx 保留输入，提供重试与 request_id，不展示堆栈。

