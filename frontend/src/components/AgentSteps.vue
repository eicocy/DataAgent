<script>
const labels = { pending: '等待执行', running: '执行中', succeeded: '已完成', partial: '部分完成', failed: '失败', skipped: '未执行',
  PENDING: '等待执行', READY: '可以执行', RUNNING: '执行中', COMPLETED: '已完成', FAILED: '失败', SKIPPED: '跳过', WAITING: '等待补充', CANCELLED: '已取消' }
export default {
  name: 'AgentSteps',
  props: { trace: { type: Object, default: null }, calls: { type: Array, default: () => [] } },
  computed: { steps() { return this.trace?.plan?.version === '2.0' ? this.trace.plan.steps || [] : (this.trace?.steps?.length ? this.trace.steps : this.calls) } },
  methods: { statusLabel(status) { return labels[status] || status || '等待执行' } },
}
</script>
<template>
  <section aria-label="分析步骤" aria-live="polite">
    <p v-if="trace?.plan?.intent">{{ trace.plan.intent }}</p>
    <p v-if="!steps.length" class="caption">提交后将显示已保存的执行步骤。</p>
    <article v-for="(step, index) in steps" :key="step.step_id || step.call_id || step.tool_call_id || index" class="tool-evidence">
      <div class="tool-evidence-title"><code>{{ step.tool_name }}</code><span>{{ step.duration_ms ?? step.execution_time_ms ?? 0 }} ms</span></div>
      <p>{{ statusLabel(step.status) }} · {{ step.result_summary || step.summary || '' }}</p>
      <p v-if="step.error_message || step.error?.message" role="alert">{{ step.error_message || step.error.message }}</p>
      <details><summary>查看参数</summary><pre>{{ JSON.stringify(step.parameters || step.arguments || {}, null, 2) }}</pre></details>
    </article>
  </section>
</template>
