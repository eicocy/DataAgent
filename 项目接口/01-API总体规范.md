# API 总体规范

## 约定

- Base URL：`/api/v1`。
- Content-Type：JSON；上传使用 multipart/form-data。
- 认证：推荐 HttpOnly Cookie；若使用 Bearer，由安全设计统一决定。
- 时间：ISO 8601，例如 `2026-09-20T15:08:11+08:00`。
- ID：响应为整数；前端不得猜测资源归属。
- 分页：`page>=1`、`page_size in [10,20,50]`。

## 统一成功响应

```json
{"code":200,"message":"success","data":{}}
```

分页 data：

```json
{"items":[],"page":1,"page_size":10,"total":86,"pages":9}
```

## 统一错误响应

```json
{
  "code":"TOOL_VALIDATION_FAILED",
  "message":"分析参数引用了不存在的字段 revenue",
  "data":{"field_errors":[],"retryable":true,"request_id":"req_01"}
}
```

HTTP 状态表达协议层结果；`code` 表达稳定业务错误。不得把 Python/SQL 堆栈或模型原始错误直接返回。

