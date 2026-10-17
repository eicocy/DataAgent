<script>
import ErrorInfoPanel from './ErrorInfoPanel.vue'
const toolLabels = { dataset_overview: '查看数据概况', get_dataset_info: '查看数据概况', preview_data: '预览数据',
  filter_rows: '筛选数据', filter_data: '筛选数据', aggregate: '汇总指标', aggregate_data: '汇总指标',
  groupby_aggregate: '按维度汇总', group_by_analysis: '按维度汇总', descriptive_statistics: '计算描述统计',
  top_n: '提取排名靠前的数据', bottom_n: '提取排名靠后的数据',
  column_summary: '统计字段', missing_value_analysis: '检查缺失值', duplicate_analysis: '检查重复数据',
  generate_chart: '绘制图表', forecast: '生成预测', sql_query: '查询数据', sort_data: '排序结果' }
const labels = { pending: '等待执行', running: '执行中', succeeded: '已完成', partial: '部分完成', failed: '失败', skipped: '未执行',
  PENDING: '等待执行', READY: '可以执行', RUNNING: '执行中', COMPLETED: '已完成', FAILED: '失败', SKIPPED: '跳过', WAITING: '等待补充', CANCELLED: '已取消' }
export default {
  name: 'AgentSteps',
  components: { ErrorInfoPanel },
  props: { trace: { type: Object, default: null }, calls: { type: Array, default: () => [] }, compact: Boolean },
  emits: ['diagnostic'],
  computed: { steps() { return ['2.0', '3.0'].includes(this.trace?.plan?.version) ? this.trace.plan.steps || [] : (this.trace?.steps?.length ? this.trace.steps : this.calls) } },
  methods: {
    stepLabel(step) { return toolLabels[step.tool_name] || '执行分析步骤' },
    stepError(step) { return step.error_info || (this.trace?.steps || this.calls).find(item => item.step_id === step.step_id && item.error_info)?.error_info || (step.status === 'FAILED' ? this.trace?.error_info : null) },
    statusLabel(status) { return labels[status] || status || '等待执行' },
    duration(step) {
      const call = [...(this.trace?.steps || this.calls)].reverse().find(item => item.step_id === step.step_id)
      if (call?.duration_ms != null) return call.duration_ms
      if (step.finished_at && step.started_at) return Math.max(0, Date.parse(step.finished_at) - Date.parse(step.started_at))
      return step.duration_ms ?? step.execution_time_ms ?? 0
    },
  },
}
</script>
<template>
  <section aria-label="分析步骤" aria-live="polite">
    <p v-if="!compact && trace?.plan?.goal">{{ trace.plan.goal }}</p>
    <p v-if="!compact && !steps.length" class="caption">提交后将显示已保存的执行步骤。</p>
    <article v-for="(step, index) in steps" :key="step.step_id || step.call_id || step.tool_call_id || index" class="tool-evidence">
      <div class="tool-evidence-title"><strong>{{ stepLabel(step) }}</strong><span>{{ duration(step) }} ms</span></div>
      <p>{{ statusLabel(step.status) }}<span v-if="!compact"> · {{ step.result_summary || step.summary || '' }}</span></p>
      <p v-if="trace?.plan?.version === '3.0'" class="caption">数据：{{ step.input_alias }}<span v-if="step.depends_on?.length"> · 依赖：{{ step.depends_on.join('、') }}</span><span v-if="step.exploration_parent"> · 探索来源：{{ step.exploration_parent }}</span></p>
      <button v-if="compact && (stepError(step) || step.status === 'FAILED' || step.status === 'failed')" type="button" class="step-diagnostic-link" @click="$emit('diagnostic')">查看失败原因</button>
      <ErrorInfoPanel v-if="!compact" :info="stepError(step)" :message="step.error_message || step.error?.message || ''" />
      <details><summary>查看工具与参数</summary><code>{{ step.tool_name }}</code><pre>{{ JSON.stringify(step.parameters || step.arguments || {}, null, 2) }}</pre></details>
    </article>
  </section>
</template>
