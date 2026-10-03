import client from './client'

export const datasetApi = {
  list(params = {}, config = {}) { return client.get('/datasets', { params, ...config }) },
  detail(id, config = {}) { return client.get(`/datasets/${id}`, config) },
  columns(id, config = {}) { return client.get(`/datasets/${id}/columns`, config) },
  preview(id, params = {}, config = {}) { return client.get(`/datasets/${id}/preview`, { params, ...config }) },
  upload(file, config = {}) {
    const body = new FormData()
    body.append('file', file)
    return client.post('/datasets/upload', body, { timeout: 120000, headers: { 'Content-Type': undefined }, ...config })
  },
  remove(id) { return client.delete(`/datasets/${id}`) },
}
