<script>
import { ElButton } from 'element-plus'
import { filesApi } from '../api/files'
// 候选内容只能来自服务端；人工确认后才交给数据集解析流程。
export default {
 name: 'DocumentCandidatePreview', components: { ElButton },
 props: { fileId: Number, sessionId: Number }, emits: ['ready'],
 data() { return { file: null, candidate: '', extraction: null, verified: false, hasHeader: true, name: '', loading: false, saving: false, error: '', notice: '', controller: null, requestId: null, revision: 0 } },
 watch: { fileId: { immediate: true, handler() { this.load() } }, candidate() { this.loadCandidate() }, hasHeader() { this.invalidate() }, name() { this.invalidate() } },
 beforeUnmount() { this.controller?.abort(); this.revision++ },
 methods: {
  invalidate() { this.verified = false; this.requestId = null; this.notice = '' },
  async load() {
   this.revision++; this.saving = false
   this.controller?.abort(); const controller = new AbortController(); this.controller = controller
   this.loading = true; this.error = ''; this.file = null; this.candidate = ''; this.extraction = null; this.invalidate()
   try { const file = await filesApi.detail(this.fileId, { signal: controller.signal }); if (controller !== this.controller || controller.signal.aborted) return; this.file = file; this.candidate = file.candidates?.[0]?.id || '' }
   catch (error) { if (controller === this.controller && !controller.signal.aborted) this.error = error.message || '文档读取失败，请重试。' }
   finally { if (controller === this.controller) this.loading = false }
  },
  async loadCandidate() {
   const token = ++this.revision; this.invalidate(); this.extraction = null; if (!this.candidate) return
   this.loading = true; this.error = ''
   try { const result = await filesApi.extraction(this.fileId, this.candidate, { offset: 0, limit: 20 }, { signal: this.controller.signal }); if (token === this.revision) this.extraction = result }
   catch (error) { if (token === this.revision && !this.controller.signal.aborted) this.error = error.message || '候选表读取失败' }
   finally { if (token === this.revision) this.loading = false }
  },
  location(value) { if (!value) return '原文'; return [value.page ? `第 ${value.page} 页` : '', value.table_index !== undefined ? `第 ${value.table_index + 1} 张表` : '', value.bbox ? `区域 ${value.bbox.join(' / ')}` : ''].filter(Boolean).join(' · ') || '原文' },
  async confirm() {
   if (this.saving || !this.verified || !this.extraction || this.loading) return
   this.requestId ||= crypto.randomUUID(); const token = this.revision; this.saving = true; this.error = ''
   try { const result = await filesApi.confirm(this.fileId, this.candidate, { confirmed: true, request_id: this.requestId, has_header: this.hasHeader, ...(this.name.trim() ? { name: this.name.trim() } : {}), ...(this.sessionId ? { session_id: this.sessionId } : {}) }, { signal: this.controller.signal }); if (token !== this.revision) return; this.notice = '已受理候选表，数据集解析完成后可用于分析。'; this.$emit('ready', result.dataset) }
   catch (error) { if (token === this.revision && !this.controller.signal.aborted) this.error = error.message || '确认失败，保留核对结果后重试。' }
   finally { if (token === this.revision) this.saving = false }
  },
 },
}
</script>
<template>
 <section class="document-candidate" aria-label="文档候选表确认" :aria-busy="loading || saving">
  <h3>{{ file?.name || '文档预览' }}</h3>
  <p v-if="loading" role="status">正在读取文档和候选表…</p>
  <p v-if="error" class="inline-error" role="alert">{{ error }} <ElButton :disabled="saving" @click="file ? loadCandidate() : load()">重试读取</ElButton></p>
  <p v-if="file?.status === 'parsing'" role="status">文档正在解析，请稍后刷新。<ElButton @click="load">刷新解析状态</ElButton></p>
  <p v-if="file?.status === 'failed'" role="alert">{{ file.error_message || '解析失败，请检查文件内容后重新上传。' }}</p>
  <details v-if="file?.preview"><summary>查看提取原文</summary><pre class="document-text">{{ file.preview }}</pre><p v-if="file.preview_truncated">原文预览已截断。</p></details>
  <p v-if="file?.status === 'ready' && !file.candidates?.length">未识别到表格。文档已作为附件保存；可在文件页面查看，暂不能作为数值分析输入。</p>
  <template v-if="file?.candidates?.length">
   <label>候选表<select v-model="candidate" :disabled="saving"><option v-for="item in file.candidates" :key="item.id" :value="item.id">{{ location(item.location) }} · {{ item.row_count }} 行</option></select></label>
   <p>原文位置：{{ location(file.candidates.find(item => item.id === candidate)?.location) }}</p>
   <p v-if="extraction">共 {{ extraction.total }} 行（包含可能的表头），显示最多 20 行。请核对表头与内容。</p>
   <div v-if="extraction" class="table-wrap phase3-table"><table class="data-table"><thead><tr><th v-for="column in extraction.columns" :key="column">{{ column }}</th></tr></thead><tbody><tr v-for="(row, index) in extraction.rows" :key="index"><td v-for="(cell, cellIndex) in row" :key="cellIndex">{{ cell }}</td></tr></tbody></table></div>
   <label><input v-model="hasHeader" type="checkbox" :disabled="saving" />第一行是表头</label>
   <label>数据集名称（可选）<input v-model="name" :disabled="saving" maxlength="200" /></label>
   <label><input v-model="verified" data-verification type="checkbox" :disabled="saving || !extraction" />我已核对原文位置、表头和样例数据</label>
   <ElButton data-confirm-document type="primary" :disabled="!verified || !extraction || loading" :loading="saving" @click="confirm">确认并创建数据集</ElButton>
  </template>
  <p v-if="notice" role="status">{{ notice }}</p>
 </section>
</template>
<style scoped>
.document-candidate { display: grid; gap: 12px; padding: 16px; border: 1px solid var(--line); border-radius: var(--radius-sm); }
label { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; } input, select { max-width: 100%; padding: 6px; border: 1px solid var(--line); border-radius: var(--radius-sm); }
.document-text { white-space: pre-wrap; max-height: 300px; overflow: auto; overflow-wrap: anywhere; }
</style>
