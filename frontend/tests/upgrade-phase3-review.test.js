import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia } from 'pinia'
import AnalysisResult from '../src/components/AnalysisResult.vue'
import DataQualityWorkbench from '../src/components/DataQualityWorkbench.vue'
import JoinWorkbench from '../src/components/JoinWorkbench.vue'
import DatasetDetailView from '../src/views/DatasetDetailView.vue'
import { datasetApi } from '../src/api/datasets'
vi.mock('../src/api/datasets', () => ({ datasetApi: { list: vi.fn(), versions: vi.fn(), detail: vi.fn(), columns: vi.fn(), preview: vi.fn(), joinPreview: vi.fn() } }))
const button = { props: ['disabled', 'loading'], template: '<button :disabled="disabled || loading"><slot /></button>' }
const global = { stubs: { ElButton: button, ChartView: true } }
// Fixtures reproduce result_tables.py's bounded normalized output; call records expose summaries only.
const normalizedKpi = { kind: 'kpi', currency: 'CNY', unit: '元', limitations: [], source_ref: 'kpi_step', artifact_id: 80, columns: ['metric','value','status','explanation'], rows: [{ metric: 'revenue', value: '9007199254740993.12', status: 'valid', explanation: null }], row_count: 1, truncated: false }
const rawKpi = { kind: 'kpi', dataset_id: 7, dataset_version: 11, source_ref: 'primary', currency: 'CNY', unit: '元', limitations: [], metrics: { revenue: { value: '9007199254740993.12', status: 'valid', explanation: null } }, row_count: 3 }
const normalizedForecast = { kind: 'forecast', currency: null, unit: null, unit_status: 'unconfirmed', limitations: ['短历史'], columns: ['time','value','lower','upper'], rows: [{ time: '2025-01-01', value: 12, lower: 9, upper: 15 }], row_count: 1, truncated: false, source_ref: 'forecast_step' }
const normalizedQuality = { kind: 'quality_score', rule_version: 'quality-score-v1', score: 90, columns: ['issue','column','count','penalty','severity','suggestion'], rows: [{ issue: 'missing', column: 'amount', count: 2, penalty: 10, severity: 'warning', suggestion: '核对源数据' }], row_count: 1, truncated: false, source_ref: 'quality_step' }

describe('Phase 3 review regressions', () => {
 beforeEach(() => { vi.clearAllMocks(); datasetApi.list.mockResolvedValue({ items: [], total: 0 }); datasetApi.versions.mockResolvedValue([]) })
 it('renders one complete raw KPI instead of raw plus normalized duplicate panels', () => {
  const wrapper = mount(AnalysisResult, { global, props: { evidence: { tool_result: rawKpi, tool_calls: [{ step_id: 'kpi_step', artifact_id: 80, status: 'succeeded', tool_name: 'calculate_kpi', result_summary: '计算完成' }], report: { tables: [normalizedKpi] } } } })
  expect(wrapper.findAll('[aria-label="业务指标结果"]')).toHaveLength(1)
  expect(wrapper.text().match(/9007199254740993\.12/g)).toHaveLength(1)
 })
 it('renders actual normalized-only rows with an honest missing-detail notice, never fake typed panels', () => {
  const wrapper = mount(AnalysisResult, { global, props: { evidence: { tool_calls: [{ status: 'succeeded', result_summary: '计算成功' }], report: { tables: [normalizedKpi, normalizedForecast, normalizedQuality] } } } })
  expect(wrapper.findAll('[aria-label="业务指标结果"], [aria-label="预测结果"], [aria-label="数据质量"]')).toHaveLength(0)
  expect(wrapper.text()).toContain('9007199254740993.12'); expect(wrapper.text()).toContain('2025-01-01'); expect(wrapper.text()).toContain('核对源数据')
  expect(wrapper.text()).toContain('当前仅提供结果表'); expect(wrapper.text()).not.toContain('未发现当前规则覆盖的问题')
 })
 it('pairs composite keys explicitly despite reverse schema order', async () => {
  const wrapper = mount(JoinWorkbench, { global, props: { datasetId: 7, versionId: 11, columns: ['customer', 'region'] } }); await flushPromises()
  wrapper.vm.rightId = 8; await flushPromises()
  wrapper.vm.versions = [{ id: 21, schema: { columns: [{ name: 'region' }, { name: 'customer' }] } }]
  wrapper.vm.rightVersion = 21; await flushPromises()
  await wrapper.get('select[aria-label="键对 1 左表字段"]').setValue('customer')
  await wrapper.get('select[aria-label="键对 1 右表字段"]').setValue('customer')
  await wrapper.vm.addPair()
  await wrapper.get('select[aria-label="键对 2 左表字段"]').setValue('region')
  await wrapper.get('select[aria-label="键对 2 右表字段"]').setValue('region')
  wrapper.vm.how = 'left'; wrapper.vm.relationship = 'many_to_one'; await flushPromises()
  expect(wrapper.vm.payload.left_on).toEqual(['customer','region']); expect(wrapper.vm.payload.right_on).toEqual(['customer','region'])
  expect(wrapper.text()).toContain('customer → customer'); expect(wrapper.text()).toContain('region → region')
 })
 it('hides old preview rows while another version is slow and keeps them hidden after failure', async () => {
  const schema = { columns: [{ name: 'amount' }] }
  datasetApi.detail.mockResolvedValue({ id: 7, status: 'ready', current_version_id: 11, original_name: 'data.csv' })
  datasetApi.versions.mockResolvedValue([{ id: 11, version_number: 1, schema }, { id: 12, version_number: 2, schema }]); datasetApi.columns.mockResolvedValue([])
  datasetApi.preview.mockResolvedValue({ columns: ['amount'], rows: [{ amount: 'old-row' }], total_rows: 1 })
  const wrapper = mount(DatasetDetailView, { props: { datasetId: '7' }, global: { ...global, plugins: [createPinia()], mocks: { $router: {} }, stubs: { ...global.stubs, AppShell: { template: '<main><slot /></main>' }, ElTable: { props: ['data'], template: '<div data-table-rows>{{ data }}</div>' }, ElTableColumn: true, ElIcon: true } } }); await flushPromises()
  expect(wrapper.text()).toContain('old-row')
  let reject; datasetApi.preview.mockImplementation(() => new Promise((resolve, r) => { reject = r }))
  wrapper.vm.selectedVersion = 12; await flushPromises()
  expect(wrapper.text()).not.toContain('old-row'); expect(wrapper.text()).toContain('正在读取版本预览')
  reject(new Error('历史版本读取失败')); await flushPromises()
  expect(wrapper.text()).not.toContain('old-row'); expect(wrapper.text()).toContain('历史版本读取失败')
  wrapper.unmount()
 })
 it('shows supplied legacy quality rates, statuses and outlier bounds without invented score/severity', () => {
  const result = { kind: 'quality', check: 'outlier_detection', findings: [{ column: 'amount', count: 2, rate: 0.25, row_refs: [2,4], lower: -1.5, upper: 9.5, status: 'valid' }, { column: 'empty', count: 0, rate: 0, row_refs: [], lower: null, upper: null, status: 'empty' }] }
  const wrapper = mount(DataQualityWorkbench, { global, props: { result } })
  expect(wrapper.text()).toContain('25%'); expect(wrapper.text()).toContain('valid'); expect(wrapper.text()).toContain('-1.5'); expect(wrapper.text()).toContain('9.5')
  expect(wrapper.text()).not.toContain('评分'); expect(wrapper.text()).not.toContain('空数据，评分未定义'); expect(wrapper.text()).not.toContain('警告')
 })
 it('prefers raw forecast/score by producing step, retaining unrelated table-only results', () => {
  const metrics = { mae: 1, rmse: 2, mape: null, mape_coverage: 0, mape_explanation: '零值未参与' }
  const raw = { kind: 'forecast', source_ref: 'primary', history_start: '2024-01-01', history_end: '2024-12-01', observation_count: 12, horizon: 1, selected_model: 'naive', aggregation: 'sum', granularity: 'month', metrics, baseline: { metrics }, points: normalizedForecast.rows, folds: [], candidates: [], uncertainty: { residual_count: 3, limitations: '未校准' }, limitations: [] }
  const wrapper = mount(AnalysisResult, { global, props: { evidence: { tool_result: raw, tool_calls: [{ step_id: 'forecast_step', status: 'succeeded', tool_name: 'forecast_data', result_summary: '成功' }], report: { tables: [normalizedForecast, normalizedKpi] } } } })
  expect(wrapper.findAll('[aria-label="预测结果"]')).toHaveLength(1)
  expect(wrapper.text().match(/2025-01-01/g)).toHaveLength(1)
  expect(wrapper.text()).toContain('9007199254740993.12')
  const score = { kind: 'quality_score', status: 'valid', rule_version: 'quality-score-v1', score: 90, row_count: 200, findings: [{ ...normalizedQuality.rows[0], row_refs: [3] }], configured_rules: {}, key_candidates: [], explanation: '真实规则解释' }
  const scored = mount(AnalysisResult, { global, props: { evidence: { tool_result: score, tool_calls: [{ step_id: 'quality_step', status: 'succeeded', tool_name: 'data_quality_score', result_summary: '成功' }], report: { tables: [normalizedQuality] } } } })
  expect(scored.findAll('[aria-label="数据质量"]')).toHaveLength(1)
  expect(scored.text()).toContain('200 行'); expect(scored.text()).toContain('真实规则解释')
 })
 it('does not describe normalized empty score rows as an empty dataset or no quality issues', () => {
  const wrapper = mount(AnalysisResult, { global, props: { evidence: { report: { tables: [{ ...normalizedQuality, rows: [], row_count: 0 }] } } } })
  expect(wrapper.text()).toContain('不能据此判断原数据是否为空')
  expect(wrapper.text()).not.toContain('空数据，评分未定义'); expect(wrapper.text()).not.toContain('未发现当前规则覆盖的问题')
 })
 it('ignores a slow superseded version after the newly selected version loads successfully', async () => {
  const schema = { columns: [{ name: 'amount' }] }
  datasetApi.detail.mockResolvedValue({ id: 7, status: 'ready', current_version_id: 11, original_name: 'data.csv' })
  datasetApi.versions.mockResolvedValue([{ id: 11, version_number: 1, schema }, { id: 12, version_number: 2, schema }])
  datasetApi.columns.mockResolvedValue([])
  let resolveOld
  datasetApi.preview.mockImplementation((id, params) => params.dataset_version_id === 12
    ? new Promise(resolve => { resolveOld = resolve })
    : Promise.resolve({ columns: ['amount'], rows: [{ amount: 'current-11' }], total_rows: 1 }))
  const wrapper = mount(DatasetDetailView, { props: { datasetId: '7' }, global: { ...global, plugins: [createPinia()], mocks: { $router: {} }, stubs: { ...global.stubs, AppShell: { template: '<main><slot /></main>' }, ElTable: { props: ['data'], template: '<div>{{ data }}</div>' }, ElTableColumn: true, ElIcon: true } } })
  await flushPromises()
  wrapper.vm.selectedVersion = 12; await flushPromises()
  wrapper.vm.selectedVersion = 11; await flushPromises()
  expect(wrapper.text()).toContain('current-11')
  resolveOld({ columns: ['amount'], rows: [{ amount: 'superseded-12' }], total_rows: 20 }); await flushPromises()
  expect(wrapper.text()).not.toContain('superseded-12'); expect(wrapper.vm.loadedPreviewVersion).toBe(11)
  wrapper.unmount()
 })
})
