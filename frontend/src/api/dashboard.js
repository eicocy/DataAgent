import client from './client'

export const dashboardApi = {
  summary() {
    return client.get('/dashboard/summary')
  },
}
