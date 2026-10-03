import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { datasetApi } from '../src/api/datasets'
import DatasetUploadView from '../src/views/DatasetUploadView.vue'

vi.mock('../src/api/datasets', () => ({
  datasetApi: { inspectSheets: vi.fn(), list: vi.fn(), detail: vi.fn(), columns: vi.fn(), preview: vi.fn(), upload: vi.fn(), remove: vi.fn() },
}))

describe('dataset upload format selection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    datasetApi.inspectSheets.mockResolvedValue({ sheets: ['销售数据', '汇总'], default: '销售数据' })
  })

  function mountUpload() {
    return mount(DatasetUploadView, { global: {
      plugins: [createPinia()],
      mocks: { $router: { push: vi.fn(), replace: vi.fn() } },
      stubs: { AppShell: { template: '<main><slot /></main>' }, ElButton: { template: '<button><slot /></button>' },
        ElIcon: { template: '<span><slot /></span>' }, ElProgress: true, ElSelect: true, ElOption: true },
    } })
  }

  it('inspects XLSX sheets and keeps the first usable worksheet as the default', async () => {
    const wrapper = mountUpload()

    await wrapper.vm.chooseFile(new File(['workbook'], 'sales.xlsx'))

    expect(datasetApi.inspectSheets).toHaveBeenCalledOnce()
    expect(wrapper.vm.sheetNames).toEqual(['销售数据', '汇总'])
    expect(wrapper.vm.selectedSheet).toBe('销售数据')
  })

  it('accepts TSV, JSON and Parquet without requesting workbook inspection', async () => {
    const wrapper = mountUpload()

    for (const name of ['sales.tsv', 'sales.json', 'sales.parquet']) {
      await wrapper.vm.chooseFile(new File(['records'], name))
      await flushPromises()
      expect(wrapper.vm.selectedFile.name).toBe(name)
    }

    expect(datasetApi.inspectSheets).not.toHaveBeenCalled()
  })
})
