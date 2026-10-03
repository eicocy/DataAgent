<script>
import ChartView from './ChartView.vue'
import { analysisApi } from '../api/analysis'
export default {
  name: 'AnalysisResult',
  components: { ChartView },
  props: { evidence: { type: Object, required: true } },
  data() { return { pages: {}, loading: false, error: '' } },
  computed: {
    charts() { return this.evidence.report?.charts?.length ? this.evidence.report.charts : this.evidence.chart ? [this.evidence.chart] : [] },
    tables() {
      if (this.evidence.report?.tables?.length) return this.evidence.report.tables
      const result = this.evidence.tool_result
      return result ? [{ ...result, rows: result.rows || result.preview_rows || result.sorted_rows || [] }] : []
    },
  },
  methods: {
    rows(table) { return this.pages[table.artifact_id]?.rows || table.rows || [] },
    columns(table) { return table.columns || Object.keys(this.rows(table)[0] || {}) },
    showValue(value) { return value === null || value === undefined ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value) },
    async page(table, offset) {
      if (this.loading) return
      this.loading = true; this.error = ''
      try { this.pages[table.artifact_id] = await analysisApi.result(this.evidence.record_id, table.artifact_id, { offset, limit: 100 }) }
      catch (error) { this.error = error.message || '结果加载失败' }
      finally { this.loading = false }
    },
  },
}
</script>
<template>
  <section class="result-evidence" aria-label="真实计算结果">
    <h3>计算结果</h3>
    <p v-if="evidence.status === 'partial'" class="partial-note" role="status">分析部分完成，下方保留已完成的真实计算结果。</p>
    <p v-if="evidence.error_message" class="message-error" role="alert">{{ evidence.error_message }}</p>
    <p v-for="(warning, index) in evidence.report?.warnings || []" :key="index" class="summary-warning">{{ typeof warning === 'string' ? warning : warning.message }}</p>
    <ChartView v-for="(chart, index) in charts" :key="chart.artifact_id || index" :spec="chart" />
    <section v-for="(table, index) in tables" :key="table.artifact_id || index">
      <div v-if="rows(table).length" class="table-wrap"><table><thead><tr><th v-for="column in columns(table)" :key="column" scope="col">{{ column }}</th></tr></thead><tbody><tr v-for="(row, rowIndex) in rows(table).slice(0, 100)" :key="rowIndex"><td v-for="column in columns(table)" :key="column">{{ showValue(row[column]) }}</td></tr></tbody></table></div>
      <pre v-else>{{ JSON.stringify(table, null, 2) }}</pre>
      <p v-if="table.row_count" class="caption">共 {{ table.row_count }} 行，当前展示最多 100 行。</p>
      <div v-if="table.artifact_id && evidence.record_id && table.row_count > 100"><el-button :disabled="loading || !(pages[table.artifact_id]?.offset > 0)" @click="page(table, Math.max(0, (pages[table.artifact_id]?.offset || 0) - 100))">上一页</el-button><el-button :disabled="loading || (pages[table.artifact_id]?.offset || 0) + 100 >= table.row_count" @click="page(table, (pages[table.artifact_id]?.offset || 0) + 100)">下一页</el-button></div>
    </section>
    <p v-if="error" role="alert">{{ error }}</p>
  </section>
</template>
<style scoped>
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 10px; text-align: left; border-bottom: 1px solid var(--line, #e6ebf2); white-space: nowrap; }
th { font-weight: 600; }
</style>
