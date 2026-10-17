import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { defineComponent } from 'vue'
import PromptComposer from '../src/components/PromptComposer.vue'

const catalog = { categories: [{ id: 'general', name: '通用分析' }], items: [
  { id: 'quality', category: 'general', name: '数据质量检查', availability: 'available', example_questions: ['检查缺失值和重复记录。'] },
  { id: 'future', category: 'general', name: '规划中的模板', availability: 'planned', example_questions: [] },
] }
const capabilities = { profile_execution: true, depth_selection: true, depths: ['FAST', 'STANDARD', 'DEEP'],
  automatic_reports: true, report_templates: [{ id: 'general', name: '通用报告' }], model_selection: true,
  models: [{ id: 'test-model', configured: true }, { id: 'unavailable', configured: false }] }
const mounted = []
afterEach(() => { mounted.splice(0).forEach(w => w.unmount()); document.body.innerHTML = '' })
function fixture(props = {}) {
  const Host = defineComponent({ components: { PromptComposer }, data() { return { question: '', options: {}, busy: false } },
    template: '<PromptComposer v-model="question" :options="options" :busy="busy" :catalog="catalog" :capabilities="capabilities" @option-change="options = { ...options, ...$event }" />',
    computed: { catalog() { return catalog }, capabilities() { return props.capabilities || capabilities } },
  })
  const w = mount(Host, { attachTo: document.body }); mounted.push(w); return w
}
async function openSettings(w) {
  await w.get('.composer-settings-trigger').trigger('click')
  await flushPromises()
  return document.querySelector('.composer-settings-panel')
}
async function select(panel, label, value) {
  const el = panel.querySelector(`[aria-label="${label}"]`)
  el.value = value; el.dispatchEvent(new Event('change', { bubbles: true })); await flushPromises()
}

describe('compact composer settings', () => {
  it('keeps all options in a teleported panel and preserves immediate options on reopen', async () => {
    const w = fixture()
    expect(w.find('select').exists()).toBe(false)
    expect(w.get('.composer-summary').text()).toBe('自动 · 标准')
    const panel = await openSettings(w)
    expect(panel.closest('.prompt-composer')).toBeNull()
    await select(panel, '分析方向', 'general')
    await select(panel, '分析模板', 'quality')
    expect(w.vm.question).toBe('检查缺失值和重复记录。')
    expect(w.vm.options.profile_ids).toEqual(['quality'])
    await select(panel, '分析深度', 'DEEP')
    await select(panel, '报告类型', 'general')
    await select(panel, '模型', 'test-model')
    expect(w.vm.options).toEqual({ category: 'general', profile_ids: ['quality'], depth: 'DEEP', report_template: 'general',
      output_formats: ['xlsx', 'docx', 'pdf', 'python'], model_id: 'test-model' })
    expect(w.get('.composer-summary').text()).toBe('数据质量检查 · 深度')
    panel.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(w.get('.composer-settings-trigger').attributes('aria-expanded')).toBe('false')
    const reopened = await openSettings(w)
    expect(reopened.querySelector('[aria-label="模型"]').value).toBe('test-model')
    await select(reopened, '分析方向', '')
    expect(w.vm.options.profile_ids).toEqual([])
    expect(w.vm.question).toBe('检查缺失值和重复记录。')
  })
  it('closes and disables settings when analysis starts, and respects server capability gates', async () => {
    const w = fixture({ capabilities: {} })
    const panel = await openSettings(w)
    for (const label of ['分析深度', '报告类型', '模型']) expect(panel.querySelector(`[aria-label="${label}"]`).disabled).toBe(true)
    w.vm.busy = true; await flushPromises()
    expect(w.get('.composer-settings-trigger').attributes('aria-expanded')).toBe('false')
    expect(w.get('.composer-settings-trigger').attributes('disabled')).toBeDefined()
  })
})
