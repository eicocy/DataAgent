<script>
import { Clock, Delete, Files, Plus, Refresh } from '@element-plus/icons-vue'

import AppShell from '../components/AppShell.vue'
import { analysisApi } from '../api/analysis'

export default {
  name: 'SessionsView',
  components: { AppShell, Clock, Delete, Files, Plus, Refresh },
  data() {
    return {
      items: [], page: 1, pageSize: 10, total: 0, searchText: '', loading: false,
      errorMessage: '', deleteTarget: null, deleting: false, searchTimer: null,
    }
  },
  computed: {
    deleteDialogVisible: {
      get() { return Boolean(this.deleteTarget) },
      set(value) { if (!value && !this.deleting) this.deleteTarget = null },
    },
  },
  created() { this.load() },
  beforeUnmount() { window.clearTimeout(this.searchTimer) },
  watch: {
    searchText() {
      window.clearTimeout(this.searchTimer)
      this.searchTimer = window.setTimeout(() => { this.page = 1; this.load() }, 300)
    },
  },
  methods: {
    async load() {
      this.loading = true
      this.errorMessage = ''
      try {
        const result = await analysisApi.sessions({ q: this.searchText || undefined, page: this.page, page_size: this.pageSize })
        this.items = result.items
        this.total = result.total
      } catch (error) { this.errorMessage = error.message || '分析会话加载失败' }
      finally { this.loading = false }
    },
    openSession(session) {
      this.$router.push({ name: 'analysis', params: { sessionId: session.id }, query: { datasetId: session.dataset_id } })
    },
    async removeSession() {
      if (!this.deleteTarget || this.deleting) return
      this.deleting = true
      try {
        await analysisApi.removeSession(this.deleteTarget.id)
        this.deleteTarget = null
        if (this.items.length === 1 && this.page > 1) this.page -= 1
        await this.load()
      } catch (error) { this.errorMessage = error.message || '会话删除失败' }
      finally { this.deleting = false }
    },
    dateLabel(value) { return value ? new Date(value).toLocaleString('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }) : '—' },
  },
}
</script>

<template>
  <AppShell>
    <section class="page-heading"><div><p class="eyebrow">可继续的分析上下文</p><h1>分析会话</h1><p class="page-intro">回到之前的问题与执行证据，继续分析同一份数据。</p></div><el-button type="primary" @click="$router.push('/datasets')"><el-icon><Plus /></el-icon>从数据集开始</el-button></section>
    <div v-if="errorMessage" class="inline-error" role="alert"><span>{{ errorMessage }}</span><el-button text type="primary" @click="load"><el-icon><Refresh /></el-icon>重试</el-button></div>
    <section class="panel sessions-panel">
      <div class="list-toolbar"><div><h2>最近会话</h2><span class="list-count">{{ total }} 个会话</span></div><el-input v-model="searchText" clearable placeholder="搜索会话或数据集" aria-label="搜索会话或数据集" /></div>
      <div v-if="!loading && !items.length" class="empty-state"><span class="empty-icon"><el-icon><Clock /></el-icon></span><h2>还没有分析会话</h2><p>从一个已解析的数据集开始提问。</p><el-button type="primary" @click="$router.push('/datasets')">查看数据集</el-button></div>
      <div v-else class="session-list" v-loading="loading">
        <article v-for="session in items" :key="session.id" class="session-card">
          <button type="button" class="session-main" @click="openSession(session)"><span class="session-icon"><el-icon><Files /></el-icon></span><span class="session-copy"><strong>{{ session.title || '新分析' }}</strong><small>{{ session.last_question || '尚未提交分析问题' }}</small><span class="session-data">{{ session.dataset_name || '未选择数据集' }} · {{ session.message_count }} 条消息</span></span></button>
          <div class="session-actions"><time>{{ dateLabel(session.updated_at) }}</time><el-button text type="primary" @click="openSession(session)">继续分析</el-button><el-button text type="danger" aria-label="删除会话" @click="deleteTarget = session"><el-icon><Delete /></el-icon></el-button></div>
        </article>
      </div>
      <el-pagination v-if="total > pageSize" v-model:current-page="page" :page-size="pageSize" :total="total" layout="prev, pager, next" @current-change="load" />
    </section>
    <el-dialog v-model="deleteDialogVisible" title="删除分析会话" width="min(440px, 92vw)" :close-on-click-modal="false"><p>删除后，该会话的消息和分析证据将一并移除；数据集文件会保留。</p><template #footer><el-button @click="deleteTarget = null">取消</el-button><el-button type="danger" :loading="deleting" @click="removeSession">确认删除</el-button></template></el-dialog>
  </AppShell>
</template>
