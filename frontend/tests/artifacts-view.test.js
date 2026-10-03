import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { reportsApi } from '../src/api/reports'
import ArtifactsView from '../src/views/ArtifactsView.vue'

vi.mock('../src/api/reports', () => ({
  reportsApi: { artifacts: vi.fn(), preview: vi.fn() },
}))

describe('artifact library', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    reportsApi.artifacts.mockResolvedValue({ items: [{ artifact_id: 8, title: '分析报告', file_name: '报告.pdf',
      artifact_type: 'PDF', mime_type: 'application/pdf', size_bytes: 2048, status: 'READY', download_url: '/api/v1/artifacts/8/download' }], has_more: false })
    reportsApi.preview.mockResolvedValue({ preview: { kind: 'report_document', document: { title: '分析报告', sections: [{ section_id: 's1', title: '结论', narrative: '华南销售额最高。' }] } } })
  })

  it('lists owner artifacts and loads a document preview on selection', async () => {
    const wrapper = mount(ArtifactsView, { global: { stubs: { AppShell: { template: '<main><slot /></main>' },
      ElButton: { template: '<button><slot /></button>' }, ElTag: { template: '<span><slot /></span>' },
      ElDialog: { props: ['modelValue'], template: '<div v-if="modelValue"><slot /><slot name="footer" /></div>' } } } })
    await flushPromises()
    expect(wrapper.text()).toContain('报告.pdf')
    await wrapper.vm.openPreview(wrapper.vm.items[0])
    await flushPromises()
    expect(reportsApi.preview).toHaveBeenCalledWith(8, { limit: 100 })
    expect(wrapper.text()).toContain('华南销售额最高。')
    wrapper.unmount()
  })

  it('paginates without requesting past the final page', async () => {
    const wrapper = mount(ArtifactsView, { global: { stubs: { AppShell: true, ElButton: true, ElTag: true, ElDialog: true } } })
    await flushPromises()
    await wrapper.vm.nextPage()
    expect(reportsApi.artifacts).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
})
