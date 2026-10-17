import { mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import ErrorInfoPanel from '../src/components/ErrorInfoPanel.vue'

describe('error diagnostics', () => {
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
