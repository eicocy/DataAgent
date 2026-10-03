import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { reportsApi } from '../src/api/reports'
import { analysisApi } from '../src/api/analysis'
import ReportWorkbench from '../src/components/ReportWorkbench.vue'

vi.mock('../src/api/analysis', () => ({ analysisApi: { run: vi.fn() } }))

vi.mock('../src/api/reports', () => ({
  reportsApi: { create: vi.fn(), update: vi.fn(), export: vi.fn() },
}))

describe('report workbench', () => {
  beforeEach(() => { vi.clearAllMocks(); analysisApi.run.mockReset() })

  it('creates from the pinned run, saves immutable section edits, and exports the current version', async () => {
    reportsApi.create.mockResolvedValue({ record_id: 70 })
    analysisApi.run.mockResolvedValueOnce({ status: 'succeeded', report: { id: 12, version: 1, title: '销售报告', source_record_ids: [42],
      spec: { dataset_id: 7, dataset_version_id: 19, sections: [] },
      document: { title: '销售报告', sections: [{ section_id: 'summary', title: '执行摘要', narrative: '销售额 12', evidence_ids: ['42:step:fact'] }] } } })
    reportsApi.update.mockResolvedValue({ id: 12, version: 2, title: '修订报告', source_record_ids: [42],
      spec: { dataset_id: 7, dataset_version_id: 19, sections: [{ section_id: 'summary', title: '经营摘要' }] },
      document: { title: '修订报告', sections: [{ section_id: 'summary', title: '经营摘要', narrative: '销售额 12' }] } })
    reportsApi.export.mockResolvedValue({ record_id: 71 })
    analysisApi.run.mockResolvedValueOnce({ status: 'succeeded', report: { artifacts: [{ artifact_id: 88, file_name: '报告.pdf', size_bytes: 512, download_url: '/api/v1/artifacts/88/download' }] } })

    const wrapper = mount(ReportWorkbench, { props: { modelValue: false, sessionId: 5, source: {
      record_id: 42, dataset_id: 7, dataset_version_id: 19, status: 'succeeded',
    } }, global: { stubs: { ElDialog: { template: '<div><slot name="header"/><slot/><slot name="footer"/></div>' },
      ElButton: { template: '<button><slot /></button>' }, ElInput: { template: '<input />' }, ElTag: true } } })

    await wrapper.setProps({ modelValue: true })
    await flushPromises()
    expect(reportsApi.create).toHaveBeenCalledWith(expect.objectContaining({
      session_id: 5, source_record_ids: [42], spec: expect.objectContaining({ dataset_version_id: 19 }),
    }))
    expect(wrapper.text()).toContain('销售额 12')

    wrapper.vm.sections[0].title = '经营摘要'
    await wrapper.vm.saveReport()
    expect(reportsApi.update).toHaveBeenCalledWith(12, expect.objectContaining({
      source_record_ids: [42], spec: expect.objectContaining({ base_version: 1, title: '销售报告',
        sections: [expect.objectContaining({ title: '经营摘要' })] }),
    }))
    await wrapper.vm.exportReport('pdf')
    expect(reportsApi.export).toHaveBeenCalledWith(12, 2, 'pdf')
    expect(wrapper.vm.files[0].artifact_id).toBe(88)
  })
})
