export const structuredKinds = new Set([
  'forecast', 'kpi', 'period_comparison', 'contribution', 'quality_score',
  'quality', 'join', 'cleaning_plan', 'cleaning',
])

// result_tables 的 kind 是结果类别，不证明完整类型化证据仍然存在。
export function hasTypedDetails(result) {
  if (!result || !structuredKinds.has(result.kind)) return false
  switch (result.kind) {
    case 'forecast':
      return Boolean(result.metrics && result.baseline?.metrics && result.uncertainty &&
        Array.isArray(result.points) && Array.isArray(result.folds) &&
        Array.isArray(result.candidates) && result.history_start && result.history_end)
    case 'kpi':
      return Boolean(result.metrics && !Array.isArray(result.metrics))
    case 'period_comparison':
    case 'contribution':
      return Boolean(result.current && result.previous && result.delta && result.growth_rate &&
        result.current_range && result.previous_range &&
        (result.kind !== 'contribution' || Array.isArray(result.groups)))
    case 'quality_score':
      return ['valid', 'empty'].includes(result.status) && Array.isArray(result.findings) &&
        typeof result.row_count === 'number' && typeof result.explanation === 'string'
    case 'quality':
      return typeof result.check === 'string' && Array.isArray(result.findings)
    case 'join':
      return Boolean(result.source_versions && typeof result.left_rows === 'number' &&
        typeof result.right_rows === 'number')
    case 'cleaning_plan':
      return Array.isArray(result.steps) && Boolean(result.before_quality && result.after_quality)
    case 'cleaning':
      return typeof result.operation === 'string' && typeof result.changed_cells === 'number'
    default:
      return false
  }
}

export function sameResultSource(left, right) {
  if (left.artifact_id != null && right.artifact_id != null) {
    return left.artifact_id === right.artifact_id
  }
  return Boolean(stepSource(left.source_ref) && left.source_ref === right.source_ref)
}

const contextSources = new Set(['dataset', 'primary'])
const stepSource = source => source && !contextSources.has(source)

function equalValue(left, right) {
  if (left === right) return true
  if (!left || !right || typeof left !== 'object' || typeof right !== 'object') return false
  const keys = Object.keys(left)
  return keys.length === Object.keys(right).length && keys.every(key => equalValue(left[key], right[key]))
}

function fullPayloadMatches(raw, table) {
  return hasTypedDetails(table) && Object.keys(raw)
    .filter(key => !['source_ref', 'artifact_id'].includes(key))
    .every(key => equalValue(raw[key], table[key]))
}

function normalizedRows(raw) {
  if (raw.kind === 'forecast') return raw.points
  if (raw.kind === 'kpi') return Object.entries(raw.metrics).map(([metric, value]) => ({ metric, ...value }))
  if (raw.kind === 'quality_score') return raw.findings
  return null
}

export function rawResultSource(evidence) {
  const raw = evidence.tool_result
  const knownSteps = [...(evidence.plan?.steps || []), ...(evidence.tool_calls || [])]
  if (raw.artifact_id != null || (stepSource(raw.source_ref) &&
    knownSteps.some(step => step.step_id === raw.source_ref))) return raw
  const tables = evidence.report?.tables || []
  const matches = tables.filter(table => fullPayloadMatches(raw, table))
  // 并行 call 数组是完成顺序。计划最后成功计算的 result_ref 才是 raw 输出契约。
  const finalStep = [...(evidence.plan?.steps || [])].reverse().find(step =>
    step.status === 'COMPLETED' && step.tool_name !== 'generate_chart')
  const planned = matches.filter(table => table.source_ref === finalStep?.step_id &&
    finalStep.result_ref === `artifact:${table.artifact_id}`)
  if (planned.length === 1) return planned[0]
  if (matches.length === 1) return matches[0]
  if (matches.length > 1) return {}

  // 旧 normalized-only 协议：仅有一个成功计算来源且投影逐值相符时关联；不按 kind 猜测。
  const calls = (evidence.tool_calls || []).filter(call =>
    call.status === 'succeeded' && call.tool_name !== 'generate_chart')
  const projected = normalizedRows(raw)
  if (calls.length !== 1 || !projected?.length) return {}
  const candidates = tables.filter(table => table.kind === raw.kind &&
    sameResultSource({ source_ref: calls[0].step_id, artifact_id: calls[0].artifact_id }, table) &&
    ['dataset_id', 'dataset_version', 'history_start', 'history_end', 'time_column', 'target_column', 'currency', 'unit']
      .every(key => table[key] == null || raw[key] == null || equalValue(raw[key], table[key])) &&
    table.rows?.length === projected.length && table.rows.every((row, index) =>
      Object.keys(row).every(key => equalValue(row[key], projected[index][key]))))
  return candidates.length === 1 ? candidates[0] : {}
}
