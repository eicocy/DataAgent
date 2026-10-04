import client from './client'

export const datasetApi = {
  versions(id, config = {}) { return client.get(`/datasets/${id}/versions`, config) },
  quality(id, versionId, config = {}) { return client.get(`/datasets/${id}/quality`, { params: { dataset_version_id: versionId }, ...config }) },
  transformPreview(id, payload, config = {}) { return client.post(`/datasets/${id}/transformations/preview`, payload, config) },
  transformConfirm(id, payload, config = {}) { return client.post(`/datasets/${id}/transformations`, payload, config) },
  transformStatus(id, execution, config = {}) { return client.get(`/datasets/${id}/transformations/${execution}`, config) },
  joinPreview(id, payload, config = {}) { return client.post(`/datasets/${id}/joins/preview`, payload, config) },
  joinConfirm(id, payload, config = {}) { return client.post(`/datasets/${id}/joins`, payload, config) },
  joinStatus(id, execution, config = {}) { return client.get(`/datasets/${id}/joins/${execution}`, config) },
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
