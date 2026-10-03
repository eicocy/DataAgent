import { createPinia, setActivePinia } from 'pinia'
import { expect, it } from 'vitest'
import { useAuthStore } from '../src/stores/auth'
import { useDatasetStore } from '../src/stores/datasets'
import { useAnalysisStore } from '../src/stores/analysis'
it('expires authentication and clears data before a login redirect', () => {
  setActivePinia(createPinia())
  const auth = useAuthStore()
  auth.user = { id: 1 }; auth.authStatus = 'authenticated'
  useDatasetStore().items = [{ id: 7 }]
  useAnalysisStore().result = { answer: 'private' }
  auth.expireSession()
  expect(auth.authStatus).toBe('anonymous')
  expect(auth.user).toBeNull()
  expect(useDatasetStore().items).toEqual([])
  expect(useAnalysisStore().result).toBeNull()
})
