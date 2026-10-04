<script>
import { datasetApi } from '../api/datasets'
import { useDatasetStore } from '../stores/datasets'

const working = new Set(['queued', 'inspecting', 'uploading', 'parsing'])
export default {
  name: 'UploadQueue',
  props: {
    formats: { type: Array, default: () => ['csv', 'tsv', 'json', 'xlsx', 'xls', 'parquet'] },
    maxFiles: { type: Number, default: 10 }, maxBytes: { type: Number, default: 20 * 1024 * 1024 },
    attachedIds: { type: Array, default: () => [] },
    sessionId: Number, prepareSession: Function,
  },
  emits: ['ready', 'document', 'document-hidden', 'busy', 'started', 'removed'],
  data() { return { items: [], processing: false, alive: true, queueError: '' } },
  computed: { busy() { return this.items.some(item => working.has(item.status)) } },
  watch: { busy(value) { if (this.alive) this.$emit('busy', value) } },
  beforeUnmount() { this.stop() },
  methods: {
    stop() { this.alive = false; for (const item of this.items) item.controller?.abort() },
    forgetDataset(id) { this.items = this.items.filter(item => item.datasetId !== id) },
    async addFiles(files) {
      this.queueError = ''
      const unbound = this.items.filter(item => !this.attachedIds.includes(item.datasetId)).length
      if (files.length + unbound + this.attachedIds.length > this.maxFiles) { this.queueError = `最多保留 ${this.maxFiles} 个文件，请先移除不需要的附件。`; return }
      for (const file of files) {
        const extension = file.name.split('.').pop().toLowerCase()
        const error = !this.formats.includes(extension) ? '暂不支持此格式，请选择表格或记录文件。' : file.size > this.maxBytes ? `文件不能超过 ${this.maxBytes / 1024 / 1024} MB。` : !file.size ? '文件为空，请选择有内容的文件。' : ''
        this.items.push({ id: crypto.randomUUID(), file, status: error ? 'invalid' : 'queued', error, percent: 0, sheets: [], sheet: '', inspected: false, datasetId: null, fileId: null, controller: null })
      }
      return this.processQueue()
    },
    async processQueue() {
      if (this.processing || !this.alive) return
      this.processing = true
      try {
        let item
        while (this.alive && (item = this.items.find(entry => entry.status === 'queued'))) {
          const controller = new AbortController()
          item.controller = controller
          try {
            if (/\.xlsx?$/i.test(item.file.name) && !item.inspected) {
              item.status = 'inspecting'
              const result = await datasetApi.inspectSheets(item.file, { signal: controller.signal })
              if (!this.alive || controller.signal.aborted) continue
              item.sheets = result.sheets || []
              item.sheet = result.default || item.sheets[0] || ''
              item.inspected = true
              if (item.sheets.length > 1) { item.status = 'sheet'; continue }
            }
            item.status = item.datasetId ? 'parsing' : 'uploading'
            this.$emit('started')
            if (/\.(txt|pdf|docx)$/i.test(item.file.name)) {
              const sessionId = this.prepareSession ? await this.prepareSession() : this.sessionId
              const document = await useDatasetStore().uploadDocument(item.file, { fileId: item.fileId, sessionId, signal: controller.signal, onAccepted: accepted => { item.fileId = accepted.id; item.status = 'parsing' }, onUploadProgress: event => { if (event.total) item.percent = Math.round(event.loaded / event.total * 100) } })
              if (!this.alive || controller.signal.aborted) continue
              item.status = 'ready'; item.error = ''; this.$emit('document', document); continue
            }
            const dataset = await useDatasetStore().upload(item.file, {
              signal: controller.signal, sheetName: item.sheet, datasetId: item.datasetId,
              onAccepted: accepted => { item.datasetId = accepted.id; item.status = 'parsing' },
              onUploadProgress: event => { if (event.total && !controller.signal.aborted) item.percent = Math.round(event.loaded / event.total * 100) },
            })
            if (!this.alive || controller.signal.aborted) continue
            item.datasetId = dataset.id
            item.status = 'ready'
            item.error = ''
            this.$emit('ready', dataset)
          } catch (error) {
            if (!this.alive) return
            item.status = controller.signal.aborted ? 'cancelled' : 'failed'
            item.error = controller.signal.aborted ? '已停止等待；已受理的解析仍可在数据集页面查看。' : error.message || '上传失败，请重试。'
            // 网络/轮询超时不代表解析失败；保留已受理 ID 以恢复等待。
            if (['DATASET_PARSE_FAILED', 'DATASET_NOT_FOUND'].includes(error.code)) item.datasetId = null
          } finally { item.controller = null }
        }
      } finally { this.processing = false }
    },
    retry(item) { if (working.has(item.status)) return; item.error = ''; item.status = 'queued'; return this.processQueue() },
    cancel(item) { item.controller?.abort(); item.status = 'cancelled'; item.error = '已停止等待；已受理的解析仍可在数据集页面查看。' },
    remove(item) { this.cancel(item); this.items = this.items.filter(entry => entry.id !== item.id); if (item.fileId) this.$emit('document-hidden', item.fileId); else this.$emit('removed', item.datasetId) },
    label(item) { return ({ queued: '等待上传', inspecting: '读取工作表', sheet: '请选择工作表', uploading: `上传 ${item.percent}%`, parsing: '正在解析', ready: '已就绪', failed: '失败', invalid: '无法上传', cancelled: '已停止' })[item.status] },
  },
}
</script>

<template>
  <section v-if="items.length || queueError" class="upload-queue" aria-label="附件上传队列">
    <p v-if="queueError" class="form-error" role="alert">{{ queueError }}</p>
    <ul><li v-for="item in items" :key="item.id">
      <div class="upload-file-info"><strong :title="item.file.name">{{ item.file.name }}</strong><small role="status">{{ label(item) }}</small><progress v-if="item.status === 'uploading'" :value="item.percent" max="100" :aria-label="`${item.file.name} 上传进度`"></progress><p v-if="item.error" class="form-error" role="alert">{{ item.error }}</p></div>
      <label v-if="item.status === 'sheet'" class="sheet-choice">工作表<select v-model="item.sheet" :aria-label="`${item.file.name} 工作表`"><option v-for="sheet in item.sheets" :key="sheet" :value="sheet">{{ sheet }}</option></select><button type="button" @click="retry(item)">上传此工作表</button></label>
      <button v-if="['failed', 'cancelled'].includes(item.status)" type="button" @click="retry(item)">重试</button>
      <button v-if="busy && ['queued','inspecting','uploading','parsing'].includes(item.status)" type="button" @click="cancel(item)">停止等待</button>
      <button type="button" :aria-label="`${item.fileId ? '收起附件预览' : '移除'} ${item.file.name}`" @click="remove(item)">{{ item.fileId ? '收起附件预览' : '移除' }}</button>
    </li></ul>
  </section>
</template>

<style scoped>
.upload-queue { width: 100%; margin-bottom: 12px; }
ul { margin: 0; padding: 0; list-style: none; }
li { display: flex; align-items: center; gap: 10px; background: var(--canvas); padding: 10px 12px; border-radius: 10px; margin-bottom: 6px; flex-wrap: wrap; }
.upload-file-info { flex: 1; min-width: 120px; }
strong { display: block; max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
small { color: var(--muted); font-size: 11px; }
button { border: 0; padding: 6px; background: transparent; color: var(--brand); cursor: pointer; border-radius: 6px; font-size: 12px; }
button:hover { background: var(--line); }
.sheet-choice { display: flex; gap: 6px; align-items: center; font-size: 12px; }
select { max-width: 160px; }
progress { display: block; height: 4px; width: 100%; }
.form-error { font-size: 11px; margin: 4px 0 0; }
</style>
