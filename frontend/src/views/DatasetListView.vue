<script>
import { mapState, mapActions } from 'pinia'
import { Files, Plus, Refresh } from '@element-plus/icons-vue'

import AppShell from '../components/AppShell.vue'
import { useDatasetStore } from '../stores/datasets'

export default {
  name: 'DatasetListView',
  components: { AppShell, Files, Plus, Refresh },
  data() { return { searchText: this.$route.query.q || '', searchTimer: null, loadError: '', deleteTarget: null, deleting: false } },
  computed: {
    ...mapState(useDatasetStore, ['items', 'pagination', 'loading']),
    deleteDialogVisible: {
      get() { return Boolean(this.deleteTarget) },
      set(visible) { if (!visible && !this.deleting) this.deleteTarget = null },
    },
  },
  created() { this.load() },
  beforeUnmount() { window.clearTimeout(this.searchTimer) },
  watch: {
    searchText(value) {
      window.clearTimeout(this.searchTimer)
      this.searchTimer = window.setTimeout(() => {
        this.$router.replace({ query: { ...this.$route.query, q: value || undefined, page: undefined } })
        this.load({ q: value, page: 1 })
      }, 300)
    },
    '$route.query.q'(value) { if ((value || '') !== this.searchText) this.searchText = value || '' },
  },
  methods: {
    ...mapActions(useDatasetStore, ['loadList', 'remove']),
    async load(overrides = {}) {
      this.loadError = ''
      try { await this.loadList({ q: this.$route.query.q || '', page: Number(this.$route.query.page || 1), ...overrides }) }
      catch (error) { this.loadError = error.message || '数据集加载失败' }
    },
    pageChanged(page) { this.$router.replace({ query: { ...this.$route.query, page: String(page) } }); this.load({ page }) },
    async confirmDelete() {
      if (!this.deleteTarget || this.deleting) return
      this.deleting = true
      try {
        await this.remove(this.deleteTarget.id)
        this.deleteTarget = null
        await this.load()
      } catch (error) { this.loadError = error.message || '删除失败，请稍后重试' }
      finally { this.deleting = false }
    },
    formatSize(bytes) { return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB` },
    statusLabel(status) { return ({ ready: '可分析', parsing: '解析中', failed: '解析失败', uploading: '上传中' })[status] || status },
  },
}
</script>

<template>
  <AppShell>
    <section class="page-heading"><div><p class="eyebrow">数据管理</p><h1>数据集</h1><p class="page-intro">上传和管理用于分析的 CSV 与 Excel 数据。</p></div><el-button type="primary" size="large" @click="$router.push('/datasets/upload')"><el-icon><Plus /></el-icon>上传数据</el-button></section>
    <section class="panel dataset-panel">
      <div class="list-toolbar"><div><h2>所有数据集</h2><span>{{ pagination.total }} 个文件</span></div><el-input v-model="searchText" clearable placeholder="搜索文件名" class="dataset-search"><template #prefix><el-icon><Files /></el-icon></template></el-input></div>
      <div v-if="loadError" class="empty-state"><p class="empty-title">{{ loadError }}</p><el-button text type="primary" @click="load">重试</el-button></div>
      <el-table v-else-if="items.length" :data="items" v-loading="loading" row-key="id" class="dataset-table">
        <el-table-column label="名称" min-width="260"><template #default="scope"><button class="dataset-name" type="button" @click="$router.push(`/datasets/${scope.row.id}`)"><span class="file-badge" :class="`file-${scope.row.file_type}`">{{ scope.row.file_type.toUpperCase() }}</span><span><strong>{{ scope.row.original_name }}</strong><small>{{ formatSize(scope.row.file_size) }}</small></span></button></template></el-table-column>
        <el-table-column label="数据规模" width="160"><template #default="scope">{{ scope.row.row_count ?? '—' }} 行 · {{ scope.row.column_count ?? '—' }} 列</template></el-table-column>
        <el-table-column label="状态" width="125"><template #default="scope"><span class="dataset-status" :class="`status-${scope.row.status}`"><i></i>{{ statusLabel(scope.row.status) }}</span></template></el-table-column>
        <el-table-column label="上传时间" width="190"><template #default="scope">{{ new Date(scope.row.created_at).toLocaleString('zh-CN') }}</template></el-table-column>
        <el-table-column label="操作" width="145" align="right"><template #default="scope"><el-button text type="primary" @click="$router.push(`/datasets/${scope.row.id}`)">查看</el-button><el-button text type="danger" :disabled="['parsing', 'uploading'].includes(scope.row.status)" @click="deleteTarget = scope.row">删除</el-button></template></el-table-column>
      </el-table>
      <div v-else-if="!loading" class="empty-state"><span class="empty-illustration"><el-icon><Files /></el-icon></span><p class="empty-title">{{ searchText ? '没有匹配的数据集' : '还没有数据集' }}</p><p class="empty-copy">上传一个 CSV 或 Excel 文件，系统会自动识别字段并生成数据预览。</p><el-button v-if="!searchText" type="primary" @click="$router.push('/datasets/upload')">上传第一个数据集</el-button><el-button v-else text @click="searchText = ''">清除搜索</el-button></div>
      <div v-if="pagination.pages > 1" class="table-pagination"><el-pagination background layout="prev, pager, next" :current-page="pagination.page" :page-count="pagination.pages" @current-change="pageChanged" /></div>
    </section>
    <el-dialog v-model="deleteDialogVisible" title="删除数据集" width="420px" @closed="deleteTarget = null">
      <p class="dialog-copy">删除后，数据文件、预览信息以及关联的会话和分析记录都会移除，且无法恢复。</p>
      <template #footer><el-button @click="deleteTarget = null">取消</el-button><el-button type="danger" :loading="deleting" @click="confirmDelete">确认删除</el-button></template>
    </el-dialog>
  </AppShell>
</template>
