<script>
import { DataAnalysis, Refresh, Search } from '@element-plus/icons-vue'

import AppShell from '../components/AppShell.vue'
import { historyApi } from '../api/history'

export default {
  name: 'HistoryView',
  components: { AppShell, DataAnalysis, Refresh, Search },
  data() { return { items: [], page: 1, pageSize: 10, total: 0, query: '', status: '', loading: false, errorMessage: '', searchTimer: null } },
  created() { this.load() },
  beforeUnmount() { window.clearTimeout(this.searchTimer) },
  watch: {
    query() { window.clearTimeout(this.searchTimer); this.searchTimer = window.setTimeout(() => { this.page = 1; this.load() }, 300) },
    status() { this.page = 1; this.load() },
  },
  methods: {
    async load() {
      this.loading = true; this.errorMessage = ''
      try {
        const result = await historyApi.list({ q: this.query || undefined, status: this.status || undefined, page: this.page, page_size: this.pageSize })
        this.items = result.items; this.total = result.total
      } catch (error) { this.errorMessage = error.message || '分析历史加载失败' }
      finally { this.loading = false }
    },
    dateLabel(value) { return value ? new Date(value).toLocaleString('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }) : '—' },
    statusLabel(value) { return ({ succeeded: '已完成', partial: '部分完成', failed: '失败', pending: '等待中', running: '处理中' })[value] || value },
    statusType(value) { return value === 'succeeded' ? 'success' : value === 'partial' ? 'warning' : value === 'failed' ? 'danger' : 'info' },
    openRecord(record) { this.$router.push({ name: 'history-detail', params: { recordId: record.id } }) },
  },
}
</script>

<template>
  <AppShell>
    <section class="page-heading"><div><p class="eyebrow">每次计算都可回看</p><h1>分析历史</h1><p class="page-intro">查看问题、工具调用、真实结果与总结状态。</p></div></section>
    <div v-if="errorMessage" class="inline-error" role="alert"><span>{{ errorMessage }}</span><el-button text type="primary" @click="load"><el-icon><Refresh /></el-icon>重试</el-button></div>
    <section class="panel history-panel">
      <div class="list-toolbar"><div><h2>所有分析记录</h2><span class="list-count">{{ total }} 条记录</span></div><div class="history-filters"><el-input v-model="query" clearable placeholder="搜索问题或数据集" aria-label="搜索问题或数据集"><template #prefix><el-icon><Search /></el-icon></template></el-input><el-select v-model="status" clearable placeholder="全部状态" aria-label="按状态筛选"><el-option label="已完成" value="succeeded" /><el-option label="部分完成" value="partial" /><el-option label="失败" value="failed" /></el-select></div></div>
      <div v-if="!loading && !items.length" class="empty-state"><span class="empty-icon"><el-icon><DataAnalysis /></el-icon></span><h2>还没有分析记录</h2><p>完成一次真实数据计算后，证据会保存在这里。</p></div>
      <div v-else class="history-list" v-loading="loading">
        <button v-for="record in items" :key="record.id" type="button" class="history-row" @click="openRecord(record)"><span class="history-row-icon"><el-icon><DataAnalysis /></el-icon></span><span class="history-row-copy"><strong>{{ record.question }}</strong><small>{{ record.dataset_name }}<template v-if="record.primary_tool_name"> · {{ record.primary_tool_name }}</template></small></span><el-tag :type="statusType(record.status)" effect="light">{{ statusLabel(record.status) }}</el-tag><time>{{ dateLabel(record.created_at) }}</time><span class="history-arrow" aria-hidden="true">→</span></button>
      </div>
      <el-pagination v-if="total > pageSize" v-model:current-page="page" :page-size="pageSize" :total="total" layout="prev, pager, next" @current-change="load" />
    </section>
  </AppShell>
</template>
