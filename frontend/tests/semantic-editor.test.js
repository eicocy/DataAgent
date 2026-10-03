import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import SemanticMappingEditor from '../src/components/SemanticMappingEditor.vue'
import { analysisApi } from '../src/api/analysis'
vi.mock('../src/api/analysis', () => ({ analysisApi: { semantics: vi.fn(), updateSemantics: vi.fn() } }))
describe('version scoped semantic correction', () => {
  it('loads suggestions and saves an explicit user correction without hiding errors', async () => {
    analysisApi.semantics.mockResolvedValue({ version: 1, mappings: [{ column: 'sales', concept: 'ambiguous_sales', role: 'metric', dataset_version_id: 7, source: 'candidate' }] })
    analysisApi.updateSemantics.mockRejectedValueOnce(new Error('保存失败')).mockResolvedValue({ version: 2 })
    const wrapper = mount(SemanticMappingEditor, { props: { sessionId: 1, datasetId: 2 } })
    await flushPromises()
    await wrapper.get('input[aria-label="sales 的业务含义"]').setValue('quantity')
    await wrapper.vm.save()
    expect(wrapper.text()).toContain('保存失败')
    await wrapper.vm.save()
    expect(analysisApi.updateSemantics).toHaveBeenLastCalledWith(1, { mappings: [expect.objectContaining({ column: 'sales', concept: 'quantity', dataset_version_id: 7 })] }, expect.any(Object))
    expect(wrapper.text()).toContain('已保存')
    wrapper.unmount()
  })
})
