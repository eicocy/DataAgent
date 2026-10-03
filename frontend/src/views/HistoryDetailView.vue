<script>
import { ArrowLeft, Refresh } from '@element-plus/icons-vue'

import AppShell from '../components/AppShell.vue'
import AnalysisResult from '../components/AnalysisResult.vue'
import AgentSteps from '../components/AgentSteps.vue'
import { historyApi } from '../api/history'

export default {
  name: 'HistoryDetailView',
  components: { AppShell, ArrowLeft, AnalysisResult, AgentSteps, Refresh },
  props: { recordId: { type: String, required: true } },
  data() { return { record: null, loading: false, errorMessage: '' } },
  created() { this.load() },
  watch: { recordId() { this.load() } },
  methods: {
    async load() {
      this.loading = true; this.errorMessage = ''
      try { this.record = await historyApi.detail(this.recordId) }
      catch (error) { this.errorMessage = error.message || '分析记录加载失败' }
      finally { this.loading = false }
    },
    retryAnalysis() {
      this.$router.push({ name: 'analysis', query: { datasetId: this.record.dataset.id, question: this.record.question, run: '1' } })
    },
    showValue(value) { return value === null || value === undefined ? '—' : String(value) },
    dateLabel(value) { return value ? new Date(value).toLocaleString('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }) : '—' },
  },
}
</script>

<template>
  <AppShell>
    <div v-if="errorMessage" class="inline-error" role="alert"><span>{{ errorMessage }}</span><el-button text type="primary" @click="load"><el-icon><Refresh /></el-icon>重试</el-button></div>
    <template v-if="record">
      <section class="page-heading history-detail-heading"><div><el-button text @click="$router.push('/history')"><el-icon><ArrowLeft /></el-icon>返回历史</el-button><p class="eyebrow">分析记录 #{{ record.id }}</p><h1>{{ record.question }}</h1><p class="page-intro">{{ record.dataset.original_name }} · {{ dateLabel(record.created_at) }} · {{ record.execution_time_ms ?? '—' }} ms</p></div><el-button type="primary" @click="retryAnalysis">再次分析</el-button></section>
      <section v-if="record.final_answer" class="panel history-answer"><p class="eyebrow">模型总结</p><p>{{ record.final_answer }}</p></section>
      <section v-else-if="record.status === 'partial'" class="partial-note history-partial">分析部分完成；下方保留已完成步骤和计算证据。</section>
      <section v-if="record.error_message" class="message-error" role="alert">{{ record.error_message }}</section>
      <section class="panel history-evidence-panel"><div class="evidence-panel-heading"><span class="evidence-dot"></span><div><h2>Tool 执行证据</h2><p>{{ record.primary_tool_name || '没有成功的 Tool 调用' }}</p></div></div>
        <AgentSteps :calls="record.tool_calls || []" /><AnalysisResult :evidence="{ ...record, record_id: record.id }" />
      </section>
    </template>
    <section v-else-if="loading" class="panel analysis-loading"><span class="large-loader"></span><h2>正在加载记录</h2></section>
  </AppShell>
</template>
