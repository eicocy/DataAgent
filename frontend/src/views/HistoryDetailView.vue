<script>
import { ArrowLeft, Clock, DataAnalysis, Document, Refresh, Timer } from '@element-plus/icons-vue'

import AppShell from '../components/AppShell.vue'
import AnalysisResult from '../components/AnalysisResult.vue'
import AgentSteps from '../components/AgentSteps.vue'
import { historyApi } from '../api/history'

export default {
  name: 'HistoryDetailView',
  components: { AppShell, ArrowLeft, AnalysisResult, AgentSteps, Clock, DataAnalysis, Document, Refresh, Timer },
  props: { recordId: { type: String, required: true } },
  data() { return { record: null, loading: false, errorMessage: '' } },
  created() { this.load() },
  watch: { recordId() { this.load() } },
  computed: {
    // 报告任务与分析共用历史记录，但内部操作标识不应成为用户问题。
    isReportTask() { return this.record?.intent_summary === 'REPORT_GENERATION' || /^REPORT_(CREATE|EXPORT):/.test(this.record?.question || '') },
    reportOperation() { return this.record?.report?.operation || (this.record?.question?.startsWith('REPORT_EXPORT:') ? 'export' : 'create') },
    recordTitle() { return this.isReportTask ? (this.record.question.replace(/^REPORT_(CREATE|EXPORT):\s*/, '') || '数据分析报告') : this.record?.question },
    recordKind() { return this.isReportTask ? (this.reportOperation === 'export' ? '报告导出' : '报告生成') : '数据分析' },
    summaryTitle() { return this.isReportTask ? `${this.recordKind}结果` : '分析结论' },
    reportVersion() {
      const value = this.record?.report?.report?.version ?? (this.reportOperation === 'export' ? this.record?.report?.version : null)
      return typeof value === 'number' ? value : null
    },
    reportSectionCount() { return this.record?.report?.report?.document?.sections?.length || 0 },
    statusLabel() { return ({ succeeded: '已完成', partial: '部分完成', failed: '失败', cancelled: '已取消', pending: '等待中', running: '处理中' })[this.record?.status] || '状态未知' },
    statusType() { return this.record?.status === 'succeeded' ? 'success' : this.record?.status === 'failed' ? 'danger' : this.record?.status === 'partial' ? 'warning' : 'info' },
    durationLabel() {
      const value = this.record?.execution_time_ms
      if (value === null || value === undefined) return ''
      return value < 1000 ? `${value} ms` : `${(value / 1000).toLocaleString('zh-CN', { maximumFractionDigits: 2 })} 秒`
    },
    showEvidence() { return !this.isReportTask || !!this.record?.tool_calls?.length },
  },
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
    returnToSession() {
      this.$router.push({ name: 'analysis', params: { sessionId: this.record.session_id }, query: { datasetId: this.record.dataset.id } })
    },
    showValue(value) { return value === null || value === undefined ? '—' : String(value) },
    dateLabel(value) { return value ? new Date(value).toLocaleString('zh-CN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Shanghai' }) : '时间未记录' },
  },
}
</script>

<template>
  <AppShell>
    <div v-if="errorMessage" class="inline-error" role="alert"><span>{{ errorMessage }}</span><el-button text type="primary" @click="load"><el-icon><Refresh /></el-icon>重试</el-button></div>
    <template v-if="record">
      <div class="history-back"><el-button text native-type="button" @click="$router.push('/history')"><el-icon><ArrowLeft /></el-icon><span>返回历史</span></el-button></div>
      <section class="page-heading history-detail-heading">
        <div class="history-heading-copy">
          <div class="history-record-label"><span>{{ recordKind }}</span><span class="history-record-id">#{{ record.id }}</span><el-tag :type="statusType" effect="light" size="small">{{ statusLabel }}</el-tag></div>
          <h1>{{ recordTitle }}</h1>
          <div class="history-meta">
            <span><el-icon><Document /></el-icon>{{ record.dataset.original_name }}</span>
            <span><el-icon><Clock /></el-icon><time :datetime="record.created_at">{{ dateLabel(record.created_at) }}</time></span>
            <span v-if="durationLabel"><el-icon><Timer /></el-icon>{{ durationLabel }}</span>
          </div>
        </div>
        <el-button v-if="isReportTask && record.session_id" type="primary" native-type="button" @click="returnToSession">返回会话</el-button>
        <el-button v-else-if="!isReportTask" type="primary" native-type="button" @click="retryAnalysis">再次分析</el-button>
      </section>
      <section v-if="record.final_answer" class="panel history-answer" aria-labelledby="history-summary-title">
        <header class="history-answer-heading"><span class="history-answer-icon"><el-icon><Document v-if="isReportTask" /><DataAnalysis v-else /></el-icon></span><h2 id="history-summary-title">{{ summaryTitle }}</h2></header>
        <p class="history-answer-body">{{ record.final_answer }}</p>
        <div v-if="isReportTask && record.status === 'succeeded'" class="history-report-note">
          <span v-if="reportVersion">版本 {{ reportVersion }}</span><span v-if="reportSectionCount">{{ reportSectionCount }} 个章节</span>
          <p v-if="reportOperation === 'export'">导出文件已保存，可在「文件与工件」中查看。</p>
          <p v-else-if="record.session_id">报告预览已保存，可返回会话继续分析数据。</p>
        </div>
      </section>
      <section v-else-if="record.status === 'partial'" class="partial-note history-partial">分析部分完成；下方保留已完成步骤和计算证据。</section>
      <section v-if="record.error_message" class="message-error" role="alert">{{ record.error_message }}</section>
      <section v-if="showEvidence" class="panel history-evidence-panel"><div class="evidence-panel-heading"><span class="evidence-dot"></span><div><h2>Tool 执行证据</h2><p>{{ record.primary_tool_name || '已保存的执行步骤与计算结果' }}</p></div></div>
        <AgentSteps :calls="record.tool_calls || []" /><AnalysisResult :evidence="{ ...record, record_id: record.id }" />
      </section>
    </template>
    <section v-else-if="loading" class="panel analysis-loading"><span class="large-loader"></span><h2>正在加载记录</h2></section>
  </AppShell>
</template>
