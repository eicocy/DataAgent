import { ElMessageBox } from 'element-plus'
import { datasetApi } from '../api/datasets'
// 预览和发布共享固定快照。输入变化/路由离开使旧响应失效，发布重试保持同一请求。
export default {
 props: { datasetId: Number, versionId: Number, columns: { type: Array, default: () => [] } }, emits: ['published'],
 data() { return { preview: null, loading: false, saving: false, error: '', notice: '', revision: 0, requestId: null, executionId: null, pollTimer: null, pollResolve: null, flowController: null } },
 watch: { payload: { deep: true, handler() { this.invalidate() } } },
 beforeUnmount() { this.revision++; this.flowController?.abort(); clearTimeout(this.pollTimer); this.pollResolve?.() },
 methods: {
  invalidate() { this.revision++; this.preview = null; this.requestId = null; this.executionId = null; this.notice = ''; this.flowController?.abort(); clearTimeout(this.pollTimer); this.pollResolve?.(); this.loading = false; this.saving = false },
  async previewChanges() {
   if (this.loading || this.saving) return
   const token = ++this.revision; const controller = new AbortController(); this.flowController = controller; this.preview = null; this.loading = true; this.error = ''; this.notice = ''
   try { const result = await datasetApi[`${this.flow}Preview`](this.datasetId, this.payload, { signal: controller.signal }); if (token === this.revision) { this.preview = result; this.requestId = crypto.randomUUID() } }
   catch (error) { if (token === this.revision) this.error = error.message || '预览失败，请检查选择后重试。' }
   finally { if (token === this.revision) this.loading = false }
  },
  async saveVersion() {
   if (this.saving || !this.preview || this.loading) return
   const token = this.revision; this.saving = true; this.error = ''; const controller = this.flowController || new AbortController(); this.flowController = controller
   try {
    if (!this.executionId) {
     await ElMessageBox.confirm(`将版本 ${this.versionId} 的预览结果保存为新版本，原版本保留。`, '保存为新版本', { confirmButtonText: '保存为新版本', cancelButtonText: '返回核对', type: 'info' })
     if (token !== this.revision) return
     const accepted = await datasetApi[`${this.flow}Confirm`](this.datasetId, { ...this.payload, confirmed: true, preview_hash: this.preview.preview_hash, request_id: this.requestId }, { signal: controller.signal }); if (token !== this.revision) return; this.executionId = accepted.execution_id
    }
    const deadline = Date.now() + 120000
    while (token === this.revision && Date.now() < deadline) {
     const state = await datasetApi[`${this.flow}Status`](this.datasetId, this.executionId, { signal: controller.signal }); if (token !== this.revision) return
     if (state.status === 'succeeded') { this.notice = `已保存新版本 ${state.output_version?.version_number ?? state.output_version?.id}`; this.$emit('published', state.output_version); this.preview = null; return }
     if (['failed', 'cancelled'].includes(state.status)) { throw new Error(`${state.error?.code || '发布失败'}：${state.error?.message || '请检查数据和预览后重试。'}`) }
     await new Promise(resolve => { this.pollResolve = resolve; this.pollTimer = setTimeout(resolve, 1000) })
    }
    if (token === this.revision) this.error = '任务仍在处理，点击保存继续查询同一个任务。'
   } catch (error) { if (token === this.revision && !['cancel','close'].includes(error)) this.error = error.status === 409 || error.response?.status === 409 ? `版本冲突：${error.message}。请刷新版本并重新预览。` : error.message || '保存失败，保留当前选择后重试。' }
   finally { if (token === this.revision) this.saving = false }
  },
 },
}
