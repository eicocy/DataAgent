"""Bounded public diagnostics; never serialize exception values or request bodies."""
from contextvars import ContextVar
from datetime import UTC, datetime
import logging
import re
import traceback
import uuid

request_id_context = ContextVar('diagnostic_request_id', default=None)


def identifier(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', value) else None


def elapsed(start, end=None):
    if start is None:
        return None
    end = end or datetime.now(UTC)
    return round(max(0, (end.replace(tzinfo=None)-start.replace(tzinfo=None)).total_seconds()), 3)


REASONS = {
    'LLM_CALL_TIMEOUT': ('模型调用超过本次允许的等待时间。', '稍后显式重试；若反复出现，检查模型连接与服务响应。'),
    'ANALYSIS_TOTAL_TIMEOUT': ('任务执行超过本次总时间预算。', '缩小分析范围或选择更高分析深度；已完成成果仍可查看。'),
    'TOOL_TIMEOUT': ('计算步骤超过允许的执行时间。', '检查数据规模和计算范围后显式重试。'),
    'TASK_INTERRUPTED': ('后台任务执行中断，未能正常结束。', '检查服务运行记录后显式重试；这不等同于模型超时。'),
    'TASK_CANCELLED': ('任务已按取消请求终止。', '需要继续时重新提交分析。'),
    'MODEL_AUTH_FAILED': ('模型服务拒绝了当前鉴权凭据。', '检查服务端模型凭据和访问权限后重试。'),
    'MODEL_RATE_LIMITED': ('模型服务返回限流或配额限制。', '检查模型配额，稍后显式重试。'),
    'MODEL_CONNECTION_FAILED': ('未能与模型服务建立或维持连接。', '检查服务端网络及模型服务地址。'),
    'PLAN_INVALID': ('生成的分析计划没有通过结构或参数校验。', '查看校验规则和字段路径，确认字段与分析方法后重试。'),
    'INTERNAL_ERROR': ('服务在处理当前操作时发生未预期异常。', '复制诊断信息，根据关联编号检查服务端记录。'),
    'CHART_POINT_LIMIT_EXCEEDED': ('绘图数据点超过限制。', '先取全局前 N 条再绘图：top_n 的 group_by 设为 []。按 genres 分组统计后，全局取前 10 组；不要在每个 genres 组内再取前 10。仅调整预览 limit 不会减少实际绘图数据。'),
    'COLUMN_NOT_FOUND': ('分析计划引用了不存在的字段，字段名未记录。', '核对当前数据版本的字段名；若问题中的字段正确，这是生成计划的问题，可保留原问题重试或反馈关联编号，无需删除正确数据。'),
    'CHART_COLUMN_NOT_FOUND': ('绘图引用了来源结果中不存在的字段。', '从绘图来源结果的列中选择维度和指标；聚合后的指标应使用输出列名。'),
    'COLUMN_TYPE_MISMATCH': ('字段类型与当前计算要求不匹配。', '改选符合要求的字段，或先修正该列的数据类型。'),
    'NUMERIC_COLUMN_REQUIRED': ('当前计算需要数值字段。', '改选数值列，或先清理该列中的非数值内容。'),
    'MODEL_CONTEXT_BUDGET_EXCEEDED': ('模型输入超过上下文容量。', '缩小本次分析涉及的字段、附件或历史背景后重试。该限制与任务等待时间不同，增加超时时间不能解决。'),
    'MODEL_BUDGET_EXCEEDED': ('本次分析的模型调用或用量预算已耗尽。', '减少分析目标，分次提问或选择更高分析深度后重试。'),
    'TOP_N_GROUP_SCOPE_INVALID': ('生成计划把“全局前 N 组”写成了“每组各取 N 条”，会保留过多数据。', '全局排名应将 top_n/bottom_n 的 group_by 设为空列表。可明确提问“在全部类型组合之间取全局前 10 组，不是每组各取 10 条”。'),
    'TOOL_CALCULATION_FAILED': ('计算步骤失败，旧记录未保存底层具体原因，无法确认是字段、类型还是计算限制。', '查看已完成成果；保留原问题在修复后的版本显式重试，或提供关联编号排查。'),
}

# Plain exception values are untrusted. Only known rule identifiers can be public.
PUBLIC_VALIDATION_RULES = set(REASONS) | {
    'PLAN_DATASET_MISMATCH', 'PLAN_STEP_LIMIT', 'DUPLICATE_STEP', 'JOIN_INPUT_UNAVAILABLE',
    'TOOL_NOT_ALLOWED', 'CLEANING_ANALYSIS_ONLY', 'PLAN_STEP_STATE_INVALID', 'DEPENDENCY_INVALID',
    'SOURCE_DEPENDENCY_MISSING', 'TOOL_ARGUMENTS_INVALID', 'DEPENDENCY_CYCLE', 'EXPECTED_OUTPUT_MISSING',
    'PLAN_TASK_INPUT_MISMATCH', 'REGISTERED_TOOLS_INSUFFICIENT', 'INITIAL_EXPLORATION_INVALID',
    'PLAN_TASK_MISMATCH', 'MODEL_OUTPUT_INVALID', 'PLAN_SCHEMA_INVALID', 'PLAN_ARGUMENTS_INVALID_JSON',
}


def validation_fields(errors):
    """Translate validation rules, allowing bounds/lengths but never the input value."""
    result = []
    for error in errors[:20]:
        loc = error.get('loc', ())
        if loc and loc[0] in {'body', 'query', 'path'}:
            loc = loc[1:]
        path = '.'.join(str(v) for v in loc)[:200] or '请求内容'
        rule = identifier(error.get('type')) or 'validation_error'
        field = {'path': path, 'rule': rule}
        ctx = error.get('ctx') or {}
        for key in ('max_length', 'min_length', 'ge', 'le', 'gt', 'lt'):
            value = ctx.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                field[key] = value
        value = error.get('input')
        if isinstance(error.get('actual_length'), int) and error['actual_length'] >= 0:
            field['actual_length'] = error['actual_length']
        if rule in {'string_too_long', 'string_too_short', 'too_long', 'too_short'} and isinstance(value, (str, list, dict)):
            field['actual_length'] = len(value)
        if rule == 'missing':
            message = f'缺少必填参数 {path}。'
        elif rule == 'string_too_long':
            message = f"字段 {path} 过长，最多允许 {field.get('max_length', '未记录')} 个字符，实际 {field.get('actual_length', '未记录')} 个字符。"
        elif rule == 'too_long':
            message = f"参数 {path} 包含的项目过多，上限 {field.get('max_length', '未记录')}，实际 {field.get('actual_length', '未记录')}。"
        elif rule == 'extra_forbidden':
            message = f'参数 {path} 不受支持，请移除此参数。'
        elif rule in {'greater_than_equal', 'less_than_equal', 'greater_than', 'less_than'}:
            limits = ', '.join(f'{k}={field[k]}' for k in ('ge','le','gt','lt') if k in field)
            message = f'参数 {path} 超出允许范围（{limits}）。'
        elif rule.endswith(('_type', '_parsing')):
            types = {'int': '整数', 'float': '数值', 'string': '文本', 'list': '列表', 'dict': '对象', 'bool': '布尔值'}
            expected = types.get(rule.split('_')[0], '规定格式')
            message = f'参数 {path} 类型或格式不正确，需要{expected}。'
        else:
            message = f'参数 {path} 不符合校验规则 {rule}。'
        field['message'] = message
        result.append(field)
    return result


def actionable_info(info):
    """Enrich new and historical diagnostics without inventing missing field names."""
    info = dict(info)
    rule = info.get('validation_rule')
    reason_code = rule if rule in REASONS else info.get('reason_code') or info.get('code')
    info['reason_code'] = reason_code
    if reason_code in REASONS:
        info['reason'], info['suggestion'] = REASONS[reason_code]
    title = '执行失败'
    if reason_code in {'COLUMN_NOT_FOUND', 'CHART_COLUMN_NOT_FOUND'}:
        title = '字段不存在'
        if info.get('column'):
            scope = '聚合后的结果' if info.get('expected_type') == '聚合输出字段或分组字段' else '当前步骤的数据来源'
            info['reason'] = f"{scope}中不存在字段 {info['column']}。"
    elif reason_code in {'NUMERIC_COLUMN_REQUIRED', 'COLUMN_TYPE_MISMATCH'}:
        title = '字段类型不匹配'
        if info.get('column'):
            info['reason'] = f"字段 {info['column']} 类型不匹配：需要{info.get('expected_type') or '数值'}，实际为 {info.get('actual_type') or '未记录'}。"
    elif reason_code == 'CHART_POINT_LIMIT_EXCEEDED':
        title = '图表数据过多'
        info['reason'] = f"绘图来源包含 {info.get('actual_count', '未记录')} 个数据点，超过单张图表 {info.get('max_count', '未记录')} 个数据点的上限。"
    elif reason_code == 'MODEL_CONTEXT_BUDGET_EXCEEDED':
        title = '上下文超限'
        if info.get('max_length') is not None:
            info['reason'] = f"模型输入上下文过长：缩减可选背景后仍有 {info.get('actual_length', '未记录')} 个字符，上限 {info['max_length']} 个字符。"
    elif reason_code == 'TOP_N_GROUP_SCOPE_INVALID':
        title = '排名范围不正确'
    elif 'TIMEOUT' in (reason_code or ''):
        title = '执行超时'
    fields = info.get('field_errors') or []
    if fields:
        fields = [f if f.get('message') else validation_fields([{'loc': [f.get('path', '')], 'type': f.get('rule')}])[0] for f in fields]
        info['field_errors'] = fields
        info['reason'] = ' '.join(f['message'] for f in fields[:3])
        info['suggestion'] = '按上述字段路径补齐参数、缩短内容或修正类型后重试。若错误发生于分析规划，表示模型生成了不合法参数，可保留问题重试并反馈关联编号。'
        title = '缺少必填参数' if fields[0]['rule'] == 'missing' else '字段过长' if fields[0]['rule'] == 'string_too_long' else '参数不符合要求'
    if reason_code == 'PLAN_INVALID' and not fields:
        info['suggestion'] = '这是生成的分析计划校验失败，尚不能据此认定数据有问题。查看具体校验规则；若未记录字段名，请保留原问题重试并反馈关联编号。'
    info['title'] = title
    return info


def error_info(code, message=None, *, reason_code=None, stage=None, operation=None,
               record=None, job=None, exception=None, limit_seconds=None, timeout_scope=None,
               retryable=None, details=None, suggestion=None, legacy=False):
    """Only emit explicit metadata. Raw exceptions/parameters/prompts are excluded."""
    reason_code = reason_code or code
    reason, default_suggestion = REASONS.get(reason_code, (message or '当前操作未能完成。', '核对输入、字段与资源状态；复制诊断信息协助排查。'))
    suggestion = suggestion if isinstance(suggestion,str) and len(suggestion)<=500 and not re.search(r'(?i)password|api.key|authorization|bearer|://|\[SQL:|prompt',suggestion) else default_suggestion
    now = datetime.now(UTC)
    info = dict(code=identifier(code) or 'INTERNAL_ERROR', reason_code=identifier(reason_code) or 'INTERNAL_ERROR',
                reason=reason, suggestion=suggestion, stage=identifier(stage or getattr(job, 'active_stage', None)),
                operation=identifier(operation), request_id=request_id_context.get(),
                analysis_request_id=getattr(record, 'request_id', None), record_id=getattr(record, 'id', None),
                job_id=getattr(job, 'id', None), dataset_id=getattr(record, 'dataset_id', None),
                dataset_version_id=getattr(record, 'dataset_version_id', None),
                stage_elapsed_seconds=elapsed(getattr(job, 'stage_started_at', None), now),
                task_elapsed_seconds=elapsed(getattr(job, 'started_at', None), now),
                queue_elapsed_seconds=elapsed(getattr(job, 'created_at', None), getattr(job, 'started_at', None)) if getattr(job, 'started_at', None) else None,
                limit_seconds=limit_seconds, timeout_scope=timeout_scope,
                retryable=bool(retryable if retryable is not None else reason_code not in {'TASK_CANCELLED','MODEL_AUTH_FAILED'}),
                legacy=legacy, field_errors=[], preserved_artifact_ids=[])
    if record is not None:
        config = record.request_config_json or {}
        info['request_id'] = config.get('http_request_id') or info['request_id']
        steps = (record.plan_json or {}).get('steps', [])
        active = next((s for s in steps if s.get('status') in {'RUNNING','FAILED'}), {})
        info.update(step_id=identifier(active.get('step_id')), tool_name=identifier(active.get('tool_name')),
                    completed_steps=[identifier(s.get('step_id')) for s in steps if s.get('status')=='COMPLETED'])
    if exception is not None:
        # Log source locations and exception class only, not exception values.
        frames = traceback.extract_tb(exception.__traceback__)[-6:]
        logging.getLogger(__name__).error('Failure request_id=%s record_id=%s type=%s frames=%s',
            info['request_id'], info['record_id'], type(exception).__name__,
            ','.join(f'{f.name}:{f.lineno}' for f in frames))
        chain, current = [], exception
        while current is not None and len(chain)<6:
            chain.append(current)
            current = current.__cause__
        for cause in reversed(chain):
            if not details and isinstance(getattr(cause,'details',None),dict):
                details = cause.details
            if isinstance(cause, ValueError):
                from app.analysis.errors import ToolError
                rule = identifier(str(cause))
                if rule and (rule in PUBLIC_VALIDATION_RULES or isinstance(cause, ToolError)):
                    info['validation_rule'] = rule
                    break
        for cause in chain:
            if hasattr(cause, 'errors'):
                try:
                    info['field_errors'] = validation_fields(cause.errors())
                except (TypeError, ValueError):
                    pass
                break
    if isinstance(details, dict):
        # Tool details may contain data values. Only structural metadata is public.
        for key in ('column', 'expected_type', 'actual_type', 'step_id', 'tool_name'):
            value = details.get(key)
            if isinstance(value, str) and len(value)<=100 and not re.search(r'(?i)password|secret|api.key|://|bearer', value):
                info[key] = value
        for key in ('actual_count', 'max_count', 'actual_length', 'max_length'):
            value = details.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                info[key] = value
        if isinstance(details.get('field_errors'), list):
            # Rebuild messages from rule metadata; never trust free-form tool error text.
            info['field_errors'] = validation_fields([
                {'loc': [f.get('path', '')], 'type': f.get('rule'), 'actual_length': f.get('actual_length'),
                 'ctx': {key:f[key] for key in ('max_length','min_length','ge','le','gt','lt') if key in f}}
                for f in details['field_errors'][:20] if isinstance(f, dict)])
    if legacy:
        info['reason'] = reason + ' 此记录形成于旧版本，详细诊断未记录。'
    return actionable_info(info)


def record_error_info(record):
    if record.error_info_json:
        return actionable_info(record.error_info_json)
    if record.error_code:
        return error_info(record.error_code, record.error_message, record=record, legacy=True)
    return None


def classify_model_error(exc):
    name = type(exc).__name__.lower()
    status = getattr(exc, 'status_code', None)
    if getattr(exc, 'code', None) in {'context_length_exceeded', 'max_context_length_exceeded'}:
        return 'MODEL_CONTEXT_BUDGET_EXCEEDED'
    if 'timeout' in name:
        return 'LLM_CALL_TIMEOUT'
    if status in (401,403) or 'authentication' in name or 'permissiondenied' in name:
        return 'MODEL_AUTH_FAILED'
    if status == 429 or 'ratelimit' in name:
        return 'MODEL_RATE_LIMITED'
    if 'connection' in name or 'connect' in name:
        return 'MODEL_CONNECTION_FAILED'
    return None
