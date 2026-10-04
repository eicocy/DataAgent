<script>
import { mapState } from 'pinia'
import { ArrowLeft, ChatLineRound, Refresh } from '@element-plus/icons-vue'
import AppShell from '../components/AppShell.vue'
import { datasetApi } from '../api/datasets'
import DataQualityWorkbench from '../components/DataQualityWorkbench.vue'
import CleaningWorkbench from '../components/CleaningWorkbench.vue'
import JoinWorkbench from '../components/JoinWorkbench.vue'
import { useDatasetStore } from '../stores/datasets'

export default {
  name: 'DatasetDetailView',
  components: { AppShell, DataQualityWorkbench, CleaningWorkbench, JoinWorkbench, ArrowLeft, ChatLineRound, Refresh },
  props: { datasetId: { type: String, required: true } },
  data() {
    return {
      activeTab: 'preview', versions: [], selectedVersion: null,
      detailToken: 0, previewToken: 0, loadedPreviewVersion: null,
      previewLoading: false, previewError: '', loading: false,
      errorMessage: '', controller: null, pollTimer: null,
    }
  },
  computed: {
    ...mapState(useDatasetStore, ['currentDataset', 'columns', 'preview']),
    visiblePreview() {
      // 版本标签与加载完成的版本必须相同，慢请求/失败时不借用上一版的行。
      if (this.loadedPreviewVersion !== this.selectedVersion || this.previewLoading || this.previewError) {
        return { columns: [], rows: [], total_rows: null }
      }
      return this.preview
    },
    displayColumns() {
      if (this.selectedVersion === this.currentDataset?.current_version_id) return this.columns
      return (this.versions.find(item => item.id === this.selectedVersion)?.schema?.columns || []).map(item => ({
        name: item.name, original_name: item.original_name || item.name,
        data_type: item.dtype || '未记录', missing_count: '未在快照中提供', unique_count: null,
        sample_values: this.visiblePreview.rows.slice(0, 3).map(row => row[item.name])
          .filter(value => value != null).map(String),
      }))
    },
    selectedColumns() {
      return this.versions.find(item => item.id === this.selectedVersion)?.schema?.columns?.map(item => item.name) || []
    },
    ready() { return this.currentDataset?.status === 'ready' },
  },
  created() { this.loadAll() },
  beforeUnmount() {
    this.detailToken++
    this.previewToken++
    this.controller?.abort()
    window.clearTimeout(this.pollTimer)
  },
  watch: {
    datasetId() { this.selectedVersion = null; this.loadAll() },
    selectedVersion() { this.loadSelectedPreview() },
  },
  methods: {
    async loadAll() {
      const token = ++this.detailToken
      this.previewToken++
      this.loadedPreviewVersion = null
      this.previewError = ''
      window.clearTimeout(this.pollTimer)
      this.controller?.abort()
      this.controller = new AbortController()
      const { signal } = this.controller
      this.loading = true
      this.errorMessage = ''
      try {
        const dataset = await datasetApi.detail(this.datasetId, { signal })
        if (token !== this.detailToken) return
        useDatasetStore().currentDataset = dataset
        if (dataset.status === 'ready') {
          const versions = await datasetApi.versions(this.datasetId, { signal })
          if (token !== this.detailToken) return
          this.versions = versions
          this.selectedVersion ||= dataset.current_version_id
          const columns = await datasetApi.columns(this.datasetId, { signal })
          if (token !== this.detailToken) return
          useDatasetStore().columns = columns
          await this.loadSelectedPreview()
        } else if (['parsing', 'uploading'].includes(dataset.status)) {
          this.pollTimer = window.setTimeout(this.loadAll, 1200)
        }
      } catch (error) {
        if (token === this.detailToken && !signal.aborted) this.errorMessage = error.message || '数据集加载失败'
      } finally {
        if (token === this.detailToken) this.loading = false
      }
    },
    async loadSelectedPreview() {
      const token = ++this.previewToken
      const version = this.selectedVersion
      this.loadedPreviewVersion = null
      this.previewError = ''
      this.previewLoading = Boolean(version)
      if (!version) return
      const controller = this.controller
      try {
        const value = await datasetApi.preview(this.datasetId,
          { dataset_version_id: version }, { signal: controller.signal })
        if (token !== this.previewToken || controller.signal.aborted) return
        useDatasetStore().preview = value
        this.loadedPreviewVersion = version
      } catch (error) {
        if (token === this.previewToken && !controller.signal.aborted) {
          this.previewError = error.message || '版本预览失败，请重试读取当前选择的版本。'
        }
      } finally {
        if (token === this.previewToken) this.previewLoading = false
      }
    },
    statusLabel(status) {
      return ({ ready: '可分析', parsing: '解析中', failed: '解析失败', uploading: '上传中' })[status] || status
    },
    showValue(value) { return value === null || value === undefined ? '—' : String(value) },
  },
}
</script>

<template>
  <AppShell>
    <section class="page-heading dataset-detail-heading"><div><el-button text class="back-link" @click="$router.push('/datasets')"><el-icon><ArrowLeft /></el-icon>返回数据集</el-button><p class="eyebrow">数据集详情</p><h1>{{ currentDataset?.original_name || '正在加载…' }}</h1><p class="page-intro">{{ currentDataset?.row_count ?? '—' }} 行 · {{ currentDataset?.column_count ?? '—' }} 列 · {{ currentDataset?.file_type?.toUpperCase() }}</p></div><div class="detail-heading-actions"><span class="dataset-status" :class="`status-${currentDataset?.status}`"><i></i>{{ statusLabel(currentDataset?.status) }}</span><el-button type="primary" :disabled="!ready" @click="$router.push({ name: 'analysis', query: { datasetId } })"><el-icon><ChatLineRound /></el-icon>开始分析</el-button></div></section>
    <div v-if="errorMessage" class="inline-error"><span>{{ errorMessage }}</span><el-button text type="primary" @click="loadAll"><el-icon><Refresh /></el-icon>重试</el-button></div>
    <section v-if="currentDataset?.status === 'failed'" class="panel parse-failure" role="alert"><h2>文件解析失败</h2><p>{{ currentDataset.parse_error_message || '文件无法解析，请检查格式后重新上传。' }}</p><el-button type="primary" @click="$router.push('/datasets/upload')">重新上传</el-button></section>
    <section v-else-if="!ready" class="panel parsing-panel" aria-live="polite"><span class="large-loader"></span><h2>正在准备数据</h2><p>系统正在识别字段并整理数据预览，请稍候。</p></section>
    <section v-else class="panel detail-panel">
      <p v-for="(warning, index) in currentDataset.quality_warnings || currentDataset.warnings || []" :key="index" class="summary-warning" role="status">{{ typeof warning === 'string' ? warning : warning.message }}</p>
      <label>查看数据版本<select v-model="selectedVersion"><option v-for="version in versions" :key="version.id" :value="version.id">版本 {{ version.version_number }}{{ version.id === currentDataset.current_version_id ? ' · 当前' : ' · 历史' }}</option></select></label>
      <div class="detail-tabs" role="tablist"><button type="button" role="tab" :aria-selected="activeTab === 'preview'" :class="{ 'is-active': activeTab === 'preview' }" @click="activeTab = 'preview'">数据预览 <span>{{ currentDataset.row_count }}</span></button><button type="button" role="tab" :aria-selected="activeTab === 'columns'" :class="{ 'is-active': activeTab === 'columns' }" @click="activeTab = 'columns'">字段信息 <span>{{ columns.length }}</span></button><button v-for="(label, tab) in { quality: '数据质量', cleaning: '清洗', join: '合并' }" :key="tab" type="button" role="tab" :aria-selected="activeTab === tab" :class="{ 'is-active': activeTab === tab }" @click="activeTab = tab">{{ label }}</button></div>
      <DataQualityWorkbench v-if="activeTab === 'quality'" :dataset-id="Number(datasetId)" :version-id="selectedVersion" />
      <CleaningWorkbench v-else-if="activeTab === 'cleaning'" :dataset-id="Number(datasetId)" :version-id="selectedVersion" :columns="selectedColumns" @published="loadAll" />
      <JoinWorkbench v-else-if="activeTab === 'join'" :dataset-id="Number(datasetId)" :version-id="selectedVersion" :columns="selectedColumns" @published="loadAll" />
      <div v-else-if="activeTab === 'preview'" class="table-wrap">
        <p v-if="previewLoading" role="status">正在读取版本预览…</p>
        <p v-else-if="previewError" class="inline-error" role="alert">{{ previewError }} <el-button @click="loadSelectedPreview">重试版本预览</el-button></p>
        <p v-else-if="loadedPreviewVersion !== selectedVersion">当前版本预览尚不可用。</p>
        <el-table v-else :data="visiblePreview.rows" v-loading="loading" stripe height="440"><el-table-column v-for="column in visiblePreview.columns" :key="column" :prop="column" :label="column" min-width="140" show-overflow-tooltip><template #default="scope">{{ showValue(scope.row[column]) }}</template></el-table-column></el-table><p v-if="loadedPreviewVersion === selectedVersion && !previewLoading && !previewError" class="table-footnote">版本 {{ loadedPreviewVersion }}：显示 {{ visiblePreview.rows.length }} 行样例，共 {{ visiblePreview.total_rows }} 行。</p></div>
      <el-table v-else-if="activeTab === 'columns'" :data="displayColumns" v-loading="loading" stripe><el-table-column prop="name" label="字段名" min-width="180" /><el-table-column prop="original_name" label="原始列名" min-width="180" /><el-table-column prop="data_type" label="识别类型" width="140" /><el-table-column prop="missing_count" label="缺失值" width="110" /><el-table-column label="唯一值" width="110"><template #default="scope">{{ scope.row.unique_count ?? '—' }}</template></el-table-column><el-table-column label="样例值" min-width="260"><template #default="scope">{{ scope.row.sample_values.join('、') || '—' }}</template></el-table-column></el-table>
    </section>
  </AppShell>
</template>
