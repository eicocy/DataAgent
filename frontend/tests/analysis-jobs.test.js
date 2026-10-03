import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, expect, it, vi } from 'vitest'
import { analysisApi } from '../src/api/analysis'
import { useAnalysisStore } from '../src/stores/analysis'
vi.mock('../src/api/analysis', () => ({ analysisApi: { submit: vi.fn(), run: vi.fn(), trace: vi.fn(), cancel: vi.fn() } }))
beforeEach(() => { setActivePinia(createPinia()); sessionStorage.clear(); vi.clearAllMocks() })
it('replays the same request after an uncertain submission and persists no results', async () => {
  const store = useAnalysisStore()
  analysisApi.submit.mockRejectedValueOnce(Object.assign(new Error('offline'), { code: 'NETWORK_ERROR' }))
  await expect(store.submit({ session_id: 5, dataset_id: 7, question: 'sales' })).rejects.toThrow('offline')
  const requestId = store.pending.request_id
  analysisApi.submit.mockResolvedValue({ record_id: 9, status: 'pending' })
  await store.submit({ session_id: 5, dataset_id: 7, question: 'sales' }, true)
  expect(analysisApi.submit.mock.calls[1][0].request_id).toBe(requestId)
  expect(JSON.parse(sessionStorage.getItem('datalens:analysis'))['5'].record_id).toBe(9)
  expect(sessionStorage.getItem('datalens:analysis')).not.toContain('answer')
})
it('restores a task only in its owning session and clears results on reset', () => {
  sessionStorage.setItem('datalens:analysis', JSON.stringify({ session_id: 5, dataset_id: 7, question: 'sales', request_id: 'a', record_id: 9 }))
  const store = useAnalysisStore()
  expect(store.restore(6)).toBeNull()
  expect(store.restore(5).record_id).toBe(9)
  store.reset()
  expect(sessionStorage.getItem('datalens:analysis')).toBeNull()
})
it('polls a completed task and clears only persisted submission metadata', async () => {
  const store = useAnalysisStore()
  store.pending = { session_id: 5, dataset_id: 7, question: 'sales', request_id: 'a', record_id: 9 }
  analysisApi.run.mockResolvedValue({ record_id: 9, status: 'partial', tool_result: { rows: [{ sales: 12 }] } })
  analysisApi.trace.mockResolvedValue({ steps: [{ status: 'failed', tool_name: 'generate_chart' }] })
  const result = await store.poll(new AbortController().signal)
  expect(result.tool_result.rows[0].sales).toBe(12)
  expect(store.trace.steps[0].status).toBe('failed')
  expect(store.pending).toBeNull()
  expect(sessionStorage.getItem('datalens:analysis')).toBeNull()
})
it('preserves two running sessions and restores A after a submission in B', async () => {
  const store = useAnalysisStore()
  analysisApi.submit.mockResolvedValueOnce({ record_id: 9, status: 'pending' }).mockResolvedValueOnce({ record_id: 10, status: 'pending' })
  await store.submit({ session_id: 5, dataset_id: 7, question: 'A' })
  await store.submit({ session_id: 6, dataset_id: 8, question: 'B' })
  expect(store.restore(5).record_id).toBe(9)
  expect(store.restore(6).record_id).toBe(10)
  expect(sessionStorage.getItem('datalens:analysis')).not.toContain('answer')
})
it('restores server running records even when client metadata was removed', () => {
  const store = useAnalysisStore()
  const messages = [{ role: 'user', content: 'A', analysis_record: { id: 9, request_id: 'original', status: 'running' } }]
  expect(store.restore(5, 7, messages)).toEqual({ session_id: 5, dataset_id: 7, question: 'A', record_id: 9, request_id: 'original' })
})
it('ignores a late poll response after switching to another session', async () => {
  const store = useAnalysisStore()
  analysisApi.submit.mockResolvedValueOnce({ record_id: 9, status: 'pending' }).mockResolvedValueOnce({ record_id: 10, status: 'pending' })
  await store.submit({ session_id: 5, dataset_id: 7, question: 'A' })
  let finish
  analysisApi.run.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  const controller = new AbortController()
  const polling = store.poll(controller.signal)
  controller.abort()
  await store.submit({ session_id: 6, dataset_id: 8, question: 'B' })
  finish({ record_id: 9, status: 'succeeded', answer: 'old A' })
  expect(await polling).toBeNull()
  expect(store.pending.record_id).toBe(10)
  expect(store.result.record_id).toBe(10)
  expect(analysisApi.trace).not.toHaveBeenCalled()
  expect(store.restore(5).record_id).toBe(9)
})
it('allows a dataset-free chat and treats clarification as terminal', async () => {
  const store = useAnalysisStore()
  analysisApi.submit.mockResolvedValue({ record_id: 12, status: 'pending' })
  await store.submit({ session_id: 5, dataset_id: null, question: '你好' })
  expect(store.pending.dataset_id).toBeNull()
  analysisApi.run.mockResolvedValue({ record_id: 12, status: 'waiting', answer: '请选择数据集' })
  analysisApi.trace.mockResolvedValue({ steps: [] })
  expect((await store.poll(new AbortController().signal)).status).toBe('waiting')
  expect(store.pending).toBeNull()
})
it('refreshes on a persisted SSE event and closes the stream at completion', async () => {
  const original = globalThis.EventSource
  let stream
  class FakeSource {
    constructor() { this.handlers = {}; this.closed = false; stream = this }
    addEventListener(name, handler) { this.handlers[name] = handler }
    close() { this.closed = true }
    emit(name) { this.handlers[name]?.({}) }
  }
  globalThis.EventSource = FakeSource
  try {
    const store = useAnalysisStore()
    store.pending = { session_id: 5, dataset_id: null, question: '你好', request_id: 'a', record_id: 12 }
    analysisApi.run.mockResolvedValueOnce({ record_id: 12, status: 'running' }).mockResolvedValueOnce({ record_id: 12, status: 'succeeded', answer: '你好' })
    analysisApi.trace.mockResolvedValue({ plan: null, steps: [] })
    const watching = store.watchRun(new AbortController().signal)
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve()
    stream.emit('response_ready')
    const result = await watching
    expect(result.answer).toBe('你好')
    expect(stream.closed).toBe(true)
    expect(store.pending).toBeNull()
  } finally { globalThis.EventSource = original }
})
it('sends cancellation for the active server run', async () => {
  const store = useAnalysisStore()
  store.pending = { session_id: 5, dataset_id: 7, question: 'sales', request_id: 'a', record_id: 9 }
  analysisApi.cancel.mockResolvedValue({ status: 'running' })
  await store.cancel()
  expect(analysisApi.cancel).toHaveBeenCalledWith(9)
})
