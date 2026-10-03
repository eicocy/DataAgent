import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { analysisApi } from '../src/api/analysis'
import { historyApi } from '../src/api/history'
import HistoryDetailView from '../src/views/HistoryDetailView.vue'
import HistoryView from '../src/views/HistoryView.vue'
import SessionsView from '../src/views/SessionsView.vue'

vi.mock('../src/api/analysis', () => ({ analysisApi: { sessions: vi.fn(), removeSession: vi.fn() } }))
vi.mock('../src/api/history', () => ({ historyApi: { list: vi.fn(), detail: vi.fn() } }))

const commonStubs = {
  AppShell: { template: '<main><slot /></main>' },
  ElButton: { template: '<button><slot /></button>' },
  ElInput: { template: '<input />' },
  ElSelect: { template: '<select><slot /></select>' },
  ElOption: { template: '<option><slot /></option>' },
  ElTag: { template: '<span><slot /></span>' },
  ElIcon: { template: '<span><slot /></span>' },
  ElPagination: { template: '<nav></nav>' },
  ElDialog: { template: '<div><slot /><slot name="footer" /></div>' },
  ChartView: { template: '<div class="chart-stub"></div>' },
  ElTable: { template: '<div></div>' },
  ElTableColumn: { template: '<div></div>' },
}

describe('sessions and analysis history', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('opens a saved session with its dataset context', async () => {
    analysisApi.sessions.mockResolvedValue({ items: [{ id: 8, dataset_id: 3, dataset_name: 'sales.csv', title: '销售复盘', last_question: '地区趋势', message_count: 4, updated_at: '2026-09-26T08:00:00Z' }], total: 1 })
    const router = { push: vi.fn() }
    const wrapper = mount(SessionsView, { global: { mocks: { $router: router }, stubs: commonStubs, directives: { loading: {} } } })
    await flushPromises()

    expect(wrapper.text()).toContain('销售复盘')
    await wrapper.get('button.session-main').trigger('click')
    expect(router.push).toHaveBeenCalledWith({ name: 'analysis', params: { sessionId: 8 }, query: { datasetId: 3 } })
  })

  it('filters history results and opens the selected evidence record', async () => {
    historyApi.list.mockResolvedValue({ items: [{ id: 19, question: '总销售额', dataset_name: 'sales.csv', status: 'succeeded', primary_tool_name: 'aggregate_data', created_at: '2026-09-26T08:00:00Z' }], total: 1 })
    const router = { push: vi.fn() }
    const wrapper = mount(HistoryView, { global: { mocks: { $router: router }, stubs: commonStubs, directives: { loading: {} } } })
    await flushPromises()

    expect(wrapper.text()).toContain('aggregate_data')
    await wrapper.get('button.history-row').trigger('click')
    expect(router.push).toHaveBeenCalledWith({ name: 'history-detail', params: { recordId: 19 } })
  })

  it('re-runs a historical question in a new analysis session', async () => {
    historyApi.detail.mockResolvedValue({ id: 19, question: '按地区汇总销售额', dataset: { id: 3, original_name: 'sales.csv' }, tool_calls: [], tool_result: null, status: 'succeeded', created_at: '2026-09-26T08:00:00Z' })
    const router = { push: vi.fn() }
    const wrapper = mount(HistoryDetailView, { props: { recordId: '19' }, global: { mocks: { $router: router }, stubs: commonStubs } })
    await flushPromises()
    const retryButton = wrapper.findAll('button').find((button) => button.text().includes('再次分析'))
    await retryButton.trigger('click')

    expect(router.push).toHaveBeenCalledWith({ name: 'analysis', query: { datasetId: 3, question: '按地区汇总销售额', run: '1' } })
  })

  it('presents a report task as a saved report and returns to its owning session', async () => {
    historyApi.detail.mockResolvedValue({ id: 2, session_id: 8, intent_summary: 'REPORT_GENERATION',
      question: 'REPORT_CREATE: 数据分析报告', dataset: { id: 3, original_name: 'sales.xlsx' },
      tool_calls: [], status: 'succeeded', execution_time_ms: null, final_answer: '报告预览已生成。',
      created_at: '2026-10-03T07:20:00Z', report: { operation: 'create', report: { title: '数据分析报告', version: 1 } } })
    const router = { push: vi.fn() }
    const wrapper = mount(HistoryDetailView, { props: { recordId: '2' }, global: { mocks: { $router: router }, stubs: commonStubs } })
    await flushPromises()

    expect(wrapper.get('h1').text()).toBe('数据分析报告')
    expect(wrapper.text()).not.toContain('REPORT_CREATE')
    expect(wrapper.text()).not.toContain('— ms')
    expect(wrapper.text()).not.toContain('模型总结')
    expect(wrapper.text()).not.toContain('没有成功的 Tool 调用')
    expect(wrapper.get('.history-answer').text()).toContain('报告预览已生成。')
    const returnButton = wrapper.findAll('button').find(button => button.text().includes('返回会话'))
    await returnButton.trigger('click')
    expect(router.push).toHaveBeenCalledWith({ name: 'analysis', params: { sessionId: 8 }, query: { datasetId: 3 } })
    wrapper.unmount()
  })

  it('keeps a real analysis question intact and displays a measured zero duration', async () => {
    historyApi.detail.mockResolvedValue({ id: 19, question: '按地区汇总销售额', dataset: { id: 3, original_name: 'sales.csv' },
      tool_calls: [], status: 'succeeded', execution_time_ms: 0, final_answer: '华东销售额最高。', created_at: '2026-10-03T07:20:00Z' })
    const wrapper = mount(HistoryDetailView, { props: { recordId: '19' }, global: { mocks: { $router: { push: vi.fn() } }, stubs: commonStubs } })
    await flushPromises()
    expect(wrapper.get('h1').text()).toBe('按地区汇总销售额')
    expect(wrapper.get('.history-meta').text()).toContain('0 ms')
    expect(wrapper.get('.history-answer').text()).toContain('分析结论')
    expect(wrapper.get('.history-answer').text()).toContain('华东销售额最高。')
    wrapper.unmount()
  })
})
