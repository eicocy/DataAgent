import client from './client'

export const historyApi = {
  list(params = {}, config = {}) { return client.get('/history', { params, ...config }) },
  detail(id, config = {}) { return client.get(`/history/${id}`, config) },
}
