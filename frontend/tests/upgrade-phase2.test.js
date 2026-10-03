import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { describe, it, expect, vi } from 'vitest'
import PromptComposer from '../src/components/PromptComposer.vue'
import AgentSteps from '../src/components/AgentSteps.vue'
import { useAnalysisStore } from '../src/stores/analysis'
import { analysisApi } from '../src/api/analysis'

vi.mock('../src/api/analysis', () => ({ analysisApi: { submit: vi.fn(async () => ({ record_id: 7 })) } }))

describe('workspace Phase 2 runtime options', () => {
  it('enables only advertised depth/model options and emits selected depth', async () => {
    const wrapper = mount(PromptComposer, { props: { capabilities: { depth_selection: true, depths: ['FAST', 'STANDARD', 'DEEP'], model_selection: true, models: [{ id: 'configured' }] } } })
    const depth = wrapper.get('select[aria-label="分析深度"]')
    expect(depth.attributes('disabled')).toBeUndefined()
    await depth.setValue('DEEP')
    expect(wrapper.emitted('option-change').at(-1)[0].depth).toBe('DEEP')
    wrapper.unmount()
  })
  it('keeps complete options for uncertain network retry and refresh', async () => {
    setActivePinia(createPinia())
    sessionStorage.clear()
    const store = useAnalysisStore()
    const options = { depth: 'DEEP', profile_ids: ['general-quality'], inputs: [{ alias: 'primary', dataset_id: 1 }] }
    await store.submit({ session_id: 2, dataset_id: 1, question: 'quality', ...options })
    store.restore(2)
    await store.submit({}, true)
    expect(analysisApi.submit.mock.calls.at(-1)[0]).toMatchObject(options)
    expect(JSON.parse(sessionStorage.getItem('datalens:analysis'))['2']).toMatchObject(options)
  })
  it('renders persisted v3 dependencies and input alias', () => {
    const wrapper = mount(AgentSteps, { props: { trace: { plan: { version: '3.0', steps: [{ step_id: 'a', tool_name: 'aggregate', input_alias: 'second', depends_on: ['inspect'], status: 'COMPLETED' }] } } } })
    expect(wrapper.text()).toContain('aggregate')
    expect(wrapper.text()).toContain('second')
    expect(wrapper.text()).toContain('inspect')
    wrapper.unmount()
  })
})
