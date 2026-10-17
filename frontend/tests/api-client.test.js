import axios from 'axios'
import { expect, it } from 'vitest'
import client from '../src/api/client'
it('distinguishes HTTP timeout and preserves structured diagnostics', () => {
  const reject = client.interceptors.response.handlers[0].rejected
  try { reject({ code: 'ECONNABORTED', config: { timeout: 15000, headers: { 'X-Request-ID': 'probe' } } }) }
  catch (error) { expect(error.code).toBe('HTTP_REQUEST_TIMEOUT'); expect(error.info.limit_seconds).toBe(15) }
  const info = { reason_code: 'PLAN_COLUMN_UNKNOWN', stage: 'planning', suggestion: '确认字段' }
  try { reject({ response: { status: 422, data: { code: 'PLAN_INVALID', message: '字段无效', data: { error_info: info } } }, config: {} }) }
  catch (error) { expect(error.info).toEqual(info) }
})
it('preserves Axios cancellation rather than exposing it as a retryable network failure', async () => {
  const cancelled = new axios.CanceledError('navigation changed')
  const rejectResponse = client.interceptors.response.handlers[0].rejected
  await expect(Promise.resolve().then(() => rejectResponse(cancelled))).rejects.toBe(cancelled)
})
it('uses the actionable reason when the HTTP envelope has only a generic message', () => {
  const reject = client.interceptors.response.handlers[0].rejected
  expect(() => reject({ response: { status: 422, data: { code: 'VALIDATION_ERROR', message: '请求参数不符合要求',
    data: { error_info: { reason: '缺少必填参数 dataset_id。', retryable: false } } } }, config: {} }))
    .toThrow('缺少必填参数 dataset_id。')
})
