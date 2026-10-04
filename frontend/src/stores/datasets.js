import { defineStore } from 'pinia'

import { datasetApi } from '../api/datasets'
import { filesApi } from '../api/files'

function delay(milliseconds, signal) {
  return new Promise((resolve, reject) => {
    const finish = () => { signal?.removeEventListener('abort', abort); resolve() }
    const timer = window.setTimeout(finish, milliseconds)
    const abort = () => {
      window.clearTimeout(timer)
      reject(new DOMException('Request cancelled', 'AbortError'))
    }
    signal?.addEventListener('abort', abort, { once: true })
  })
}

export const useDatasetStore = defineStore('datasets', {
  state: () => ({
    items: [], currentDataset: null, columns: [],
    preview: { columns: [], rows: [], offset: 0, limit: 50, total_rows: 0 },
    query: { q: '', file_type: '', status: '', page: 1, page_size: 10 },
    pagination: { page: 1, page_size: 10, total: 0, pages: 0 },
    loading: false, uploadStatus: 'idle', error: null,
  }),
  actions: {
    async uploadDocument(file, { fileId, sessionId, signal, onAccepted, onUploadProgress } = {}) {
      const accepted = fileId ? { id: fileId } : (await filesApi.upload(file, { sessionId, signal, onUploadProgress })).file
      onAccepted?.(accepted)
      const deadline = Date.now() + 120000
      while (Date.now() < deadline) {
        if (signal?.aborted) throw new DOMException('Request cancelled', 'AbortError')
        const result = await filesApi.detail(accepted.id, { signal })
        if (result.status === 'ready') return result
        if (result.status === 'failed') throw new Error(result.error_message || '文档解析失败，请检查源文件。')
        await delay(1000, signal)
      }
      throw new Error('解析仍在处理，请稍后继续等待或到文件页面查看。')
    },
    reset() {
      this.items = []
      this.currentDataset = null
      this.columns = []
      this.preview = { columns: [], rows: [], offset: 0, limit: 50, total_rows: 0 }
      this.query = { q: '', file_type: '', status: '', page: 1, page_size: 10 }
      this.pagination = { page: 1, page_size: 10, total: 0, pages: 0 }
      this.loading = false
      this.uploadStatus = 'idle'
      this.error = null
    },
    async loadList(params = this.query, config = {}) {
      this.loading = true
      this.error = null
      try {
        this.query = { ...this.query, ...params }
        const query = Object.fromEntries(
          Object.entries(this.query).filter(([, value]) => value !== '' && value !== null && value !== undefined),
        )
        const result = await datasetApi.list(query, config)
        this.items = result.items
        this.pagination = { page: result.page, page_size: result.page_size, total: result.total, pages: result.pages }
        return result
      } catch (error) {
        this.error = error
        throw error
      } finally {
        this.loading = false
      }
    },
    async loadDataset(id, config = {}) { this.currentDataset = await datasetApi.detail(id, config); return this.currentDataset },
    async loadColumns(id, config = {}) { this.columns = await datasetApi.columns(id, config); return this.columns },
    async loadPreview(id, params = {}, config = {}) { this.preview = await datasetApi.preview(id, params, config); return this.preview },
    async upload(file, { signal, onUploadProgress, sheetName, onAccepted, datasetId } = {}) {
      this.uploadStatus = 'uploading'
      this.error = null
      try {
        const accepted = datasetId ? { id: datasetId } : await datasetApi.upload(file, sheetName, { signal, onUploadProgress })
        onAccepted?.(accepted)
        this.currentDataset = accepted
        this.uploadStatus = 'parsing'
        const deadline = Date.now() + 120000
        while (Date.now() < deadline) {
          if (signal?.aborted) throw new DOMException('Request cancelled', 'AbortError')
          const result = await datasetApi.detail(accepted.id, { signal })
          this.currentDataset = result
          if (result.status === 'ready') { this.uploadStatus = 'ready'; return result }
          if (result.status === 'failed') {
            this.uploadStatus = 'failed'
            throw Object.assign(new Error(result.parse_error_message || '文件解析失败'), { code: 'DATASET_PARSE_FAILED' })
          }
          await delay(1000, signal)
        }
        throw new Error('解析时间过长，请稍后在数据集列表查看状态')
      } catch (error) {
        if (error.name !== 'AbortError') { this.uploadStatus = 'failed'; this.error = error }
        throw error
      }
    },
    async remove(id) {
      await datasetApi.remove(id)
      this.items = this.items.filter((item) => item.id !== id)
      if (this.currentDataset?.id === id) this.currentDataset = null
    },
  },
})
