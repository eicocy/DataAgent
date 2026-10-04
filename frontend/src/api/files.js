import client from './client'
export const filesApi = {
  list(params = {}, config = {}) { return client.get('/files', { params, ...config }) },
  detail(id, config = {}) { return client.get(`/files/${id}`, config) },
  extraction(id, candidate, params = {}, config = {}) { return client.get(`/files/${id}/extractions/${candidate}`, { params, ...config }) },
  confirm(id, candidate, payload, config = {}) { return client.post(`/files/${id}/extractions/${candidate}/datasets`, payload, config) },
  upload(file, { sessionId, sheetName, ...config } = {}) {
    const body = new FormData(); body.append('file', file)
    if (sessionId) body.append('session_id', sessionId)
    if (sheetName) body.append('sheet_name', sheetName)
    return client.post('/files/upload', body, { timeout: 120000, headers: { 'Content-Type': undefined }, ...config })
  },
}
