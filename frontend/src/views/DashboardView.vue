<script>
import { dashboardApi } from '../api/dashboard'
import AppShell from '../components/AppShell.vue'
import { DataAnalysis, Files, Plus, UploadFilled } from '@element-plus/icons-vue'

export default {
  name: 'DashboardView',
  components: { AppShell, DataAnalysis, Files, Plus, UploadFilled },
  data() {
    return { summary: null, loading: true, errorMessage: '' }
  },
  computed: {
    metrics() {
      return [
        { label: '数据集', value: this.summary?.dataset_count ?? '—', detail: `${this.summary?.ready_dataset_count ?? 0} 个可分析`, icon: 'files' },
        { label: '分析记录', value: this.summary?.analysis_count ?? '—', detail: '可追溯计算结果', icon: 'analysis' },
        { label: '分析会话', value: this.summary?.session_count ?? '—', detail: '可继续的分析上下文', icon: 'analysis' },
      ]
    },
  },
  created() {
    this.loadSummary()
  },
  methods: {
    async loadSummary() {
      this.loading = true
      this.errorMessage = ''
      try {
        this.summary = await dashboardApi.summary()
      } catch (error) {
        this.errorMessage = error.message || '工作区概览加载失败'
      } finally {
        this.loading = false
      }
    },
  },
}
</script>

<template>
  <AppShell>
    <section class="page-heading">
      <div><p class="eyebrow">工作区概览</p><h1>Dashboard</h1><p class="page-intro">从你的数据出发，开始一段可追溯的分析。</p></div>
      <el-button type="primary" size="large" @click="$router.push('/datasets/upload')"><el-icon><Plus /></el-icon>上传数据</el-button>
    </section>
    <div v-if="errorMessage" class="inline-error" role="alert"><span>{{ errorMessage }}</span><el-button text type="primary" @click="loadSummary">重试</el-button></div>
    <section class="metric-grid" aria-label="工作区指标">
      <article v-for="metric in metrics" :key="metric.label" class="metric-card">
        <div class="metric-top"><span>{{ metric.label }}</span><span class="metric-icon"><el-icon><Files v-if="metric.icon === 'files'" /><DataAnalysis v-else /></el-icon></span></div>
        <div class="metric-value">{{ loading ? '…' : metric.value }}</div><p>{{ metric.detail }}</p>
      </article>
    </section>
    <section class="dashboard-lower">
      <article class="panel welcome-panel">
        <div class="panel-overline"><span class="evidence-dot"></span> 可追溯分析</div>
        <h2>让结论带上证据。</h2>
        <p>DataLens 会把自然语言问题交给 Agent，再由受控工具对你的数据进行真实计算。每次分析都能回看工具、参数和结果。</p>
        <div class="evidence-flow" aria-label="分析步骤"><span>问题</span><i>→</i><span>Agent</span><i>→</i><span>Tool 计算</span><i>→</i><span>结果</span></div>
        <el-button class="start-analysis" @click="$router.push('/analysis')">打开分析工作台 <span aria-hidden="true">→</span></el-button>
      </article>
      <article class="panel quick-panel">
        <div class="panel-title"><h2>快速开始</h2><span>两步开始分析</span></div>
        <button class="quick-action" type="button" @click="$router.push('/datasets/upload')">
          <span class="quick-icon upload-icon"><el-icon><UploadFilled /></el-icon></span><span class="quick-copy"><strong>上传 CSV 或 Excel</strong><small>解析字段并查看数据预览</small></span><span class="quick-arrow">↗</span>
        </button>
        <button class="quick-action" type="button" @click="$router.push('/datasets')">
          <span class="quick-icon data-icon"><el-icon><Files /></el-icon></span><span class="quick-copy"><strong>查看数据集</strong><small>管理已上传的数据文件</small></span><span class="quick-arrow">↗</span>
        </button>
        <div class="quick-footnote">支持 CSV、XLSX，单个文件最大 20 MB。</div>
        <div class="recent-analysis-heading"><h3>最近分析</h3><button type="button" @click="$router.push('/history')">查看全部 →</button></div>
        <button v-for="record in summary?.recent_analyses || []" :key="record.id" type="button" class="recent-analysis-item" @click="$router.push({ name: 'history-detail', params: { recordId: record.id } })"><span><strong>{{ record.question }}</strong><small>{{ record.dataset_name }} · {{ record.status === 'partial' ? '部分完成' : record.status === 'failed' ? '失败' : '已完成' }}</small></span><span aria-hidden="true">→</span></button>
        <p v-if="!loading && !summary?.recent_analyses?.length" class="recent-empty">完成一次分析后，记录会显示在这里。</p>
      </article>
    </section>
  </AppShell>
</template>
