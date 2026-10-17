<script>
import LazyChart from './LazyChart.vue'
import { chatResults } from '../utils/chatResults'
import ChartView from './ChartView.vue'
import ErrorInfoPanel from './ErrorInfoPanel.vue'
import ForecastResult from './ForecastResult.vue'
import BusinessResult from './BusinessResult.vue'
import DataQualityWorkbench from './DataQualityWorkbench.vue'
import { analysisApi } from '../api/analysis'
import { hasTypedDetails, rawResultSource, sameResultSource, structuredKinds } from '../utils/resultShape'

export default {
  name: 'AnalysisResult',
  components: { LazyChart, ErrorInfoPanel, ChartView, ForecastResult, BusinessResult, DataQualityWorkbench },
  props: { evidence: { type: Object, required: true }, presentation: { type: String, default: 'full' } },
  emits: ['preview'],
  data() {
    return { pages: {}, loading: false, error: '', expanded: false, pageController: null }
  },
  watch: { evidence() { this.pageController?.abort(); this.pages = {}; this.loading = false; this.error = ''; this.expanded = false } },
  beforeUnmount() { this.pageController?.abort() },
  computed: {
    chat() { return this.presentation === 'chat' },
    selection() { return chatResults(this.evidence) },
    visibleEntries() { return this.expanded ? [...this.selection.primary, ...this.selection.more] : this.selection.primary },
    visibleTyped() { return this.chat ? this.visibleEntries.filter(entry => entry.kind === 'table' && hasTypedDetails(entry.value)).map(entry => ({ result: entry.value, source: entry.source })) : this.typedEntries },
    visibleCharts() { return this.chat ? this.visibleEntries.filter(entry => entry.kind === 'chart').map(entry => entry.value) : this.charts },
    visibleTables() { return this.chat ? this.visibleEntries.filter(entry => entry.kind === 'table' && !hasTypedDetails(entry.value)).map(entry => ({ ...entry.value, ...entry.source })) : this.tables },
    typedEntries() {
      const entries = []
      const raw = this.evidence.tool_result
      if (hasTypedDetails(raw)) {
        entries.push({ result: raw, source: rawResultSource(this.evidence) })
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
      const controller = new AbortController()
      this.pageController = controller
      const recordId = this.evidence.record_id
      try {
        const response = await analysisApi.result(recordId, table.artifact_id, { offset, limit: 100 }, { signal: controller.signal })
        if (this.pageController !== controller || controller.signal.aborted || this.evidence.record_id !== recordId) return
        this.pages[table.artifact_id] = response
      } catch (error) {
        if (!controller.signal.aborted) this.error = error.message || '结果加载失败'
      } finally {
        if (this.pageController === controller) this.loading = false
      }
    },
  },
}
</script>

<template>
  <section class="result-evidence" :class="{ 'chat-results': chat }" :aria-label="chat ? '分析结果' : '真实计算结果'">
    <h3 v-if="!chat">计算结果</h3>
    <p v-if="!chat && evidence.status === 'partial'" class="partial-note" role="status">分析部分完成，下方保留已完成的真实计算结果。</p>
    <ErrorInfoPanel v-if="!chat" :info="evidence.error_info" :message="evidence.error_message || ''" />
    <p v-for="(warning, index) in evidence.report?.warnings || []" :key="index" class="summary-warning">
      {{ typeof warning === 'string' ? warning : warning.message }}
    </p>
    <section v-for="(entry, index) in visibleTyped" :key="entry.source.artifact_id || entry.source.source_ref || index">
      <ForecastResult v-if="entry.result.kind === 'forecast'" :result="entry.result" :compact="chat" :hide-chart="chat && (visibleCharts.length >= 2 || visibleCharts.some(chart => chart.source_ref && chart.source_ref === entry.source.source_ref))" @expand="$emit('preview', { kind: 'chart', value: $event })" />
      <BusinessResult v-else-if="['kpi', 'period_comparison', 'contribution'].includes(entry.result.kind)" :result="entry.result" :compact="chat" />
      <DataQualityWorkbench v-else-if="['quality', 'quality_score'].includes(entry.result.kind)" :result="entry.result" :compact="chat" />
      <div v-else>
        <h3>{{ entry.result.kind === 'join' ? '合并结果' : '清洗结果' }}</h3>
        <p>{{ entry.result.row_count }} 行 · {{ entry.result.column_count ?? entry.result.columns?.length }} 列 · 输出版本 {{ entry.result.output_version ?? '未发布' }}</p>
        <p v-if="entry.result.source_versions">左版本 {{ entry.result.source_versions.left }} · 右版本 {{ entry.result.source_versions.right }}</p>
        <p v-for="(step, i) in entry.result.steps || [entry.result]" :key="i">
          {{ step.operation }} · 改变 {{ step.changed_cells ?? '—' }} 个单元格 · 新增缺失 {{ step.added_missing ?? '—' }}
        </p>
      </div>
      <button v-if="chat" type="button" class="result-text-action" @click="$emit('preview', { kind: 'table', value: { ...entry.result, ...entry.source } })">查看完整数据</button>
    </section>
    <component :is="chat ? 'LazyChart' : 'ChartView'" v-for="(chart, index) in visibleCharts" :key="chart.artifact_id || index" :spec="chart" @expand="$emit('preview', { kind: 'chart', value: chart })" />
    <section v-for="(table, index) in visibleTables" :key="table.artifact_id || index">
      <p v-if="chat && (table.currency || table.unit)" class="caption">{{ [table.currency, table.unit].filter(Boolean).join(' · ') }}</p>
      <p v-for="note in chat && !tableOnly(table) ? table.limitations || [] : []" :key="note" class="summary-warning">{{ note }}</p>
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
            <tr v-for="(row, rowIndex) in rows(table).slice(0, chat ? 10 : 100)" :key="rowIndex">
              <td v-for="column in columns(table)" :key="column">{{ showValue(row[column]) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else-if="tableOnly(table)">当前结果表没有展示行，不能据此判断原数据是否为空或没有质量问题。</p>
      <details v-else-if="!chat"><summary>查看结果详情</summary><pre>{{ JSON.stringify(table, null, 2) }}</pre></details>
      <p v-if="table.row_count != null" class="caption">结果表共 {{ table.row_count }} 行，当前展示最多 {{ chat ? 10 : 100 }} 行。</p>
      <p v-if="!chat && table.source_ref" class="caption">结果来源：{{ table.source_ref }}</p>
      <div v-if="!chat && table.artifact_id && evidence.record_id && table.row_count > 100">
        <el-button :disabled="loading || !(pages[table.artifact_id]?.offset > 0)" @click="page(table, Math.max(0, (pages[table.artifact_id]?.offset || 0) - 100))">上一页</el-button>
        <el-button :disabled="loading || (pages[table.artifact_id]?.offset || 0) + 100 >= table.row_count" @click="page(table, (pages[table.artifact_id]?.offset || 0) + 100)">下一页</el-button>
      </div>
      <button v-if="chat" type="button" class="result-text-action" @click="$emit('preview', { kind: 'table', value: table })">查看完整数据</button>
    </section>
    <button v-if="chat && selection.more.length" type="button" class="result-text-action more-results" :aria-expanded="expanded" @click="expanded = !expanded">{{ expanded ? '收起更多结果' : `查看其余 ${selection.more.length} 项结果` }}</button>
    <p v-if="error" role="alert">{{ error }}</p>
  </section>
</template>

<style scoped>
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 10px; text-align: left; border-bottom: 1px solid var(--line, #e6ebf2); white-space: nowrap; }
th { font-weight: 600; }
.chat-results { min-width: 0; margin: 20px 0; }
.chat-results > section { margin: 20px 0; }
.chat-results .table-wrap { max-width: 100%; overflow: auto; }
.result-text-action { border: 0; background: transparent; padding: 8px 0; color: var(--muted); font-size: 12px; cursor: pointer; }
.result-text-action:hover { color: var(--brand); }
.result-text-action:focus-visible { outline: 2px solid var(--brand); outline-offset: 3px; }
</style>
