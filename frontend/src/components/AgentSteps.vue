<script>
const labels = { pending: '等待执行', running: '执行中', succeeded: '已完成', partial: '部分完成', failed: '失败', skipped: '未执行',
  PENDING: '等待执行', READY: '可以执行', RUNNING: '执行中', COMPLETED: '已完成', FAILED: '失败', SKIPPED: '跳过', WAITING: '等待补充', CANCELLED: '已取消' }
export default {
  name: 'AgentSteps',
  props: { trace: { type: Object, default: null }, calls: { type: Array, default: () => [] } },
  computed: { steps() { return ['2.0', '3.0'].includes(this.trace?.plan?.version) ? this.trace.plan.steps || [] : (this.trace?.steps?.length ? this.trace.steps : this.calls) } },
  methods: {
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
    <p v-if="trace?.plan?.intent">{{ trace.plan.intent }}</p>
    <p v-if="!steps.length" class="caption">提交后将显示已保存的执行步骤。</p>
    <article v-for="(step, index) in steps" :key="step.step_id || step.call_id || step.tool_call_id || index" class="tool-evidence">
      <div class="tool-evidence-title"><code>{{ step.tool_name }}</code><span>{{ duration(step) }} ms</span></div>
      <p>{{ statusLabel(step.status) }} · {{ step.result_summary || step.summary || '' }}</p>
      <p v-if="trace?.plan?.version === '3.0'" class="caption">数据：{{ step.input_alias }}<span v-if="step.depends_on?.length"> · 依赖：{{ step.depends_on.join('、') }}</span><span v-if="step.exploration_parent"> · 探索来源：{{ step.exploration_parent }}</span></p>
      <p v-if="step.error_message || step.error?.message" role="alert">{{ step.error_message || step.error.message }}</p>
      <details><summary>查看参数</summary><pre>{{ JSON.stringify(step.parameters || step.arguments || {}, null, 2) }}</pre></details>
    </article>
  </section>
</template>
