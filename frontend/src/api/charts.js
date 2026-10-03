import client from './client'

export const chartsApi = {
  render(artifactId, payload = {}, config = {}) {
    return client.post(`/charts/${artifactId}/render`, payload, config)
  },
}
