import axios from 'axios'

const client = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

client.interceptors.request.use((config) => {
  config.headers['X-Request-ID'] ||= crypto.randomUUID()
  return config
})

client.interceptors.response.use(
  (response) => response.data.data,
  (error) => {
    // 导航停止轮询属于取消，不应被重写成可重试网络错误。
    if (axios.isCancel(error) || error.code === 'ERR_CANCELED') throw error
    const body = error.response?.data
    if (error.response?.status === 401 && typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('datalens:auth-expired'))
    }
    const timedOut = ['ECONNABORTED', 'ETIMEDOUT'].includes(error.code)
    const appError = new Error(body?.data?.error_info?.reason || body?.message || (timedOut ? '接口请求等待超时，后台任务结果尚未确认。' : '无法连接服务，请检查网络与服务状态。'))
    appError.code = body?.code || (timedOut ? 'HTTP_REQUEST_TIMEOUT' : 'NETWORK_ERROR')
    appError.status = error.response?.status || 0
    appError.fieldErrors = body?.data?.field_errors || []
    appError.recordId = body?.data?.record_id
    appError.retryable = Boolean(body?.data?.retryable)
    appError.requestId = error.response?.headers?.['x-request-id'] || error.config?.headers?.['X-Request-ID']
    appError.info = body?.data?.error_info || {
      code: appError.code, reason_code: appError.code, reason: appError.message, stage: 'request',
      suggestion: appError.status ? '核对请求和资源状态后重试。' : '已有任务请重新连接确认状态；提交响应丢失时使用原请求编号确认，避免重复创建。',
      timeout_scope: timedOut ? 'http' : null, limit_seconds: timedOut ? (error.config?.timeout || 15000) / 1000 : null,
      request_id: appError.requestId, retryable: !appError.status || appError.status >= 500,
    }
    appError.retryable = Boolean(appError.info.retryable ?? appError.retryable)
    throw appError
  },
)

export default client
