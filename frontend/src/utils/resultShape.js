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
  return Boolean(left.source_ref && right.source_ref && left.source_ref === right.source_ref)
}
