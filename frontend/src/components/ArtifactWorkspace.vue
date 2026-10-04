<script>
import { mapState } from 'pinia'
import { useWorkspaceStore } from '../stores/workspace'
import ArtifactPreview from './ArtifactPreview.vue'
import { reportsApi } from '../api/reports'
export default {
  name: 'ArtifactWorkspace', components: { ArtifactPreview },
  props: { sessionId: { type: Number, required: true } }, emits: ['report', 'reference'],
  data() { return { regenerating: false, regenerationError: '', actionToken: 0 } },
  computed: { ...mapState(useWorkspaceStore, ['items', 'reports', 'selected', 'selectedId', 'preview', 'loading', 'previewLoading', 'error', 'hasMore']) },
  watch: { sessionId() { this.actionToken++; this.regenerating = false; this.regenerationError = '' } },
  beforeUnmount() { this.actionToken++ },
  methods: {
    refresh() { return useWorkspaceStore().load(this.sessionId) },
    select(item) { this.regenerationError = ''; return useWorkspaceStore().select(item.id || item.artifact_id) },
    async regenerate() {
      if (!this.selectedId || this.regenerating) return
      const id = this.selectedId, token = ++this.actionToken, sid = this.sessionId
      this.regenerating = true; this.regenerationError = ''
      try { const item = await reportsApi.regenerate(id); if (token !== this.actionToken || sid !== this.sessionId) return; await this.refresh(); if (token === this.actionToken) await this.select(item) }
      catch (error) { if (token === this.actionToken) this.regenerationError = error.message || '重新生成失败，原成果已保留' }
      finally { if (token === this.actionToken) this.regenerating = false }
    },
    page(delta) { const store = useWorkspaceStore(); store.select(this.selectedId, {}, false, Math.max(0, (this.preview?.offset || 0) + delta * 100)) },
    loadMore() { return useWorkspaceStore().load(this.sessionId, {}, true) },
  },
}
</script>
<template>
  <section class="artifact-workspace" aria-label="会话成果">
    <header><h3>会话成果</h3><el-button size="small" :loading="loading" @click="refresh">刷新成果</el-button></header>
    <p v-if="error" role="alert">{{ error }} <el-button text @click="refresh">重试</el-button></p>
    <p v-if="loading && !items.length" role="status">正在恢复会话成果…</p>
    <p v-else-if="!items.length && !reports.length" class="caption">本会话还没有成果。分析完成后，结果、图表和报告会保存在这里。</p>
    <div class="artifact-choices"><button v-for="item in items" :key="item.id || item.artifact_id" type="button" :aria-pressed="selectedId === (item.id || item.artifact_id)" @click="select(item)"><span>{{ item.name || item.title }}</span><small>{{ item.type || item.artifact_type }} · {{ item.status === 'EXPIRED' ? '已过期' : item.expires_at ? '临时留存' : '长期保存' }}</small></button></div>
    <el-button v-if="hasMore" size="small" :loading="loading" @click="loadMore">加载更多成果</el-button>
    <div v-if="reports.length" class="report-choices"><el-button v-for="report in reports" :key="report.id" size="small" plain @click="$emit('report', report.id)">{{ report.title }} · v{{ report.version }}</el-button></div>
    <section v-if="selected" class="artifact-selected"><h4>{{ selected.name || selected.title }}</h4><p v-if="selected.status === 'EXPIRED'" role="status">原文件已清理，不能恢复或引用。可使用仍可用的固定输入重新分析。</p><template v-else><div class="artifact-actions"><a :href="selected.download_url">下载完整文件</a><el-button size="small" :loading="regenerating" @click="regenerate">重新生成副本</el-button><el-button v-if="['table','chart','dataset','report','pdf','word','excel'].includes(selected.type)" size="small" @click="$emit('reference', selected)">@ 引用</el-button></div><p v-if="selected.source_artifact_ids?.length" class="caption">来源成果 #{{ selected.source_artifact_ids.join('、#') }}</p><p v-if="previewLoading" role="status">正在读取预览…</p><ArtifactPreview v-else :preview="preview" :title="selected.name || selected.title" /><div v-if="preview && (preview.total > 100 || preview.kind === 'workbook')" class="artifact-actions"><el-button size="small" :disabled="!preview.offset" @click="page(-1)">上一页明细</el-button><span>预览 {{ (preview.offset || 0) + 1 }} 起</span><el-button size="small" :disabled="preview.total != null && (preview.offset || 0) + 100 >= preview.total" @click="page(1)">下一页明细</el-button></div></template><p v-if="regenerationError" role="alert">{{ regenerationError }}</p></section>
  </section>
</template>
<style scoped>
.artifact-workspace { border-top: 1px solid var(--line); margin-top: 20px; padding-top: 16px; min-width: 0; }
header, .artifact-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
header h3 { margin: 0 auto 0 0; font-size: 14px; }
.artifact-choices { display: grid; gap: 6px; margin: 12px 0; }
.artifact-choices button { cursor: pointer; display: grid; text-align: left; gap: 5px; background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius-sm); padding: 10px 12px; color: var(--ink); overflow-wrap: anywhere; }
.artifact-choices button:hover, .artifact-choices button[aria-pressed="true"] { border-color: var(--brand); background: var(--canvas); }
.artifact-choices button:focus-visible, a:focus-visible { outline: 2px solid var(--brand); outline-offset: 2px; }
small { color: var(--muted); font-size: 11px; }
.report-choices { display: flex; flex-wrap: wrap; gap: 6px; }
.report-choices .el-button { margin-left: 0; }
.artifact-selected { margin-top: 16px; min-width: 0; }
.artifact-actions a { color: var(--brand); text-decoration: underline; font-size: 12px; }
.artifact-actions a:hover { color: var(--ink); }
</style>
