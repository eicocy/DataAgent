<script>
import { ElButton } from 'element-plus'
import { analysisApi } from '../api/analysis'

// 修正仅作用于当前会话的固定数据版本，不改动原数据。
export default {
  name: 'SemanticMappingEditor',
  components: { ElButton },
  props: { sessionId: Number, datasetId: Number, busy: Boolean },
  data() { return { mappings: [], original: [], loading: false, saving: false, error: '', notice: '', controller: null } },
  watch: {
    sessionId: { immediate: true, handler() { this.load() } },
    datasetId() { this.load() },
  },
  beforeUnmount() { this.controller?.abort() },
  methods: {
    async load() {
      this.controller?.abort()
      const controller = new AbortController()
      this.controller = controller
      this.mappings = []; this.original = []; this.error = ''; this.notice = ''; this.saving = false
      if (!this.sessionId || !this.datasetId) { this.loading = false; return }
      this.loading = true
      try {
        const result = await analysisApi.semantics(this.sessionId, this.datasetId, { signal: controller.signal })
        if (this.controller !== controller || controller.signal.aborted) return
        this.mappings = result.mappings.map(item => ({ ...item }))
        this.original = result.mappings.map(item => ({ ...item }))
      } catch (error) { if (!controller.signal.aborted && this.controller === controller) this.error = error.message || '字段含义暂时不可用，可重试。' }
      finally { if (this.controller === controller) this.loading = false }
    },
    async save() {
      if (this.saving || this.busy) return
      const mappings = this.mappings.filter((item, index) => ['concept', 'role', 'unit', 'currency', 'aggregation'].some(key => item[key] !== this.original[index]?.[key]))
      if (!mappings.length) { this.notice = '字段含义未改变'; return }
      if (mappings.some(item => !item.concept.trim())) { this.error = '业务含义不能为空'; return }
      const controller = this.controller
      this.saving = true; this.error = ''; this.notice = ''
      try {
        await analysisApi.updateSemantics(this.sessionId, { mappings: mappings.map(item => ({ ...item, currency: item.currency?.trim() || null, unit: item.unit?.trim() || null })) }, { signal: controller.signal })
        if (this.controller !== controller || controller.signal.aborted) return
        this.original = this.mappings.map(item => ({ ...item }))
        this.notice = '已保存，后续分析使用修正后的字段含义。'
      } catch (error) { if (this.controller === controller && !controller.signal.aborted) this.error = error.message || '保存失败，请保留修改后重试。' }
      finally { if (this.controller === controller) this.saving = false }
    },
  },
}
</script>

<template>
  <details class="semantic-editor">
    <summary>确认字段含义</summary>
    <p class="caption">销售额 revenue · 销量 quantity · 利润 profit。识别结果仅为候选，请核对业务口径。</p>
    <p v-if="loading" role="status">正在识别字段…</p>
    <p v-if="error" role="alert">{{ error }} <el-button v-if="!mappings.length" native-type="button" text @click="load">重试</el-button></p>
    <div class="semantic-fields">
      <div v-for="item in mappings" :key="item.column" class="semantic-row">
        <label>{{ item.column }}<input v-model="item.concept" :aria-label="`${item.column} 的业务含义`" maxlength="100" :disabled="busy || saving" /></label>
        <label>字段用途<select v-model="item.role" :aria-label="`${item.column} 的字段用途`" :disabled="busy || saving"><option value="metric">指标</option><option value="dimension">维度</option></select></label>
        <label>统计口径<select v-model="item.aggregation" :aria-label="`${item.column} 的统计口径`" :disabled="busy || saving"><option value="none">未确认</option><option value="sum">求和</option><option value="mean">平均</option><option value="count">记录数</option><option value="nunique">去重计数</option></select></label>
        <span class="caption">{{ item.source === 'user' ? '已确认' : '待核对' }}</span>
        <label>币种（可选）<input v-model="item.currency" maxlength="10" :aria-label="`${item.column} 的币种`" placeholder="例如 CNY；混合币种请先处理" :disabled="busy || saving" /></label>
        <label>单位（可选）<input v-model="item.unit" maxlength="30" :aria-label="`${item.column} 的单位`" placeholder="例如 元、件；未知请留空" :disabled="busy || saving" /></label>
      </div>
    </div>
    <el-button v-if="mappings.length" native-type="button" :disabled="busy || loading" :loading="saving" @click="save">保存字段含义</el-button>
    <p v-if="notice" role="status">{{ notice }}</p>
    <p v-if="!loading && !error && !mappings.length" class="caption">暂未识别到业务字段，可直接描述分析问题。</p>
  </details>
</template>

<style scoped>
.semantic-editor { margin: 12px 0; padding: 12px 16px; border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--surface); font-size: 12px; }
summary { cursor: pointer; color: var(--muted); }
.semantic-fields { max-height: 260px; overflow: auto; margin: 12px 0; }
.semantic-row { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 12px; margin: 8px 0; }
.semantic-row label { display: grid; gap: 4px; color: var(--muted); }
input, select { max-width: 180px; height: 32px; border: 1px solid var(--line); border-radius: var(--radius-sm); padding: 4px 8px; background: var(--surface); color: var(--ink); }
</style>
