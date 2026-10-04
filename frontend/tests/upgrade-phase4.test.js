import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { workspaceApi } from '../src/api/workspace'
import { reportsApi } from '../src/api/reports'
import { useWorkspaceStore } from '../src/stores/workspace'
import MentionPicker from '../src/components/MentionPicker.vue'
import Workspace from '../src/views/AnalysisWorkspaceView.vue'
import { buildChartOption } from '../src/utils/chartOption'
vi.mock('../src/api/workspace', () => ({ workspaceApi: { restore: vi.fn(), select: vi.fn(), capabilities: vi.fn(), profiles: vi.fn() } }))
vi.mock('../src/api/reports', () => ({ reportsApi: { preview: vi.fn(), artifacts: vi.fn(), get: vi.fn() } }))

describe('Phase 4 workspace', () => {
 beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })
 it('ignores old session responses and restores the selected artifact', async () => {
  let resolve
  workspaceApi.restore.mockImplementationOnce(() => new Promise(r => { resolve = r })).mockResolvedValueOnce({ artifacts: { items: [{ id: 9, artifact_id: 9 }] }, selected_artifact_id: 8, selected_artifact: { id: 8, name: 'Older selection' }, reports: [] })
  reportsApi.preview.mockResolvedValue({ preview: { kind: 'text', content: 'new session' } })
  const store = useWorkspaceStore()
  const old = store.load(1); await store.load(2)
  resolve({ artifacts: { items: [{ id: 3 }] }, selected_artifact_id: 3 }); await old
  expect(store.sessionId).toBe(2); expect(store.selectedId).toBe(8)
  expect(store.items[0].id).toBe(9); expect(store.preview.content).toBe('new session')
  expect(store.selected.name).toBe('Older selection')
 })
 it('reports do not hide the last analysis', () => {
  const analysis = { record_id: 4, status: 'succeeded', report: { tables: [] } }
  const report = { record_id: 5, status: 'succeeded', report: { operation: 'create', report: { id: 7 } } }
  const computed = Workspace.computed.latestEvidence.call({ messages: [{ evidence: analysis }, { evidence: report }], restoredAnalysis: null })
  expect(computed).toBe(analysis)
 })
 it('serializes persisted selection so refresh restores the last click', async () => {
  let finishFirst
  workspaceApi.select.mockImplementationOnce(() => new Promise(r => { finishFirst = r })).mockResolvedValueOnce({})
  reportsApi.preview.mockResolvedValue({ preview: { kind: 'text', content: 'selected' } })
  const store = useWorkspaceStore(); store.sessionId = 1
  const first = store.select(7); await flushPromises()
  const second = store.select(8); await flushPromises()
  expect(workspaceApi.select).toHaveBeenCalledTimes(1)
  finishFirst({}); await Promise.all([first,second])
  expect(workspaceApi.select.mock.calls.map(args => args[1])).toEqual([7,8])
  expect(store.selectedId).toBe(8)
 })
 it('mentions emit structured IDs and exclude expired or code artifacts', async () => {
  const wrapper = mount(MentionPicker, { props: { items: [
   { id: 7, artifact_id: 7, type: 'table', status: 'READY', name: '数据表' },
   { id: 8, type: 'python', status: 'READY', name: '脚本' }, { id: 9, type: 'table', status: 'EXPIRED', name: '旧数据' }], modelValue: [] } })
  await wrapper.get('button').trigger('click')
  expect(wrapper.emitted('update:modelValue')[0][0]).toEqual([7])
  expect(wrapper.text()).not.toContain('脚本'); expect(wrapper.text()).not.toContain('旧数据')
 })
 it('shows forecast lower and upper bounds without changing numeric values', () => {
  const result = buildChartOption({ chart_type: 'line', series: [{ name: '预测', points: [{ x: '2026-01', y: 10, lower: -2, upper: 21 }] }] })
  expect(result.series.map(s => s.data[0])).toEqual([10, -2, 21])
 })
})
