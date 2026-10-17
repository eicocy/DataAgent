import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import SafeMarkdown from '../src/components/SafeMarkdown.vue'
import AnalysisResult from '../src/components/AnalysisResult.vue'
import ChatMessage from '../src/components/ChatMessage.vue'
import LazyChart from '../src/components/LazyChart.vue'
import { chatResults } from '../src/utils/chatResults'
import { analysisApi } from '../src/api/analysis'

vi.mock('../src/api/analysis', () => ({ analysisApi: { result: vi.fn() } }))
const stubs = { ChartView: true, LazyChart: true, ElButton: { template: '<button><slot /></button>' } }
const table = (id, source, n = 20) => ({ artifact_id: id, source_ref: source, columns: ['name', 'count'], row_count: n, rows: Array.from({ length: n }, (_, i) => ({ name: `group-${id}-${i}`, count: i })) })
const chart = (id, source) => ({ artifact_id: id, source_ref: source, type: 'bar', series: [] })

describe('conversation result presentation', () => {
  it('renders Markdown while escaping HTML and blocking unsafe links and all automatic images', () => {
    const wrapper = mount(SafeMarkdown, { props: { content: '# 结果\n\n**金额**\n\n<script>alert(1)</script>\n\n[x](javascript:alert(1))\n\n![secret](https://example.com/track.png)\n\n[文档](https://example.com)\n\n| A | B |\n|---|---|\n| 1 | 2 |' } })
    expect(wrapper.find('h1').text()).toBe('结果')
    expect(wrapper.find('strong').text()).toBe('金额')
    expect(wrapper.find('table').exists()).toBe(true)
    expect(wrapper.findAll('script, img, iframe')).toHaveLength(0)
    expect(wrapper.findAll('a').map(a => a.attributes('href'))).toEqual(['https://example.com/track.png', 'https://example.com'])
    expect(wrapper.text()).toContain('<script>')
  })

  it('prioritizes expected outputs, deduplicates sources, and bounds the default to two charts and one table', async () => {
    const evidence = { record_id: 9, plan: { expected_outputs: ['answer', 'plot'] }, report: { tables: [table(1, 'intermediate'), table(2, 'answer'), table(2, 'answer')], charts: [chart(3, 'plot'), chart(4, 'answer'), chart(5, 'other')] } }
    const selected = chatResults(evidence)
    expect(selected.primary.filter(e => e.kind === 'table').map(e => e.source.artifact_id)).toEqual([2])
    expect(selected.primary.filter(e => e.kind === 'chart')).toHaveLength(2)
    expect(selected.more).toHaveLength(2)
    const wrapper = mount(AnalysisResult, { props: { evidence, presentation: 'chat' }, global: { stubs } })
    expect(wrapper.findAll('tbody tr')).toHaveLength(10)
    expect(wrapper.findAll('lazy-chart-stub')).toHaveLength(2)
    await wrapper.get('.more-results').trigger('click')
    expect(wrapper.findAll('lazy-chart-stub')).toHaveLength(3)
    wrapper.unmount()
  })

  it('uses a chart source table when expected outputs omit it, and only the first saved result for old records', () => {
    const evidence = { report: { tables: [table(1, 'filter'), table(2, 'groups')], charts: [chart(3, 'groups')] } }
    expect(chatResults(evidence).primary.find(e => e.kind === 'table').source.artifact_id).toBe(2)
    expect(chatResults({ report: { tables: [table(1), table(2)] } }).primary.map(e => e.source.artifact_id)).toEqual([1])
    expect(chatResults({ report: { tables: [table(2)], charts: [chart(1)] } }).primary[0].source.artifact_id).toBe(1)
    const oldChart = { artifact_id: 3, source_tool_call_id: 'call-2' }
    expect(chatResults({ report: { tables: [table(1, 'filter'), table(2, 'groups')], charts: [oldChart] }, tool_calls: [{ tool_call_id: 'call-2', step_id: 'groups' }] }).primary.find(entry => entry.kind === 'table').source.artifact_id).toBe(2)
  })

  it('keeps completed scalar metrics and legacy diagnostic fallback visible', () => {
    const chat = mount(ChatMessage, { props: { message: { role: 'assistant', content: '你好', evidence: { record_id: 8, status: 'succeeded' } } }, global: { stubs } })
    expect(chat.find('.result-evidence').exists()).toBe(false)
    expect(chat.find('.reply-details').exists()).toBe(false)
    chat.unmount()
    const wrapper = mount(ChatMessage, { props: { message: { role: 'assistant', content: '原文不改写', evidence: { status: 'partial', tool_result: { metric_values: { sales_sum: 12 } } } } }, global: { stubs } })
    expect(wrapper.text()).toContain('原文不改写')
    expect(wrapper.text()).toContain('sales_sum')
    expect(wrapper.text()).toContain('12')
    expect(wrapper.findAll('.completion-note')).toHaveLength(1)
    wrapper.unmount()
    const legacy = mount(ChatMessage, { props: { message: { role: 'assistant', evidence: { status: 'failed', error_message: '旧记录失败' } } }, global: { stubs } })
    expect(legacy.text()).toContain('旧记录失败')
    expect(legacy.text()).toContain('历史信息有限')
  })

  it('shows a failure once, keeps preserved data, and emits operations with its own record', async () => {
    const evidence = { record_id: 4, dataset_id: 7, dataset_version_id: 2, status: 'partial', error_message: '失败', error_info: { reason: '字段不存在：revenue', suggestion: '选择已有字段' }, report: { tables: [table(31, 'groups')] }, plan: { version: '3.0', steps: [{ step_id: 'bad', tool_name: 'aggregate', status: 'FAILED', error_info: { reason: '字段不存在：revenue' } }] } }
    const wrapper = mount(ChatMessage, { props: { message: { role: 'assistant', content: '失败', evidence } }, global: { stubs } })
    expect(wrapper.findAll('.error-info-panel')).toHaveLength(1)
    expect(wrapper.find('.markdown-body').exists()).toBe(false)
    expect(wrapper.findAll('tbody tr')).toHaveLength(10)
    await wrapper.get('.result-text-action').trigger('click')
    expect(wrapper.emitted('preview')[0][0].evidence.record_id).toBe(4)
    const button = label => wrapper.findAll('button').find(button => button.text() === label)
    await button('生成报告').trigger('click')
    expect(wrapper.emitted('report')[0][0].record_id).toBe(4)
    await button('下载').trigger('click')
    expect(wrapper.emitted('files')[0][0].record_id).toBe(4)
    wrapper.unmount()
  })

  it('pages using the original record and rejects a response after changing evidence', async () => {
    let finish
    analysisApi.result.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const original = { record_id: 4, report: { tables: [table(31, 'groups', 150)] } }
    const wrapper = mount(AnalysisResult, { props: { evidence: original }, global: { stubs } })
    const paging = wrapper.vm.page(original.report.tables[0], 100)
    const signal = analysisApi.result.mock.calls.at(-1)[3].signal
    expect(analysisApi.result).toHaveBeenCalledWith(4, 31, { offset: 100, limit: 100 }, { signal })
    await wrapper.setProps({ evidence: { record_id: 99, report: { tables: [table(55, 'new')] } } })
    expect(signal.aborted).toBe(true)
    finish({ rows: [{ name: 'late result' }], offset: 100 })
    await paging
    expect(wrapper.text()).not.toContain('late result')
    wrapper.unmount()
  })

  it('mounts a chart only near the viewport and disconnects observation on cleanup', async () => {
    let notify
    const disconnect = vi.fn(), observe = vi.fn()
    vi.stubGlobal('IntersectionObserver', class { constructor(callback) { notify = callback } observe = observe; disconnect = disconnect })
    const wrapper = mount(LazyChart, { props: { spec: chart(8, 'groups') }, global: { stubs: { ChartView: true } } })
    expect(wrapper.find('chart-view-stub').exists()).toBe(false)
    notify([{ isIntersecting: true }]); await flushPromises()
    expect(wrapper.find('chart-view-stub').exists()).toBe(true)
    wrapper.unmount(); expect(disconnect).toHaveBeenCalled()
    vi.unstubAllGlobals()
  })
})
