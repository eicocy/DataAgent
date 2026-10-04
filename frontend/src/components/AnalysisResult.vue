<script>
import ChartView from './ChartView.vue'
import ForecastResult from './ForecastResult.vue'
import BusinessResult from './BusinessResult.vue'
import DataQualityWorkbench from './DataQualityWorkbench.vue'
import { analysisApi } from '../api/analysis'
import { hasTypedDetails, sameResultSource, structuredKinds } from '../utils/resultShape'

export default {
  name: 'AnalysisResult',
  components: { ChartView, ForecastResult, BusinessResult, DataQualityWorkbench },
  props: { evidence: { type: Object, required: true } },
  data() {
    return { pages: {}, loading: false, error: '' }
  },
  computed: {
    typedEntries() {
      const entries = []
      const raw = this.evidence.tool_result
      if (hasTypedDetails(raw)) {
        // 当前 tool_result 是最后一次成功的非图表结果；call 只提供来源关联与摘要。
        const producer = [...(this.evidence.tool_calls || [])].reverse().find(call =>
          call.status === 'succeeded' && call.tool_name !== 'generate_chart')
        entries.push({
          result: raw,
          source: {
            source_ref: producer?.step_id || raw.source_ref,
            artifact_id: producer?.artifact_id || raw.artifact_id,
          },
        })
      }
      for (const result of this.evidence.report?.tables || []) {
        if (!hasTypedDetails(result)) continue
        if (!entries.some(entry => sameResultSource(entry.source, result))) {
          entries.push({ result, source: result })
        }
      }
      return entries
    },
    charts() {
      return this.evidence.report?.charts?.length
        ? this.evidence.report.charts
        : this.evidence.chart ? [this.evidence.chart] : []
    },
    tables() {
      if (this.evidence.report?.tables?.length) {
        return this.evidence.report.tables.filter(table =>
          !this.typedEntries.some(entry => sameResultSource(entry.source, table)))
      }
      const result = this.evidence.tool_result
      // Join 的样例行有用，其他完整类型化结果由各自面板展示。
      if (!result || (hasTypedDetails(result) && result.kind !== 'join')) return []
      return [{ ...result, rows: result.rows || result.preview_rows || result.sorted_rows || [] }]
    },
  },
  methods: {
    tableOnly(table) {
      return structuredKinds.has(table.kind) && !hasTypedDetails(table)
    },
    rows(table) {
      return this.pages[table.artifact_id]?.rows || table.rows || []
    },
    columns(table) {
      return table.columns || Object.keys(this.rows(table)[0] || {})
    },
    showValue(value) {
      if (value === null || value === undefined) return '—'
      return typeof value === 'object' ? JSON.stringify(value) : String(value)
    },
    async page(table, offset) {
      if (this.loading) return
      this.loading = true
      this.error = ''
      try {
        this.pages[table.artifact_id] = await analysisApi.result(
          this.evidence.record_id, table.artifact_id, { offset, limit: 100 })
      } catch (error) {
        this.error = error.message || '结果加载失败'
      } finally {
        this.loading = false
      }
    },
  },
}
</script>

<template>
  <section class="result-evidence" aria-label="真实计算结果">
    <h3>计算结果</h3>
    <p v-if="evidence.status === 'partial'" class="partial-note" role="status">分析部分完成，下方保留已完成的真实计算结果。</p>
    <p v-if="evidence.error_message" class="message-error" role="alert">{{ evidence.error_message }}</p>
    <p v-for="(warning, index) in evidence.report?.warnings || []" :key="index" class="summary-warning">
      {{ typeof warning === 'string' ? warning : warning.message }}
    </p>
    <section v-for="(entry, index) in typedEntries" :key="entry.source.artifact_id || entry.source.source_ref || index">
      <ForecastResult v-if="entry.result.kind === 'forecast'" :result="entry.result" />
      <BusinessResult v-else-if="['kpi', 'period_comparison', 'contribution'].includes(entry.result.kind)" :result="entry.result" />
      <DataQualityWorkbench v-else-if="['quality', 'quality_score'].includes(entry.result.kind)" :result="entry.result" />
      <div v-else>
        <h3>{{ entry.result.kind === 'join' ? '合并结果' : '清洗结果' }}</h3>
        <p>{{ entry.result.row_count }} 行 · {{ entry.result.column_count ?? entry.result.columns?.length }} 列 · 输出版本 {{ entry.result.output_version ?? '未发布' }}</p>
        <p v-if="entry.result.source_versions">左版本 {{ entry.result.source_versions.left }} · 右版本 {{ entry.result.source_versions.right }}</p>
        <p v-for="(step, i) in entry.result.steps || [entry.result]" :key="i">
          {{ step.operation }} · 改变 {{ step.changed_cells ?? '—' }} 个单元格 · 新增缺失 {{ step.added_missing ?? '—' }}
        </p>
      </div>
    </section>
    <ChartView v-for="(chart, index) in charts" :key="chart.artifact_id || index" :spec="chart" />
    <section v-for="(table, index) in tables" :key="table.artifact_id || index">
      <template v-if="tableOnly(table)">
        <p class="summary-warning">当前仅提供结果表，完整计算信息未提供，无法展示完整指标或验证详情。</p>
        <p v-if="table.currency || table.unit">{{ table.currency || '币种未提供' }} · {{ table.unit || '单位未提供' }}</p>
        <p v-if="table.current_range">本期：{{ table.current_range.start }} 至 {{ table.current_range.end }}</p>
        <p v-if="table.previous_range">对比期：{{ table.previous_range.start }} 至 {{ table.previous_range.end }}</p>
        <p v-for="note in table.limitations || []" :key="note" class="summary-warning">{{ note }}</p>
      </template>
      <div v-if="rows(table).length" class="table-wrap phase3-table">
        <table class="data-table">
          <thead><tr><th v-for="column in columns(table)" :key="column" scope="col">{{ column }}</th></tr></thead>
          <tbody>
            <tr v-for="(row, rowIndex) in rows(table).slice(0, 100)" :key="rowIndex">
              <td v-for="column in columns(table)" :key="column">{{ showValue(row[column]) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else-if="tableOnly(table)">当前结果表没有展示行，不能据此判断原数据是否为空或没有质量问题。</p>
      <pre v-else>{{ JSON.stringify(table, null, 2) }}</pre>
      <p v-if="table.row_count != null" class="caption">结果表共 {{ table.row_count }} 行，当前展示最多 100 行。</p>
      <p v-if="table.source_ref" class="caption">结果来源：{{ table.source_ref }}</p>
      <div v-if="table.artifact_id && evidence.record_id && table.row_count > 100">
        <el-button :disabled="loading || !(pages[table.artifact_id]?.offset > 0)" @click="page(table, Math.max(0, (pages[table.artifact_id]?.offset || 0) - 100))">上一页</el-button>
        <el-button :disabled="loading || (pages[table.artifact_id]?.offset || 0) + 100 >= table.row_count" @click="page(table, (pages[table.artifact_id]?.offset || 0) + 100)">下一页</el-button>
      </div>
    </section>
    <p v-if="error" role="alert">{{ error }}</p>
  </section>
</template>

<style scoped>
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 10px; text-align: left; border-bottom: 1px solid var(--line, #e6ebf2); white-space: nowrap; }
th { font-weight: 600; }
</style>
