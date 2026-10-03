import client from './client'

export const analysisApi = {
  submit(payload, config = {}) { return client.post('/analysis/runs', payload, config) },
  run(id, config = {}) { return client.get(`/analysis/runs/${id}`, config) },
  trace(id, config = {}) { return client.get(`/analysis/runs/${id}/trace`, config) },
  cancel(id, config = {}) { return client.post(`/analysis/runs/${id}/cancel`, {}, config) },
  result(id, artifactId, params = {}, config = {}) { return client.get(`/analysis/runs/${id}/results/${artifactId}`, { params, ...config }) },
  createSession(payload, config = {}) { return client.post('/analysis/sessions', payload, config) },
  sessions(params = {}, config = {}) { return client.get('/analysis/sessions', { params, ...config }) },
  session(id, params = {}, config = {}) { return client.get(`/analysis/sessions/${id}`, { params, ...config }) },
  removeSession(id) { return client.delete(`/analysis/sessions/${id}`) },
  updateSession(id, payload, config = {}) { return client.patch(`/analysis/sessions/${id}`, payload, config) },
  chat(payload, config = {}) { return client.post('/analysis/chat', payload, { timeout: 120000, ...config }) },
}
