import client from './client'

export const authApi = {
  async register(payload) {
    return client.post('/auth/register', payload)
  },
  async login(payload) {
    const result = await client.post('/auth/login', payload)
    return result
  },
  async me() {
    return client.get('/auth/me')
  },
  async logout() {
    return client.post('/auth/logout')
  },
}
