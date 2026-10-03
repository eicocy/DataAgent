import axios from 'axios'
import { expect, it } from 'vitest'
import client from '../src/api/client'
it('preserves Axios cancellation rather than exposing it as a retryable network failure', async () => {
  const cancelled = new axios.CanceledError('navigation changed')
  const rejectResponse = client.interceptors.response.handlers[0].rejected
  await expect(Promise.resolve().then(() => rejectResponse(cancelled))).rejects.toBe(cancelled)
})
