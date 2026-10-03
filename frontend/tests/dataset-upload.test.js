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
  it('ignores an old workbook inspection after selecting a new file', async () => {
    let finish
    datasetApi.inspectSheets.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = mountUpload()
    const old = wrapper.vm.chooseFile(new File(['book'], 'old.xlsx'))
    await wrapper.vm.chooseFile(new File(['a\n1'], 'new.csv'))
    finish({ sheets: ['过期工作表'], default: '过期工作表' })
    await old
    expect(wrapper.vm.selectedFile.name).toBe('new.csv')
    expect(wrapper.vm.sheetNames).toEqual([])
    expect(wrapper.vm.inspectingSheets).toBe(false)
    wrapper.unmount()
  })
})
