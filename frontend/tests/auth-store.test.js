import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { authApi } from '../src/api/auth'
import { useAuthStore } from '../src/stores/auth'

vi.mock('../src/api/auth', () => ({
  authApi: {
    login: vi.fn(),
    me: vi.fn(),
    logout: vi.fn(),
  },
}))

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('restores the public user after login without storing a token', async () => {
    authApi.login.mockResolvedValue({ user: { id: 7, username: 'alice', status: 'active' } })
    const store = useAuthStore()

    await store.login({ username: 'alice', password: 'safe-password' })

    expect(store.user).toEqual({ id: 7, username: 'alice', status: 'active' })
    expect(store.authStatus).toBe('authenticated')
    expect(Object.keys(store.$state)).not.toContain('token')
  })

  it('clears user state after logout', async () => {
    const store = useAuthStore()
    store.user = { id: 7, username: 'alice', status: 'active' }
    store.authStatus = 'authenticated'
    authApi.logout.mockResolvedValue({ logged_out: true })

    await store.logout()

    expect(store.user).toBeNull()
    expect(store.authStatus).toBe('anonymous')
  })
})
