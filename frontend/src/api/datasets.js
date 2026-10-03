import client from './client'

export const datasetApi = {
  list(params = {}, config = {}) { return client.get('/datasets', { params, ...config }) },
  detail(id, config = {}) { return client.get(`/datasets/${id}`, config) },
  columns(id, config = {}) { return client.get(`/datasets/${id}/columns`, config) },
  preview(id, params = {}, config = {}) { return client.get(`/datasets/${id}/preview`, { params, ...config }) },
  inspectSheets(file, config = {}) {
    const body = new FormData()
    body.append('file', file)
    return client.post('/datasets/inspect-sheets', body, { headers: { 'Content-Type': undefined }, ...config })
  },
  upload(file, sheetName = null, config = {}) {
    const body = new FormData()
    body.append('file', file)
    if (sheetName) body.append('sheet_name', sheetName)
    return client.post('/datasets/upload', body, { timeout: 120000, headers: { 'Content-Type': undefined }, ...config })
  },
  remove(id) { return client.delete(`/datasets/${id}`) },
}
