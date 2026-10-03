<script>
import AppShell from '../components/AppShell.vue'
import { reportsApi } from '../api/reports'

export default {
  name: 'ArtifactsView',
  components: { AppShell },
  data() {
    return { items: [], offset: 0, limit: 30, hasMore: false, loading: false,
      errorMessage: '', selected: null, preview: null, previewLoading: false }
  },
  created() { this.loadArtifacts() },
  methods: {
    async loadArtifacts() {
      this.loading = true
      this.errorMessage = ''
      try {
        const result = await reportsApi.artifacts({ offset: this.offset, limit: this.limit })
        this.items = result.items || []
        this.hasMore = result.has_more
      } catch (error) { this.errorMessage = error.message || '文件列表加载失败' }
      finally { this.loading = false }
    },
    async openPreview(item) {
      this.selected = item
      this.preview = null
      this.previewLoading = true
      try {
        const result = await reportsApi.preview(item.artifact_id, { limit: 100 })
        this.preview = result.preview
      } catch (error) { this.errorMessage = error.message || '文件预览失败' }
      finally { this.previewLoading = false }
    },
    closePreview() { this.selected = null; this.preview = null },
    nextPage() { if (!this.hasMore || this.loading) return; this.offset += this.limit; this.loadArtifacts() },
    previousPage() { if (this.offset <= 0 || this.loading) return; this.offset = Math.max(0, this.offset - this.limit); this.loadArtifacts() },
    sizeLabel(size) { return size < 1024 ? `${size} B` : `${(size / 1024).toFixed(1)} KB` },
    statusLabel(status) { return status === 'EXPIRED' ? '已过期' : status === 'READY' ? '可用' : status },
    frameUrl() { return this.preview?.preview_url || '' },
  },
}
</script>

<template>
  <AppShell>
    <section class="page-heading"><div><p class="eyebrow">Artifact Library</p><h1>文件与工件</h1><p class="page-intro">预览和下载当前账号生成的分析结果与报告文件。</p></div></section>
    <section class="panel artifact-library">
      <div class="list-toolbar"><div><h2>最近生成</h2><span>{{ items.length }} 个文件</span></div><el-button plain :loading="loading" @click="loadArtifacts">刷新</el-button></div>
      <p v-if="errorMessage" class="inline-error" role="alert">{{ errorMessage }} <el-button text type="primary" @click="loadArtifacts">重试</el-button></p>
      <div v-if="loading && !items.length" class="empty-state" role="status">正在加载文件…</div>
      <div v-else-if="!items.length" class="empty-state"><span class="empty-icon">▧</span><h2>还没有生成文件</h2><p>完成一次分析后，可以在工作台生成 PDF、Word、Excel 或网页报告。</p><el-button type="primary" @click="$router.push('/analysis')">开始分析</el-button></div>
      <div v-else class="artifact-list">
        <article v-for="item in items" :key="item.artifact_id" class="artifact-row">
          <button class="artifact-open" type="button" :disabled="item.status === 'EXPIRED'" @click="openPreview(item)"><span class="artifact-type">{{ item.artifact_type }}</span><span class="artifact-copy"><strong>{{ item.file_name || item.title }}</strong><small>{{ item.mime_type }} · {{ sizeLabel(item.size_bytes) }} · {{ new Date(item.created_at).toLocaleString('zh-CN') }}</small></span><el-tag size="small" :type="item.status === 'EXPIRED' ? 'info' : 'success'">{{ statusLabel(item.status) }}</el-tag></button>
          <a class="artifact-download" :href="item.download_url" :aria-label="`下载 ${item.file_name || item.title}`">下载</a>
        </article>
      </div>
      <div v-if="items.length" class="artifact-pagination"><el-button plain :disabled="offset === 0 || loading" @click="previousPage">上一页</el-button><span>第 {{ Math.floor(offset / limit) + 1 }} 页</span><el-button plain :disabled="!hasMore || loading" @click="nextPage">下一页</el-button></div>
    </section>
    <el-dialog :model-value="Boolean(selected)" :title="selected?.file_name || '文件预览'" width="min(1100px, 95vw)" top="3vh" @close="closePreview">
      <div v-if="previewLoading" class="empty-state" role="status">正在读取预览…</div>
      <div v-else-if="preview?.kind === 'workbook'" class="workbook-preview"><section v-for="sheet in preview.sheets" :key="sheet.name"><h3>{{ sheet.name }}</h3><div class="table-wrap"><table class="data-table"><tbody><tr v-for="(row, rowIndex) in sheet.rows" :key="rowIndex"><td v-for="(cell, cellIndex) in row" :key="cellIndex">{{ cell }}</td></tr></tbody></table></div></section></div>
      <article v-else-if="preview?.kind === 'report_document'" class="document-preview"><h1>{{ preview.document.title }}</h1><section v-for="section in preview.document.sections" :key="section.section_id"><h2>{{ section.title }}</h2><p>{{ section.narrative }}</p></section></article>
      <iframe v-else-if="preview?.kind === 'document'" class="artifact-frame" :src="frameUrl()" :title="selected?.file_name || '报告预览'"></iframe>
      <pre v-else-if="preview?.kind === 'text'" class="artifact-text-preview">{{ preview.content }}</pre>
      <div v-else-if="preview" class="artifact-text-preview">{{ preview.rows?.length || 0 }} 行 · {{ preview.columns?.join('、') }}</div>
      <template #footer><a v-if="selected" class="el-button el-button--primary is-plain" :href="selected.download_url">下载文件</a><el-button @click="closePreview">关闭</el-button></template>
    </el-dialog>
  </AppShell>
</template>
