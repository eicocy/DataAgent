import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia } from 'pinia'

import { analysisApi } from '../src/api/analysis'
import { datasetApi } from '../src/api/datasets'
import { reportsApi } from '../src/api/reports'
import AnalysisWorkspaceView from '../src/views/AnalysisWorkspaceView.vue'

vi.mock('../src/api/analysis', () => ({
  analysisApi: { createSession: vi.fn(), updateSession: vi.fn(), session: vi.fn(), submit: vi.fn(), run: vi.fn(), trace: vi.fn(), cancel: vi.fn(), result: vi.fn() },
}))
vi.mock('../src/api/datasets', () => ({
  datasetApi: { detail: vi.fn(), list: vi.fn(), columns: vi.fn(), preview: vi.fn(), upload: vi.fn(), remove: vi.fn() },
}))
vi.mock('../src/api/workspace', () => ({ workspaceApi: { capabilities: vi.fn(async () => ({})), profiles: vi.fn(async () => ({ categories: [], items: [] })) } }))
vi.mock('../src/api/files', () => ({ filesApi: { list: vi.fn(async () => ({ items: [], total: 0 })) } }))
vi.mock('../src/api/reports', () => ({ reportsApi: { artifact: vi.fn(), preview: vi.fn() } }))

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
          ElPopover: { template: '<div><slot name="reference" /><slot /></div>' },
          ElDialog: { template: '<section><slot /></section>' },
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

  it('interrupts the accepted run once and waits for server cancellation before unlocking input', async () => {
    let finishRun
    analysisApi.run.mockImplementationOnce(() => new Promise(resolve => { finishRun = resolve }))
    analysisApi.cancel.mockResolvedValue({ record_id: 9, status: 'running' })
    const wrapper = mountWorkspace()
    await flushPromises()
    wrapper.vm.question = '统计电影总数'
    const submission = wrapper.vm.submitQuestion()
    await flushPromises()
    await wrapper.get('.composer-interrupt').trigger('click')
    await wrapper.vm.cancelTask()
    expect(analysisApi.cancel).toHaveBeenCalledTimes(1)
    expect(analysisApi.cancel).toHaveBeenCalledWith(9, expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(wrapper.vm.loading).toBe(true)
    expect(wrapper.get('.composer-interrupt').text()).toContain('正在中断')
    finishRun({ record_id: 9, status: 'cancelled', tool_calls: [], tool_result: { rows: [{ count: 9125 }] } })
    await submission
    expect(wrapper.vm.loading).toBe(false)
    expect(wrapper.find('.composer-interrupt').exists()).toBe(false)
    expect(wrapper.text()).toContain('任务已中断，已完成的结果仍可查看')
    wrapper.unmount()
  })

  it('does not cancel an unaccepted run or show late cancellation errors in another session', async () => {
    const wrapper = mountWorkspace()
    await flushPromises()
    wrapper.vm.loading = true
    await wrapper.vm.cancelTask()
    expect(analysisApi.cancel).not.toHaveBeenCalled()
    expect(wrapper.vm.cancelRequested).toBe(false)
    let rejectCancel
    analysisApi.cancel.mockImplementationOnce(() => new Promise((_, reject) => { rejectCancel = reject }))
    const { useAnalysisStore } = await import('../src/stores/analysis')
    useAnalysisStore().pending = { record_id: 9, session_id: 5 }
    const cancelling = wrapper.vm.cancelTask()
    wrapper.vm.controller.abort()
    wrapper.vm.controller = new AbortController()
    wrapper.vm.cancelRequested = false
    rejectCancel(new Error('old request failed'))
    await cancelling
    expect(wrapper.vm.errorMessage).toBe('')
    expect(wrapper.vm.cancelRequested).toBe(false)
    wrapper.unmount()
  })

  it('does not create empty sessions on the landing page and creates once on send', async () => {
    analysisApi.createSession.mockResolvedValue({ id: 5 })
    analysisApi.run.mockResolvedValue({ record_id: 9, status: 'succeeded', answer: '你好', tool_calls: [] })
    const wrapper = mountWorkspace({ params: {}, query: {} })
    await flushPromises()
    expect(analysisApi.createSession).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('想分析什么？')
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
    expect(wrapper.find('.conversation-empty').exists()).toBe(true)
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

  it('keeps old message preview, downloads and report creation bound to the original record', async () => {
    const original = { record_id: 4, dataset_id: 7, dataset_version_id: 11, status: 'succeeded' }
    const wrapper = mountWorkspace()
    await flushPromises()
    wrapper.vm.messages = [{ id: 2, role: 'assistant', evidence: { ...original, record_id: 99 } }]
    analysisApi.result.mockResolvedValue({ rows: [{ value: 'original-page' }], columns: ['value'] })
    await wrapper.vm.openPreview({ kind: 'table', evidence: original, value: { artifact_id: 31, rows: [] } })
    expect(analysisApi.result).toHaveBeenCalledWith(4, 31, { offset: 0, limit: 100 }, expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(wrapper.vm.previewEvidence().record_id).toBe(4)
    expect(wrapper.vm.previewEvidence().report.tables[0].rows[0].value).toBe('original-page')
    wrapper.vm.reportForMessage(original)
    expect(wrapper.vm.reportSource.record_id).toBe(4)
    analysisApi.run.mockResolvedValue({ record_id: 4, artifacts: [{ artifact_id: 31 }] })
    reportsApi.artifact.mockResolvedValue({ artifact_id: 31, name: '原成果', download_url: '/api/v1/artifacts/31/download' })
    await wrapper.vm.openMessageFiles(original)
    expect(analysisApi.run).toHaveBeenLastCalledWith(4, expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(wrapper.vm.previewFiles[0].download_url).toBe('/api/v1/artifacts/31/download')
    wrapper.unmount()
  })

  it('rejects late preview data on session replacement and restores a failure only on the assistant message', async () => {
    const record = { id: 4, status: 'failed', error_message: '字段不存在', error_info: { reason: '字段不存在：revenue' } }
    analysisApi.session.mockResolvedValue({ dataset: null, messages: [
      { id: 1, role: 'user', content: '统计 revenue', status: 'failed', analysis_record: record },
      { id: 2, role: 'assistant', content: '字段不存在', status: 'failed', analysis_record: record },
    ] })
    const wrapper = mountWorkspace({ params: { sessionId: '5' }, query: {} })
    await flushPromises()
    expect(wrapper.findAll('.error-info-panel')).toHaveLength(1)
    expect(wrapper.vm.artifactPanelOpen).toBe(false)
    let finish
    analysisApi.result.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const loading = wrapper.vm.openPreview({ kind: 'table', evidence: { record_id: 4 }, value: { artifact_id: 31 } })
    const signal = analysisApi.result.mock.calls.at(-1)[3].signal
    await wrapper.vm.initializeWorkspace()
    expect(signal.aborted).toBe(true)
    finish({ rows: [{ value: 'late' }] }); await loading
    expect(wrapper.vm.previewSelection).toBe(null)
    expect(wrapper.vm.artifactPanelOpen).toBe(false)
    wrapper.unmount()
  })

  it('reanalyzes an old reply with its question and fixed input version instead of the latest configuration', async () => {
    const wrapper = mountWorkspace()
    await flushPromises()
    wrapper.vm.capabilities = { profile_execution: true }
    const reply = { id: 2, role: 'assistant', evidence: { record_id: 4, dataset_id: 7, dataset_version_id: 11, request_options: { depth: 'FAST', profile_ids: ['original'], inputs: [{ alias: 'primary', dataset_id: 7, dataset_version_id: 11 }] } } }
    wrapper.vm.messages = [{ id: 1, role: 'user', content: '原问题' }, reply, { id: 3, role: 'user', content: '新问题' }]
    wrapper.vm.runOptions = { depth: 'DEEP', profile_ids: ['latest'] }
    analysisApi.run.mockResolvedValue({ record_id: 10, status: 'succeeded', answer: '重新完成', tool_calls: [] })
    await wrapper.vm.retryMessage(wrapper.vm.messages[1])
    expect(analysisApi.submit).toHaveBeenLastCalledWith(expect.objectContaining({ question: '原问题', depth: 'FAST', profile_ids: ['original'], inputs: [{ alias: 'primary', dataset_id: 7, dataset_version_id: 11 }] }), expect.any(Object))
    wrapper.unmount()
  })
})
