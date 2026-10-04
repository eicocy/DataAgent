<script>
import ChartView from './ChartView.vue'
export default {
  name: 'ArtifactPreview', components: { ChartView },
  props: { preview: { type: Object, default: null }, title: { type: String, default: '成果预览' } },
  methods: { columns(table) { return (table.columns || []).map(c => typeof c === 'string' ? c : c.name || c.field) }, value(value) { return value == null ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value) } },
}
</script>
<template>
  <div v-if="preview" class="artifact-preview">
    <ChartView v-if="preview.chart" :spec="preview.chart" />
    <template v-else-if="preview.kind === 'workbook'"><section v-for="sheet in preview.sheets" :key="sheet.name"><h4>{{ sheet.name }}</h4><div class="table-wrap"><table class="data-table"><tbody><tr v-for="(row, index) in sheet.rows" :key="index"><td v-for="(cell, ci) in row" :key="ci">{{ value(cell) }}</td></tr></tbody></table></div></section></template>
    <article v-else-if="preview.kind === 'report_document'"><h3>{{ preview.document?.title }}</h3><p v-if="preview.document?.metadata?.user_edited">此版本包含用户编辑文案，计算结果与证据保留原始来源。</p><section v-for="section in preview.document?.sections || []" :key="section.section_id"><h4>{{ section.title }}</h4><p>{{ section.narrative }}</p><div v-for="(table,index) in section.data?.tables || []" :key="index" class="table-wrap"><table class="data-table"><thead><tr><th v-for="c in columns(table)" :key="c">{{ c }}</th></tr></thead><tbody><tr v-for="(row,ri) in table.rows?.slice(0,100)" :key="ri"><td v-for="c in columns(table)" :key="c">{{ value(row[c]) }}</td></tr></tbody></table></div></section></article>
    <iframe v-else-if="preview.kind === 'document'" :src="preview.preview_url" :title="title" :sandbox="preview.mime_type === 'text/html' ? '' : undefined" class="artifact-document-frame"></iframe>
    <pre v-else-if="preview.kind === 'text'">{{ preview.content }}</pre>
    <template v-else><p>{{ preview.total ?? preview.rows?.length ?? 0 }} 行 · 当前预览 {{ preview.rows?.length || 0 }} 行</p><div class="table-wrap"><table class="data-table"><thead><tr><th v-for="column in preview.columns" :key="column">{{ column }}</th></tr></thead><tbody><tr v-for="(row,index) in preview.rows" :key="index"><td v-for="column in preview.columns" :key="column">{{ value(row[column]) }}</td></tr></tbody></table></div></template>
  </div>
</template>
<style scoped>
.artifact-preview { min-width: 0; font-size: 12px; }
.table-wrap { width: 100%; overflow: auto; max-height: 420px; }
.data-table { width: max-content; min-width: 100%; }
.data-table th, .data-table td { max-width: 260px; overflow-wrap: anywhere; white-space: normal; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 560px; overflow: auto; }
p { white-space: pre-wrap; overflow-wrap: anywhere; }
.artifact-document-frame { width: 100%; height: 560px; border: 1px solid var(--line); background: var(--surface); }
</style>
