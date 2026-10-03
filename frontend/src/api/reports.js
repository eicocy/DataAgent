import client from './client'

export const reportsApi = {
  list(params = {}, config = {}) { return client.get('/reports', { params, ...config }) },
  get(id, params = {}, config = {}) { return client.get(`/reports/${id}`, { params, ...config }) },
  create(payload, config = {}) { return client.post('/reports', payload, config) },
  update(id, payload, config = {}) { return client.patch(`/reports/${id}`, payload, config) },
  export(id, version, format, config = {}) {
    return client.post(`/reports/${id}/versions/${version}/exports/${format}`, {}, config)
  },
  artifacts(params = {}, config = {}) { return client.get('/artifacts', { params, ...config }) },
  artifact(id, config = {}) { return client.get(`/artifacts/${id}`, config) },
  preview(id, params = {}, config = {}) { return client.get(`/artifacts/${id}/preview`, { params, ...config }) },
}
