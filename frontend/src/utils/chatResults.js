import { hasTypedDetails, rawResultSource, sameResultSource } from './resultShape'

// 来源去重只在同类结果中进行，图表与其来源表仍是两种可查看的结果。
export function chatResults(evidence) {
  const entries = []
  const add = (kind, value, source = value) => {
    if (!entries.some(entry => entry.kind === kind && sameResultSource(entry.source, source))) {
      entries.push({ kind, value, source, key: `${kind}:${source.artifact_id ?? source.source_ref ?? entries.length}` })
    }
  }
  for (const table of evidence.report?.tables || []) add('table', table)
  const raw = evidence.tool_result
  if (raw && (hasTypedDetails(raw) || raw.rows?.length || raw.preview_rows?.length || raw.sorted_rows?.length || raw.metric_values)) {
    const source = rawResultSource(evidence)
    const existing = entries.find(entry => sameResultSource(entry.source, source))
    if (existing && hasTypedDetails(raw)) existing.value = raw
    else if (!existing) add('table', { ...raw, rows: raw.rows || raw.preview_rows || raw.sorted_rows || (raw.metric_values ? Object.entries(raw.metric_values).map(([metric, value]) => ({ metric, value })) : []) }, source)
  }
  for (const chart of evidence.report?.charts?.length ? evidence.report.charts : evidence.chart ? [evidence.chart] : []) add('chart', chart)
  const expected = evidence.plan?.expected_outputs || []
  const resolveSource = source => (evidence.tool_calls || []).find(call => source != null && [call.call_id, call.tool_call_id].includes(source))?.step_id || source
  const chartSources = entries.filter(entry => entry.kind === 'chart').map(entry => resolveSource(entry.value.source_ref || entry.value.source_tool_call_id))
  const sourceStep = entry => entry.source.source_ref || evidence.plan?.steps?.find(step => step.result_ref === `artifact:${entry.source.artifact_id}`)?.step_id
  const rank = entry => {
    const index = expected.indexOf(sourceStep(entry))
    return index >= 0 ? index : entry.kind === 'table' && chartSources.includes(sourceStep(entry)) ? expected.length : expected.length + 1
  }
  const prioritized = entries.some(entry => rank(entry) <= expected.length) && (expected.length || chartSources.some(Boolean))
  const ordered = [...entries].sort((a, b) => rank(a) - rank(b))
  if (!prioritized && ordered.every(entry => entry.source.artifact_id != null && Number.isFinite(Number(entry.source.artifact_id)))) {
    ordered.sort((a, b) => Number(a.source.artifact_id) - Number(b.source.artifact_id))
  }
  const primary = [], more = []
  let charts = 0, tables = 0
  for (const entry of ordered) {
    const allowed = prioritized ? entry.kind === 'chart' ? charts < 2 : tables < 1 : primary.length === 0
    if (allowed) { primary.push(entry); if (entry.kind === 'chart') charts++; else tables++ }
    else more.push(entry)
  }
  return { primary, more }
}
