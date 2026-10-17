<script>
export default {
  name: 'AnalysisScope',
  props: { context: { type: Object, default: null }, dataset: { type: Object, default: null } },
  computed: {
    filters() {
      const label = f => `${f.column} ${f.operator || f.op || ''} ${Array.isArray(f.value) ? f.value.join('、') : f.value ?? ''}`
      if (this.context?.filter_groups?.length) return this.context.filter_groups.map(g => `${g.input_alias || 'primary'} / ${g.source_ref || 'dataset'}：(${g.filters.map(label).join(g.logic === 'or' ? ' 或 ' : ' 且 ')})`)
      return (this.context?.filters || []).map(label)
    },
  },
}
</script>
<template>
  <section v-if="context" class="analysis-scope" aria-label="当前分析范围">
    <strong>当前分析范围</strong>
    <span>数据：{{ dataset?.original_name || `#${context.active_dataset_id || '未记录'}` }} · 固定版本 {{ context.dataset_version_id ?? '未记录' }}</span>
    <span>筛选：{{ filters.join('；') || '未设置' }}</span>
    <span>分组：{{ context.dimensions?.join('、') || '未设置' }} · 指标：{{ context.metrics?.join('、') || '由本次计划确定' }}</span>
    <span v-if="context.time_range">时间：{{ context.time_range.start }} 至 {{ context.time_range.end }}</span>
    <span v-for="(item, index) in context.units || []" :key="index">{{ item.column }}：{{ item.currency || '' }} {{ item.unit || '单位未确认' }}</span>
  </section>
</template>
<style scoped>
.analysis-scope { display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 11px; line-height: 1.6; padding: 10px 12px; border: 1px solid var(--line); border-radius: 8px; background: var(--canvas); overflow-wrap: anywhere; }
.analysis-scope strong { width: 100%; } .analysis-scope span { color: var(--muted); }
</style>
