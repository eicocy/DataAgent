import client from './client'

export const workspaceApi = {
  capabilities(config = {}) { return client.get('/workspace/capabilities', config) },
  profiles(params = {}, config = {}) { return client.get('/analysis/profiles', { params, ...config }) },
}
