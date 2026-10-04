import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import DocumentCandidatePreview from '../src/components/DocumentCandidatePreview.vue'
import CleaningWorkbench from '../src/components/CleaningWorkbench.vue'
import BusinessResult from '../src/components/BusinessResult.vue'
import ForecastResult from '../src/components/ForecastResult.vue'
import { filesApi } from '../src/api/files'
import { datasetApi } from '../src/api/datasets'
import { useDatasetStore } from '../src/stores/datasets'
import { createPinia, setActivePinia } from 'pinia'
import { ElMessageBox } from 'element-plus'
import { percentText } from '../src/utils/exactDecimal'
vi.mock('../src/api/files', () => ({ filesApi: { upload: vi.fn(), detail: vi.fn(), extraction: vi.fn(), confirm: vi.fn() } }))
vi.mock('../src/api/datasets', () => ({ datasetApi: { transformPreview: vi.fn(), transformConfirm: vi.fn(), transformStatus: vi.fn() } }))
const options = { global: { stubs: { ElButton: { template: '<button :disabled="disabled || loading"><slot /></button>', props: ['disabled', 'loading'] }, ChartView: true } } }
describe('Phase 3 controlled workflows', () => {
 it('resumes an accepted document after a transient polling failure without uploading twice', async () => {
  setActivePinia(createPinia()); let acceptedId
  filesApi.upload.mockResolvedValue({ file: { id: 40 } })
  filesApi.detail.mockRejectedValueOnce(new Error('网络中断')).mockResolvedValueOnce({ id: 40, status: 'ready' })
  const store = useDatasetStore()
  await expect(store.uploadDocument(new File(['文本'], 'note.txt'), { onAccepted: item => { acceptedId = item.id } })).rejects.toThrow('网络中断')
  expect(acceptedId).toBe(40)
  await expect(store.uploadDocument(null, { fileId: acceptedId })).resolves.toMatchObject({ id: 40 })
  expect(filesApi.upload).toHaveBeenCalledTimes(1)
 })
 it('blocks duplicate publication and preserves confirmation ID through uncertain submit retry', async () => {
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
  const wrapper = mount(CleaningWorkbench, { ...options, props: { datasetId: 7, versionId: 11, columns: ['amount'] } })
  wrapper.vm.steps = [{ tool: 'remove_duplicates', columns: ['amount'], keep: 'first' }]; await flushPromises()
  wrapper.vm.preview = { preview_hash: 'a'.repeat(64), before: {}, after: {}, result: {} }; wrapper.vm.requestId = 'same-id'
  let reject; datasetApi.transformConfirm.mockImplementationOnce(() => new Promise((resolve, r) => { reject = r }))
  const pending = wrapper.vm.saveVersion(); await flushPromises(); await wrapper.vm.saveVersion()
  expect(datasetApi.transformConfirm).toHaveBeenCalledTimes(1); reject(new Error('网络中断')); await pending
  datasetApi.transformConfirm.mockResolvedValueOnce({ execution_id: 31 }); datasetApi.transformStatus.mockResolvedValue({ status: 'succeeded', output_version: { id: 12, version_number: 2 } })
  await wrapper.vm.saveVersion()
  expect(datasetApi.transformConfirm.mock.calls[0][1]).toEqual(datasetApi.transformConfirm.mock.calls[1][1])
  expect(wrapper.emitted('published')[0][0].id).toBe(12)
  wrapper.unmount()
 })
 it('converts decimal ratios to exact percentages using decimal text positions', () => {
  expect(percentText('0.123456789123456789')).toBe('12.3456789123456789%')
  expect(percentText('-0.0001')).toBe('-0.01%'); expect(percentText(null)).toBeNull()
 })
 it('document needs verification and retries reuse the accepted payload', async () => {
  filesApi.detail.mockResolvedValue({ id: 4, status: 'ready', preview: '原文', candidates: [{ id: 'c1', location: { page: 2 }, row_count: 3 }] })
  filesApi.extraction.mockResolvedValue({ rows: [['金额'], ['1']], columns: ['column_1'], total: 3 })
  filesApi.confirm.mockRejectedValueOnce(new Error('网络中断')).mockResolvedValueOnce({ dataset: { id: 7 } })
  const wrapper = mount(DocumentCandidatePreview, { ...options, props: { fileId: 4 } }); await flushPromises()
  expect(wrapper.find('[data-confirm-document]').attributes('disabled')).toBeDefined()
  await wrapper.find('input[data-verification]').setValue(true)
  await wrapper.vm.confirm(); await wrapper.vm.confirm()
  expect(filesApi.confirm.mock.calls[0][2]).toEqual(filesApi.confirm.mock.calls[1][2])
  expect(wrapper.emitted('ready')[0][0].id).toBe(7)
 })
 it('invalidates cleaning preview and ignores superseded response', async () => {
  let resolve; datasetApi.transformPreview.mockImplementation(() => new Promise(r => { resolve = r }))
  const wrapper = mount(CleaningWorkbench, { ...options, props: { datasetId: 7, versionId: 11, columns: ['amount'] } })
  wrapper.vm.steps = [{ tool: 'remove_duplicates', columns: ['amount'], keep: 'first' }]
  const pending = wrapper.vm.previewChanges(); await flushPromises()
  wrapper.vm.steps[0].keep = 'last'; await flushPromises()
  resolve({ preview_hash: 'old', result: {}, before: {}, after: {} }); await pending
  expect(wrapper.vm.preview).toBeNull()
 })
 it('renders exact decimals and undefined reasons', () => {
  const wrapper = mount(BusinessResult, { ...options, props: { result: { kind: 'kpi', currency: 'CNY', unit: '元', metrics: { revenue: { value: '9007199254740993.12345678', status: 'valid' }, margin: { value: null, explanation: '分母为零' } }, limitations: [] } } })
  expect(wrapper.text()).toContain('9007199254740993.12345678'); expect(wrapper.text()).toContain('分母为零')
 })
 it('shows zero-target MAPE coverage and honest uncertainty', () => {
  const metrics = { mae: 1, rmse: 2, mape: null, mape_coverage: 0, mape_explanation: '目标全为零' }
  const wrapper = mount(ForecastResult, { ...options, props: { result: { kind: 'forecast', baseline: { metrics }, metrics, folds: [], candidates: [], points: [], limitations: [], uncertainty: { limitations: '样本有限' } } } })
  expect(wrapper.text()).toContain('目标全为零'); expect(wrapper.text()).toContain('经验误差范围，未经校准')
 })
})
