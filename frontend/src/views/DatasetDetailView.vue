<script>
import { mapState, mapActions } from 'pinia'
import { ArrowLeft, ChatLineRound, Refresh } from '@element-plus/icons-vue'

import AppShell from '../components/AppShell.vue'
import { useDatasetStore } from '../stores/datasets'

export default {
  name: 'DatasetDetailView',
  components: { AppShell, ArrowLeft, ChatLineRound, Refresh },
  props: { datasetId: { type: String, required: true } },
  data() { return { activeTab: 'preview', loading: false, errorMessage: '', controller: null, pollTimer: null } },
  computed: { ...mapState(useDatasetStore, ['currentDataset', 'columns', 'preview']), ready() { return this.currentDataset?.status === 'ready' } },
  created() { this.loadAll() },
  beforeUnmount() { this.controller?.abort(); window.clearTimeout(this.pollTimer) },
  watch: { datasetId() { this.loadAll() } },
  methods: {
    ...mapActions(useDatasetStore, ['loadDataset', 'loadColumns', 'loadPreview']),
    async loadAll() {
      this.controller?.abort(); this.controller = new AbortController()
      const { signal } = this.controller
      this.loading = true; this.errorMessage = ''
      try {
        const dataset = await this.loadDataset(this.datasetId, { signal })
        if (dataset.status === 'ready') await Promise.all([this.loadColumns(this.datasetId, { signal }), this.loadPreview(this.datasetId, {}, { signal })])
        else if (dataset.status === 'parsing' || dataset.status === 'uploading') this.pollTimer = window.setTimeout(this.loadAll, 1200)
      } catch (error) { if (error.name !== 'AbortError') this.errorMessage = error.message || '数据集加载失败' }
      finally { this.loading = false }
    },
    statusLabel(status) { return ({ ready: '可分析', parsing: '解析中', failed: '解析失败', uploading: '上传中' })[status] || status },
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
      <div class="detail-tabs" role="tablist"><button type="button" role="tab" :aria-selected="activeTab === 'preview'" :class="{ 'is-active': activeTab === 'preview' }" @click="activeTab = 'preview'">数据预览 <span>{{ currentDataset.row_count }}</span></button><button type="button" role="tab" :aria-selected="activeTab === 'columns'" :class="{ 'is-active': activeTab === 'columns' }" @click="activeTab = 'columns'">字段信息 <span>{{ columns.length }}</span></button></div>
      <div v-if="activeTab === 'preview'" class="table-wrap"><el-table :data="preview.rows" v-loading="loading" stripe height="440"><el-table-column v-for="column in preview.columns" :key="column" :prop="column" :label="column" min-width="140" show-overflow-tooltip><template #default="scope">{{ showValue(scope.row[column]) }}</template></el-table-column></el-table><p class="table-footnote">显示 {{ preview.rows.length }} 行样例，共 {{ preview.total_rows }} 行。</p></div>
      <el-table v-else :data="columns" v-loading="loading" stripe><el-table-column prop="name" label="字段名" min-width="180" /><el-table-column prop="original_name" label="原始列名" min-width="180" /><el-table-column prop="data_type" label="识别类型" width="140" /><el-table-column prop="missing_count" label="缺失值" width="110" /><el-table-column label="唯一值" width="110"><template #default="scope">{{ scope.row.unique_count ?? '—' }}</template></el-table-column><el-table-column label="样例值" min-width="260"><template #default="scope">{{ scope.row.sample_values.join('、') || '—' }}</template></el-table-column></el-table>
    </section>
  </AppShell>
</template>
