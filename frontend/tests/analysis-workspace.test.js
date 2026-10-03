import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia } from 'pinia'

import { analysisApi } from '../src/api/analysis'
import { datasetApi } from '../src/api/datasets'
import AnalysisWorkspaceView from '../src/views/AnalysisWorkspaceView.vue'

vi.mock('../src/api/analysis', () => ({
  analysisApi: { createSession: vi.fn(), updateSession: vi.fn(), session: vi.fn(), submit: vi.fn(), run: vi.fn(), trace: vi.fn(), cancel: vi.fn() },
}))
vi.mock('../src/api/datasets', () => ({
  datasetApi: { detail: vi.fn(), list: vi.fn(), columns: vi.fn(), preview: vi.fn(), upload: vi.fn(), remove: vi.fn() },
}))
vi.mock('../src/api/workspace', () => ({ workspaceApi: { capabilities: vi.fn(async () => ({})), profiles: vi.fn(async () => ({ categories: [], items: [] })) } }))

describe('analysis workspace', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    analysisApi.submit.mockResolvedValue({ record_id: 9, status: 'pending' })
    analysisApi.trace.mockResolvedValue({ plan: null, steps: [] })
    datasetApi.detail.mockResolvedValue({ id: 7, original_name: 'sales.csv', row_count: 10, column_count: 3 })
    datasetApi.list.mockResolvedValue({ items: [{ id: 7, original_name: 'sales.csv' }] })
    analysisApi.session.mockResolvedValue({ dataset: { id: 7 }, messages: [] })
  })

  function mountWorkspace(route = { params: { sessionId: '5' }, query: { datasetId: '7' } }) {
    return mount(AnalysisWorkspaceView, {
      global: {
        plugins: [createPinia()],
        mocks: { $route: route, $router: { push: vi.fn(), replace: vi.fn() } },
        stubs: {
          AppShell: { template: '<main><slot /></main>' },
          ReportWorkbench: true,
          ChartView: { template: '<div class="chart-view-stub"></div>' },
          ElButton: { template: '<button><slot /></button>' },
          ElTag: { template: '<span><slot /></span>' },
          ElInput: { template: '<textarea><slot /></textarea>' },
          ElSelect: { template: '<select><slot /></select>' },
          ElOption: { template: '<option><slot /></option>' },
          ElIcon: { template: '<span><slot /></span>' },
          ElTable: { template: '<div></div>' },
          ElTableColumn: { template: '<div></div>' },
        },
      },
    })
  }

  it('does not create empty sessions on the landing page and creates once on send', async () => {
    analysisApi.createSession.mockResolvedValue({ id: 5 })
    analysisApi.run.mockResolvedValue({ record_id: 9, status: 'succeeded', answer: '你好', tool_calls: [] })
    const wrapper = mountWorkspace({ params: {}, query: {} })
    await flushPromises()
    expect(analysisApi.createSession).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Hey！今天想分析什么数据？')
    wrapper.vm.question = '你好'
    await wrapper.vm.submitQuestion()
    expect(analysisApi.createSession).toHaveBeenCalledTimes(1)
    expect(analysisApi.submit).toHaveBeenCalledWith(expect.objectContaining({ session_id: 5 }), expect.any(Object))
    wrapper.unmount()
  })
  it('resets upload busy state when replacing a workspace', async () => {
    const route = { params: { sessionId: '5' }, query: {} }
    const wrapper = mountWorkspace(route)
    await flushPromises()
    wrapper.vm.uploadBusy = true
    route.params.sessionId = '6'
    await wrapper.vm.initializeWorkspace()
    expect(wrapper.vm.sessionId).toBe(6)
    expect(wrapper.vm.uploadBusy).toBe(false)
    wrapper.unmount()
  })
  it('binds a selected owned dataset before exposing its semantic editor and preserves selection on binding failure', async () => {
    const wrapper = mountWorkspace({ params: { sessionId: '5' }, query: {} })
    await flushPromises()
    wrapper.vm.capabilities = { profile_execution: true }
    wrapper.vm.attachedDatasets = [{ id: 7, original_name: 'sales.csv' }]
    analysisApi.updateSession.mockResolvedValue({ id: 5 })
    datasetApi.detail.mockResolvedValue({ id: 8, original_name: 'other.csv' })
    await wrapper.vm.chooseDataset(8)
    expect(analysisApi.updateSession).toHaveBeenCalledWith(5, { attached_dataset_ids: [7, 8] }, expect.any(Object))
    expect(wrapper.vm.dataset.id).toBe(8)
    analysisApi.updateSession.mockRejectedValue(new Error('附件已满'))
    datasetApi.detail.mockResolvedValue({ id: 9, original_name: 'third.csv' })
    await wrapper.vm.chooseDataset(9)
    expect(wrapper.vm.dataset.id).toBe(8)
    expect(wrapper.vm.errorMessage).toContain('附件已满')
    wrapper.unmount()
  })
  it('serializes removal behind an in-flight addition and restores a removal control', async () => {
    let finish
    analysisApi.updateSession.mockImplementationOnce(() => new Promise(resolve => { finish = resolve })).mockResolvedValue({ id: 5 })
    const wrapper = mountWorkspace()
    await flushPromises()
    wrapper.vm.attachedDatasets = [{ id: 7, original_name: 'old.csv' }]
    const addition = wrapper.vm.attachDataset({ id: 8, original_name: 'new.csv' })
    await flushPromises()
    const removal = wrapper.vm.removeAttachment(7)
    await flushPromises()
    expect(analysisApi.updateSession).toHaveBeenCalledTimes(1)
    finish({ id: 5 })
    await Promise.all([addition, removal])
    expect(analysisApi.updateSession.mock.calls.map(call => call[1].attached_dataset_ids)).toEqual([[7, 8], [8]])
    expect(wrapper.vm.attachedDatasets.map(item => item.id)).toEqual([8])
    await flushPromises()
    expect(wrapper.find('button[aria-label="移除附件 new.csv"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('shows the answer and evidence returned by the background run API', async () => {
    analysisApi.run.mockResolvedValue({
      message_id: 12,
      status: 'succeeded',
      answer: 'East 销售额为 12。',
      execution_time: 0.42,
      tool_calls: [{ tool_call_id: 'tc_1', tool_name: 'group_by_analysis', status: 'succeeded', duration_ms: 8, parameters: { value_column: 'sales' }, result_summary: '返回 2 组' }],
      tool_result: { columns: ['region', 'sales_sum'], rows: [{ region: 'East', sales_sum: 12 }] },
    })
    const wrapper = mountWorkspace()
    await flushPromises()
    wrapper.vm.question = '按地区汇总销售额'

    await wrapper.vm.submitQuestion()
    await flushPromises()

    expect(analysisApi.submit).toHaveBeenCalledWith(expect.objectContaining({ session_id: 5, dataset_id: 7, question: '按地区汇总销售额' }), expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(wrapper.text()).toContain('East 销售额为 12。')
    expect(wrapper.text()).toContain('group_by_analysis')
    expect(wrapper.text()).toContain('返回 2 组')
  })

  it('keeps the real result visible when the API reports partial completion', async () => {
    analysisApi.run.mockResolvedValue({ status: 'partial', answer: null, summary_error: 'SUMMARY_UNAVAILABLE', execution_time: 0.1, tool_calls: [], tool_result: { metric_values: { sales_sum: 12 } } })
    const wrapper = mountWorkspace()
    await flushPromises()
    wrapper.vm.question = '总销售额'

    await wrapper.vm.submitQuestion()
    await flushPromises()

    expect(wrapper.text()).toContain('分析部分完成')
    expect(wrapper.text()).toContain('sales_sum')
    expect(wrapper.text()).toContain('12')
  })
  it('does not let an old submission clear a new workspace loading state', async () => {
    const wrapper = mountWorkspace()
    await flushPromises()
    let rejectOld
    analysisApi.submit.mockImplementationOnce(() => new Promise((resolve, reject) => { rejectOld = reject }))
    wrapper.vm.question = 'old question'
    const oldSubmission = wrapper.vm.submitQuestion()
    await flushPromises()
    wrapper.vm.controller.abort()
    wrapper.vm.controller = new AbortController()
    wrapper.vm.messages = []
    wrapper.vm.loading = true
    rejectOld(Object.assign(new Error('cancelled'), { code: 'ERR_CANCELED' }))
    await oldSubmission
    expect(wrapper.vm.loading).toBe(true)
    expect(wrapper.vm.messages).toEqual([])
    expect(wrapper.vm.errorMessage).toBe('')
    wrapper.unmount()
  })
  it('lets a conversation without a dataset send general chat', async () => {
    analysisApi.session.mockResolvedValue({ dataset: null, messages: [] })
    analysisApi.run.mockResolvedValue({ record_id: 9, message_id: 10, status: 'succeeded', answer: '你好', tool_calls: [] })
    const wrapper = mountWorkspace({ params: { sessionId: '5' }, query: {} })
    await flushPromises()
    expect(wrapper.text()).toContain('可先聊天')
    expect(datasetApi.detail).not.toHaveBeenCalled()
    wrapper.vm.question = '你好'
    await wrapper.vm.submitQuestion()
    expect(analysisApi.submit).toHaveBeenCalledWith(expect.objectContaining({ dataset_id: null, question: '你好' }), expect.any(Object))
    expect(wrapper.text()).toContain('你好')
  })
  it('shows dataset clarification choices once on the assistant response', async () => {
    analysisApi.run.mockResolvedValue({ record_id: 9, message_id: 10, status: 'waiting',
      answer: '请选择数据集', tool_calls: [],
      agent_response: { clarification: { candidate_dataset_ids: [7] } } })
    const wrapper = mountWorkspace()
    await flushPromises()
    wrapper.vm.question = '汇总销售额'
    await wrapper.vm.submitQuestion()
    await flushPromises()
    expect(wrapper.findAll('.clarification-choices')).toHaveLength(1)
    expect(wrapper.find('.message-assistant .clarification-choices').text()).toContain('选择 sales.csv')
    wrapper.unmount()
  })
  it('restores the latest waiting response from the durable run after refresh', async () => {
    analysisApi.session.mockResolvedValue({ dataset: null, messages: [
      { id: 10, role: 'assistant', content: '请选择数据集', status: 'waiting',
        analysis_record: { id: 9, status: 'waiting', tool_calls: [] } },
    ] })
    analysisApi.run.mockResolvedValue({ record_id: 9, status: 'waiting', tool_calls: [],
      agent_response: { clarification: { candidate_dataset_ids: [7] } } })
    const wrapper = mountWorkspace({ params: { sessionId: '5' }, query: {} })
    await flushPromises()
    expect(wrapper.findAll('.clarification-choices')).toHaveLength(1)
    expect(wrapper.text()).toContain('选择 sales.csv')
    wrapper.unmount()
  })
})
