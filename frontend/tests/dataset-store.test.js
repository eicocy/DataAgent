import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { datasetApi } from '../src/api/datasets'
import { useDatasetStore } from '../src/stores/datasets'

vi.mock('../src/api/datasets', () => ({
  datasetApi: {
    list: vi.fn(),
    detail: vi.fn(),
    columns: vi.fn(),
    preview: vi.fn(),
    upload: vi.fn(),
    remove: vi.fn(),
  },
}))

describe('dataset store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('waits until an uploaded dataset reaches ready', async () => {
    datasetApi.upload.mockResolvedValue({ id: 9, status: 'parsing' })
    datasetApi.detail
      .mockResolvedValueOnce({ id: 9, status: 'parsing' })
      .mockResolvedValueOnce({ id: 9, status: 'ready', row_count: 12 })
    const store = useDatasetStore()

    const result = await store.upload(new File(['sales'], 'sales.csv'))

    expect(datasetApi.upload).toHaveBeenCalledOnce()
    expect(datasetApi.detail).toHaveBeenCalledTimes(2)
    expect(result.status).toBe('ready')
    expect(store.currentDataset.row_count).toBe(12)
  })

  it('surfaces parse failure and keeps the failed dataset details', async () => {
    datasetApi.upload.mockResolvedValue({ id: 10, status: 'parsing' })
    datasetApi.detail.mockResolvedValue({ id: 10, status: 'failed', parse_error_message: '文件无法解析' })
    const store = useDatasetStore()

    await expect(store.upload(new File(['bad'], 'bad.csv'))).rejects.toThrow('文件无法解析')
    expect(store.currentDataset.status).toBe('failed')
  })

  it('omits empty optional filters from dataset list requests', async () => {
    datasetApi.list.mockResolvedValue({ items: [], page: 1, page_size: 10, total: 0, pages: 0 })
    const store = useDatasetStore()

    await store.loadList()

    expect(datasetApi.list).toHaveBeenCalledWith({ page: 1, page_size: 10 }, {})
  })
})
