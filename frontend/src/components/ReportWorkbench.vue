<script>
import { reportsApi } from '../api/reports'
import { analysisApi } from '../api/analysis'

const FORMATS = [
  { id: 'pdf', label: 'PDF' }, { id: 'docx', label: 'Word' },
  { id: 'xlsx', label: 'Excel' }, { id: 'html', label: 'HTML' },
  { id: 'markdown', label: 'Markdown' }, { id: 'csv', label: 'CSV' },
  { id: 'json', label: 'JSON' },
  { id: 'python', label: 'Python' }, { id: 'sql', label: 'SQL' },
]

export default {
  name: 'ReportWorkbench',
  props: {
    modelValue: { type: Boolean, default: false },
    sessionId: { type: Number, required: true },
    source: { type: Object, default: null },
    reportId: { type: Number, default: null },
  },
  emits: ['update:modelValue', 'changed'],
  data() {
    return { report: null, title: '', sections: [], loading: false, saving: false,
      exporting: '', errorMessage: '', files: [], formats: FORMATS, requestGeneration: 0,
      createRequestId: null, exportRequestIds: {}, template: 'auto' }
  },
  watch: {
    modelValue: { immediate: true, handler(value) { if (value && !this.report) this.createReport() } },
    sessionId() { this.resetReport() },
    reportId() { this.resetReport() },
    'source.record_id'() { if (!this.reportId) this.resetReport() },
  },
  methods: {
    resetReport() { this.requestGeneration++; this.report = null; this.sections = []; this.files = []; this.createRequestId = null; this.exportRequestIds = {}; this.loading = false; this.exporting = ''; this.saving = false; this.errorMessage = ''; if (this.modelValue) this.createReport() },
    close() { this.$emit('update:modelValue', false) },
    async createReport() {
      if (this.loading || (!this.reportId && (!this.source?.record_id || !this.source?.dataset_id || !this.source?.dataset_version_id))) return
      const generation = ++this.requestGeneration
      this.loading = true
      this.errorMessage = ''
      try {
        if (this.reportId) { const value = await reportsApi.get(this.reportId); if (generation === this.requestGeneration) this.applyReport(value); return }
        this.createRequestId ||= crypto.randomUUID()
        const response = await reportsApi.create({
          session_id: this.sessionId,
          source_record_ids: [this.source.record_id],
          request_id: this.createRequestId,
          spec: { title: '数据分析报告', template: this.template, report_type: 'general', dataset_id: this.source.dataset_id,
            dataset_version_id: this.source.dataset_version_id },
        })
        const value = await this.waitForReportTask(response.record_id, generation)
        if (generation === this.requestGeneration) { this.applyReport(value.report || value); this.$emit('changed') }
      } catch (error) {
        if (generation === this.requestGeneration) this.errorMessage = error.message || '报告生成失败'
      } finally { if (generation === this.requestGeneration) this.loading = false }
    },
    async waitForReportTask(recordId, generation = this.requestGeneration) {
      const deadline = Date.now() + 300000
      while (Date.now() < deadline) {
        if (generation !== this.requestGeneration) throw new Error('报告工作区已切换')
        const result = await analysisApi.run(recordId)
        if (result.status === "succeeded") return result.report || {}
        if (["failed", "cancelled"].includes(result.status)) {
          const error = new Error(result.error_message || "报告任务未完成")
          error.code = result.error_code
          throw error
        }
        await new Promise((resolve) => window.setTimeout(resolve, 700))
      }
      throw new Error("报告任务超过 5 分钟，请稍后从任务记录查看状态")
    },
    applyReport(value) {
      this.report = value
      this.title = value.document?.title || value.title
      const configured = value.spec?.sections || []
      this.sections = (value.document?.sections?.length ? value.document.sections : configured).map((section) => ({ ...section }))
    },
    async saveReport() {
      if (!this.report || this.saving) return
      this.saving = true
      this.errorMessage = ''
      const generation = this.requestGeneration
      try {
        const spec = { ...this.report.spec, report_id: this.report.id,
          base_version: this.report.version, title: this.title.trim(),
          sections: this.sections.map(({ data, ...section }) => section) }
        const response = await reportsApi.update(this.report.id, {
          session_id: this.sessionId, source_record_ids: this.report.source_record_ids, spec,
        })
        if (generation === this.requestGeneration) { this.applyReport(response); this.$emit('changed') }
      } catch (error) {
        if (generation === this.requestGeneration) this.errorMessage = error.code === 'REPORT_VERSION_CONFLICT'
          ? '报告版本已更新，请重新打开后继续编辑。' : error.message || '报告保存失败'
      } finally { if (generation === this.requestGeneration) this.saving = false }
    },
    async exportReport(format) {
      if (!this.report || this.exporting) return
      this.exporting = format
      this.errorMessage = ''
      const generation = this.requestGeneration
      try {
        const key = `${this.report.id}:${this.report.version}:${format}`
        this.exportRequestIds[key] ||= crypto.randomUUID()
        const task = await reportsApi.export(this.report.id, this.report.version, format, { requestId: this.exportRequestIds[key] })
        const result = await this.waitForReportTask(task.record_id, generation)
        if (generation === this.requestGeneration) { this.files = [...(result.artifacts || []), ...this.files.filter(item => !result.artifacts?.some(file => file.artifact_id === item.artifact_id))]; this.$emit('changed') }
      } catch (error) {
        if (generation === this.requestGeneration) this.errorMessage = error.message || '导出失败，请重试'
      } finally { if (generation === this.requestGeneration) this.exporting = '' }
    },
    removeSection(index) { if (this.sections.length > 1) this.sections.splice(index, 1) },
    artifactUrl(file) { return file.download_url }
  },
  beforeUnmount() { this.requestGeneration++ },
}
</script>

<template>
  <el-dialog :model-value="modelValue" class="report-dialog" width="min(980px, 94vw)" top="4vh" :close-on-click-modal="false" @close="close">
    <template #header>
      <div class="report-dialog-heading"><div><p class="eyebrow">固定数据版本 · 可追溯来源</p><h2>报告工作区</h2></div><el-tag v-if="report" effect="plain">v{{ report.version }}</el-tag></div>
    </template>
    <div v-if="loading" class="report-loading" role="status">正在整理报告内容…</div>
    <div v-else-if="errorMessage && !report" class="report-error" role="alert"><p>{{ errorMessage }}</p><el-button type="primary" @click="createReport">重试生成</el-button></div>
    <div v-else-if="report" class="report-layout">
      <section class="report-preview">
        <label class="report-title-field">报告标题<el-input v-model="title" maxlength="255" /></label>
        <div class="report-section-list">
          <article v-for="(section, index) in sections" :key="section.section_id" class="report-section-card">
            <header><el-input v-model="section.title" maxlength="160" aria-label="章节标题" /><el-button v-if="sections.length > 1" text type="danger" aria-label="删除章节" @click="removeSection(index)">删除</el-button></header>
            <p v-if="section.narrative">{{ section.narrative }}</p>
            <div v-for="(table, tableIndex) in (section.data?.tables || [])" :key="tableIndex" class="report-table-wrap">
              <table><thead><tr><th v-for="column in table.columns" :key="column">{{ column }}</th></tr></thead><tbody><tr v-for="(row, rowIndex) in table.rows?.slice(0, 20)" :key="rowIndex"><td v-for="column in table.columns" :key="column">{{ row[column] ?? '—' }}</td></tr></tbody></table>
            </div>
            <small v-if="section.evidence_ids?.length" class="report-evidence">依据 {{ section.evidence_ids.join(' · ') }}</small>
          </article>
          <div v-if="!sections.length" class="report-empty">所有章节已删除。保存后会保留空白报告版本。</div>
        </div>
      </section>
      <aside class="report-tools">
        <div class="report-toolbar"><h3>导出格式</h3><el-button plain :loading="saving" @click="saveReport">保存新版本</el-button></div>
        <p class="report-help">修改章节后保存会创建不可变新版本；之前生成的文件仍关联原版本。</p>
        <p class="report-help">计算指标来自固定版本证据。用户修改的标题和文案会在新版本中标记。</p>
        <div class="report-format-grid"><el-button v-for="item in formats" :key="item.id" plain :loading="exporting === item.id" :disabled="Boolean(exporting)" @click="exportReport(item.id)">{{ item.label }}</el-button></div>
        <div v-if="files.length" class="report-files"><h3>已生成文件</h3><a v-for="(file, index) in files" :key="`${file.artifact_id}-${index}`" :href="artifactUrl(file)"><span>{{ file.file_name }}</span><small>{{ Math.ceil(file.size_bytes / 1024) }} KB</small></a></div>
        <p v-if="errorMessage" class="report-error" role="alert">{{ errorMessage }}</p>
      </aside>
    </div>
  </el-dialog>
</template>
