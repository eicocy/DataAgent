// 诊断副本只包含公开元数据，不复制请求正文或原始异常。
const keys = ['code', 'reason_code', 'reason', 'suggestion', 'stage', 'operation', 'step_id', 'tool_name',
  'stage_elapsed_seconds', 'task_elapsed_seconds', 'queue_elapsed_seconds', 'limit_seconds', 'timeout_scope',
  'request_id', 'analysis_request_id', 'record_id', 'job_id', 'dataset_id', 'dataset_version_id',
  'retryable', 'legacy', 'title', 'field_errors', 'validation_rule', 'column', 'expected_type', 'actual_type',
  'actual_count', 'max_count', 'actual_length', 'max_length', 'diagnostic_source', 'reviewed_at', 'completed_steps', 'preserved_artifact_ids']

export function diagnosticCopy(info) {
  return JSON.stringify(Object.fromEntries(keys.filter(key => info?.[key] != null).map(key => [key, info[key]])), null, 2)
}

export function taskError(result) {
  return Object.assign(new Error(result.error_info?.reason || result.error_message || result.parse_error_message || '任务未能完成'), {
    code: result.error_code || result.parse_error_code || 'TASK_FAILED', info: result.error_info,
    recordId: result.record_id, retryable: Boolean(result.error_info?.retryable),
  })
}

export const stageLabels = { llm: '模型调用', planning: '分析规划', sql: '数据库查询', pandas: '数据计算',
  tool: '工具计算', report: '报告交付', parse: '文件解析', request: '接口请求', idle: '阶段切换' }
