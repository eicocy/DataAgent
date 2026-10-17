<script>
import { diagnosticCopy, stageLabels } from '../utils/errorInfo'

// 统一失败原因和人工排查信息；重试行为交由所属业务页面处理。
export default {
  name: 'ErrorInfoPanel',
  props: {
    info: { type: Object, default: null }, message: { type: String, default: '' },
    retryable: Boolean, retryLabel: { type: String, default: '重试' },
  },
  emits: ['retry'],
  data() { return { copied: false, copyFailed: false } },
  computed: {
    visible() { return Boolean(this.info || this.message) },
    copyText() { return diagnosticCopy(this.info || { reason: this.message, legacy: true }) },
    fields() {
      const info = this.info || {}
      const seconds = value => value == null ? '未记录' : `${value} 秒`
      return [
        ['错误码', info.code], ['细分原因', info.reason_code], ['失败阶段', stageLabels[info.stage] || info.stage],
        ['操作', info.operation], ['步骤', info.step_id], ['工具', info.tool_name],
        ['阶段耗时', seconds(info.stage_elapsed_seconds)], ['任务耗时', seconds(info.task_elapsed_seconds)],
        ['排队耗时', seconds(info.queue_elapsed_seconds)], ['触发阈值', seconds(info.limit_seconds)],
        ['超时范围', { task: '任务总预算', stage: '单次操作', http: '浏览器请求' }[info.timeout_scope] || info.timeout_scope],
        ['请求关联编号', info.request_id], ['分析幂等编号', info.analysis_request_id],
        ['分析记录', info.record_id], ['后台任务', info.job_id], ['数据版本', info.dataset_version_id],
        ['校验规则', info.validation_rule],
        ['相关字段', info.column], ['期望类型', info.expected_type], ['实际类型', info.actual_type],
      ]
    },
  },
  watch: {
    // 切换错误时清除上一条复制状态。
    info() { this.copied = false; this.copyFailed = false },
  },
  methods: {
    async copy() {
      this.copied = false; this.copyFailed = false
      try { await navigator.clipboard.writeText(this.copyText); this.copied = true }
      catch { this.copyFailed = true; this.$nextTick(() => this.$refs.copyText?.select()) }
    },
  },
}
</script>

<template>
  <section v-if="visible" class="error-info-panel" aria-label="错误原因与诊断信息">
    <p class="error-reason" role="alert">{{ info?.reason || message }}</p>
    <p v-if="info?.suggestion" class="error-suggestion">建议：{{ info.suggestion }}</p>
    <p v-if="info?.preserved_artifact_ids?.length" class="error-suggestion">已保留 {{ info.preserved_artifact_ids.length }} 项成果，可继续查看。</p>
    <details>
      <summary>查看详细原因</summary>
      <p v-if="!info || info.legacy" class="error-suggestion">历史信息有限，未记录的诊断字段无法补造。</p>
      <dl><template v-for="[label, value] in fields" :key="label"><dt>{{ label }}</dt><dd>{{ value ?? '未记录' }}</dd></template></dl>
      <ul v-if="info?.field_errors?.length"><li v-for="(field, index) in info.field_errors" :key="index">{{ field.path }}：{{ field.rule }}</li></ul>
      <button type="button" @click="copy">{{ copied ? '已复制' : '复制诊断信息' }}</button>
      <p v-if="copyFailed" role="status">无法自动复制，请选取下方诊断文本手动复制。</p>
      <textarea v-if="copyFailed" ref="copyText" readonly :value="copyText" aria-label="可手动复制的诊断信息" />
    </details>
    <button v-if="retryable" type="button" class="retry-action" @click="$emit('retry')">{{ retryLabel }}</button>
  </section>
</template>

<style scoped>
.error-info-panel { padding: 12px 14px; margin: 10px 0; border: 1px solid #e6b4ac; border-radius: 10px; background: #fff8f6; color: #70372f; font-size: 12px; overflow-wrap: anywhere; }
.error-reason { font-weight: 600; margin: 0 0 6px; white-space: pre-wrap; }
.error-suggestion { margin: 6px 0; line-height: 1.6; }
summary, button { cursor: pointer; }
summary { padding: 6px 0; }
dl { display: grid; grid-template-columns: minmax(80px, 110px) minmax(0, 1fr); gap: 7px 12px; }
dt { color: #7c615d; } dd { margin: 0; }
button { border: 1px solid #d8ada5; border-radius: 6px; background: white; padding: 5px 10px; color: inherit; }
.retry-action { margin-top: 8px; }
textarea { width: 100%; min-height: 150px; font-size: 11px; }
</style>
