import { mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import ErrorInfoPanel from '../src/components/ErrorInfoPanel.vue'

describe('error diagnostics', () => {
  it('shows actionable title and measurements without expanding technical details', () => {
    const wrapper = mount(ErrorInfoPanel, { props: { info: { title: '图表数据过多',
      reason: '绘图来源包含 902 个数据点，上限 500 个。', suggestion: '先取全局前10组。',
      code: 'CHART_POINT_LIMIT_EXCEEDED', completed_steps: ['count', 'top10'] } } })
    expect(wrapper.get('.error-heading').text()).toContain('图表数据过多')
    expect(wrapper.get('[role="alert"]').text()).toContain('902')
    expect(wrapper.get('.error-suggestion').text()).toContain('如何处理：先取全局前10组')
    expect(wrapper.get('details').element.open).toBe(false)
    expect(wrapper.text()).not.toContain('未记录')
    expect(wrapper.text()).toContain('已完成 2 个步骤')
  })
  it('shows measured cause, threshold, preservation and delegates retry', async () => {
    const wrapper = mount(ErrorInfoPanel, { props: { info: { code: 'TASK_TIMEOUT', reason: '模型调用超时',
      suggestion: '稍后重试', stage: 'llm', limit_seconds: 90, stage_elapsed_seconds: 90.2,
      preserved_artifact_ids: [12], request_id: 'correlation' }, retryable: true } })
    expect(wrapper.text()).toContain('模型调用超时')
    expect(wrapper.text()).toContain('90.2 秒')
    expect(wrapper.text()).toContain('已保留 1 项成果')
    await wrapper.get('.retry-action').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })
  it('provides selectable safe diagnostics when clipboard fails', async () => {
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: vi.fn().mockRejectedValue(new Error()) } })
    const wrapper = mount(ErrorInfoPanel, { props: { info: { code: 'PLAN_INVALID', reason: '字段无效', secret: 'do-not-copy' } } })
    await wrapper.get('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.find('textarea').exists()).toBe(true))
    expect(wrapper.get('textarea').element.value).toContain('PLAN_INVALID')
    expect(wrapper.get('textarea').element.value).not.toContain('do-not-copy')
  })
})
