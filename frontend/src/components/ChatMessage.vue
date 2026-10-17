<script>
import SafeMarkdown from './SafeMarkdown.vue'
import AnalysisResult from './AnalysisResult.vue'
import AnalysisScope from './AnalysisScope.vue'
import AgentSteps from './AgentSteps.vue'
import ErrorInfoPanel from './ErrorInfoPanel.vue'
import { chatResults } from '../utils/chatResults'
export default {
  name: 'ChatMessage', components: { SafeMarkdown, AnalysisResult, AnalysisScope, AgentSteps, ErrorInfoPanel },
  props: { message: { type: Object, required: true }, busy: Boolean, datasets: { type: Array, default: () => [] }, sessionId: Number },
  emits: ['retry', 'preview', 'files', 'report', 'clarification'],
  data() { return { copied: false, copyFailed: false } },
  computed: {
    evidence() { return this.message.evidence },
    diagnostic() { return this.message.errorInfo || this.evidence?.error_info },
    failed() { return Boolean(this.message.error || this.diagnostic || this.evidence?.status === 'failed') },
    // 原始模型回复保持原文；服务端错误回退文案已在诊断面板出现时不再重复。
    showContent() { return this.message.content && !(this.failed && [this.evidence?.error_message, this.message.error].includes(this.message.content)) },
    hasResults() { const results = chatResults(this.evidence || {}); return Boolean(results.primary.length || results.more.length || this.evidence?.report?.warnings?.length) },
    units() { return (this.evidence?.analysis_context?.units || []).filter(item => item.unit || item.currency).map(item => `${item.column}：${[item.currency, item.unit].filter(Boolean).join(' ')}`) },
    canReport() { return this.hasResults && this.evidence?.record_id && this.evidence?.dataset_id && this.evidence?.dataset_version_id && ['succeeded', 'partial'].includes(this.evidence.status) },
    trace() { return { plan: this.evidence?.plan, steps: this.evidence?.tool_calls || [], error_info: this.diagnostic } },
    hasDetails() { return Boolean(this.evidence?.plan || this.evidence?.tool_calls?.length || this.evidence?.analysis_context || this.hasResults) },
  },
  methods: {
    async copy() {
      try { await navigator.clipboard.writeText(this.message.content || ''); this.copied = true }
      catch { this.copyFailed = true; this.$nextTick(() => this.$refs.copyText?.select()) }
    },
    showDiagnostic() {
      const element = this.$refs.diagnostic?.$el
      if (!element?.scrollIntoView) return
      element.scrollIntoView({ block: 'center' }); element.setAttribute('tabindex', '-1'); element.focus({ preventScroll: true })
    },
    closeMore(event) { event.currentTarget.closest('details')?.removeAttribute('open') },
  },
}
</script>
<template>
  <article class="chat-message" :class="`message-${message.role}`" :data-record-id="evidence?.record_id">
    <p v-if="message.role === 'user'" class="user-message-text">{{ message.content }}</p>
    <template v-else>
      <SafeMarkdown v-if="showContent" :content="message.content || ''" />
      <p v-if="evidence?.status === 'cancelled' && !failed" class="completion-note" role="status">任务已中断，已完成的结果仍可查看。</p>
      <p v-else-if="evidence?.status === 'partial' && !failed" class="completion-note" role="status">分析部分完成，已完成的结果仍可查看。</p>
      <p v-if="units.length" class="completion-note">单位：{{ units.join('；') }}</p>
      <AnalysisResult v-if="evidence && hasResults" :evidence="evidence" presentation="chat" @preview="$emit('preview', { ...$event, evidence })" />
      <div v-if="evidence?.agent_response?.clarification?.candidate_dataset_ids?.length" class="clarification-choices"><button v-for="id in evidence.agent_response.clarification.candidate_dataset_ids" :key="id" type="button" :disabled="busy" @click="$emit('clarification', id)">选择 {{ datasets.find(item => item.id === id)?.original_name || `数据集 #${id}` }}</button></div>
    </template>
    <ErrorInfoPanel v-if="failed" ref="diagnostic" :info="diagnostic" :message="message.error || evidence?.error_message || '分析失败，旧记录未保存详细原因。'" :retryable="!busy" :retry-label="['NETWORK_ERROR', 'HTTP_REQUEST_TIMEOUT'].includes(message.errorCode) ? '重新连接确认状态' : '保留问题并重试'" @retry="$emit('retry', message)" />
    <details v-if="message.role === 'assistant' && hasDetails" class="reply-details"><summary>数据与口径 · 查看步骤</summary><AnalysisScope :context="evidence.analysis_context" /><AgentSteps :trace="trace" :calls="evidence.tool_calls || []" compact @diagnostic="showDiagnostic" /><p class="caption"><span v-if="sessionId">会话 #{{ sessionId }} · </span>分析记录 #{{ evidence.record_id }}</p><details><summary>来源详情</summary><pre>{{ JSON.stringify({ plan: evidence.plan, tool_calls: evidence.tool_calls, report: evidence.report, tool_result: evidence.tool_result }, null, 2) }}</pre></details></details>
    <div v-if="message.role === 'assistant'" class="reply-actions">
      <button type="button" @click="copy">{{ copied ? '已复制' : '复制' }}</button>
      <button v-if="evidence?.record_id" type="button" @click="$emit('files', evidence)">下载</button>
      <details class="reply-more" @keydown.esc.prevent="$event.currentTarget.removeAttribute('open')"><summary>更多</summary><div class="reply-more-menu" @click="closeMore"><button v-if="canReport" type="button" :disabled="busy" @click="$emit('report', evidence)">生成报告</button><button v-if="evidence?.record_id" type="button" @click="$emit('files', evidence)">查看文件</button><button type="button" :disabled="busy" @click="$emit('retry', message)">重新分析</button></div></details>
    </div>
    <textarea v-if="copyFailed" ref="copyText" readonly :value="message.content" aria-label="可手动复制的回复" class="reply-copy-fallback" />
  </article>
</template>
<style scoped>
.chat-message { width: 100%; max-width: 760px; min-width: 0; margin: 0 auto 40px; padding: 0; border: 0; background: transparent; border-radius: 0; font-size: 15px; line-height: 1.75; }
.message-user { display: flex; flex-wrap: wrap; justify-content: flex-end; }
.user-message-text { width: fit-content; max-width: 85%; margin: 0; padding: 12px 18px; border-radius: 18px; background: #f2f4f7; white-space: pre-wrap; overflow-wrap: anywhere; }
.message-user > :not(.user-message-text) { width: 100%; }
.completion-note { margin: 12px 0; color: var(--muted); font-size: 13px; }
.reply-details { margin: 18px 0 12px; color: var(--muted); font-size: 12px; }
summary { cursor: pointer; width: fit-content; }
.reply-details > summary { padding: 6px 0; }
.reply-details pre { max-height: 360px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; }
.reply-actions { display: flex; align-items: center; gap: 16px; margin-top: 14px; color: var(--muted); font-size: 12px; }
.reply-actions button, .clarification-choices button, .step-diagnostic-link { padding: 5px 0; border: 0; color: inherit; background: transparent; font: inherit; cursor: pointer; }
.reply-actions button:hover { color: var(--ink); }
.reply-more { position: relative; }
.reply-more summary { list-style: none; padding: 5px 0; }
.reply-more summary::-webkit-details-marker { display: none; }
.reply-more-menu { position: absolute; z-index: 5; bottom: 100%; left: -12px; display: grid; min-width: 130px; padding: 6px; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); box-shadow: 0 6px 22px #26344912; }
.reply-more-menu button { text-align: left; padding: 8px 10px; border-radius: 6px; white-space: nowrap; }
.reply-more-menu button:hover { background: var(--canvas); }
button:focus-visible, summary:focus-visible { outline: 2px solid var(--brand); outline-offset: 3px; }
.reply-copy-fallback { width: 100%; min-height: 100px; margin-top: 10px; }
.chat-message :deep(.analysis-scope) { margin-top: 12px; }
@media (max-width: 600px) { .chat-message { margin-bottom: 32px; } .user-message-text { max-width: 92%; } }
</style>
