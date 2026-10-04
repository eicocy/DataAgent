import { defineStore } from 'pinia'

import { authApi } from '../api/auth'
import { useDatasetStore } from './datasets'
import { useAnalysisStore } from './analysis'
import { useWorkspaceStore } from './workspace'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    authStatus: 'unknown',
    initialized: false,
  }),

  actions: {
    expireSession() {
      useDatasetStore().reset()
      useAnalysisStore().reset()
      useWorkspaceStore().reset()
      this.user = null; this.authStatus = 'anonymous'; this.initialized = true
    },
    async initialize() {
      if (this.initialized) return this.user
      this.authStatus = 'loading'
      try {
        this.user = await authApi.me()
        this.authStatus = 'authenticated'
      } catch {
        this.user = null
        this.authStatus = 'anonymous'
      } finally {
        this.initialized = true
      }
      return this.user
    },

    async login(credentials) {
      // JWT 只由 HttpOnly Cookie 保存，Pinia 只保存不含凭据的用户资料。
      useDatasetStore().reset()
      useAnalysisStore().reset()
      useWorkspaceStore().reset()
      const result = await authApi.login(credentials)
      this.user = result.user
      this.authStatus = 'authenticated'
      this.initialized = true
      return this.user
    },

    async register(details) {
      useDatasetStore().reset()
      useAnalysisStore().reset()
      useWorkspaceStore().reset()
      this.user = await authApi.register(details)
      this.authStatus = 'authenticated'
      this.initialized = true
      return this.user
    },

    async logout() {
      try {
        await authApi.logout()
      } finally {
        this.expireSession()
      }
    },
  },
})
