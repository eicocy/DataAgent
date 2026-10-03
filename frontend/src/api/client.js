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
    const appError = new Error(body?.message || '服务暂时不可用')
    appError.code = body?.code || 'NETWORK_ERROR'
    appError.status = error.response?.status || 0
    appError.fieldErrors = body?.data?.field_errors || []
    appError.recordId = body?.data?.record_id
    appError.retryable = Boolean(body?.data?.retryable)
    appError.requestId = error.config?.headers?.['X-Request-ID']
    throw appError
  },
)

export default client
