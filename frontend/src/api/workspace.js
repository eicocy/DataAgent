import client from './client'

export const workspaceApi = {
  capabilities(config = {}) { return client.get('/workspace/capabilities', config) },
  profiles(params = {}, config = {}) { return client.get('/analysis/profiles', { params, ...config }) },
  restore(id, params = {}, config = {}) { return client.get(`/analysis/sessions/${id}/workspace`, { params, ...config }) },
  select(id, selectedId, config = {}) { return client.patch(`/analysis/sessions/${id}/workspace`, { selected_artifact_id: selectedId }, config) },
}
