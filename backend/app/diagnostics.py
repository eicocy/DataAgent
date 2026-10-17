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
}


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
                rule = identifier(str(cause))
                if rule and rule.upper()==rule:
                    info['validation_rule'] = rule
                    break
        for cause in chain:
            if hasattr(cause, 'errors'):
                try:
                    info['field_errors'] = [{'path': '.'.join(str(v) for v in e['loc']), 'rule': e['type']}
                                            for e in cause.errors()[:20]]
                except (TypeError, ValueError):
                    pass
                break
    if isinstance(details, dict):
        # Tool details may contain data values. Only structural metadata is public.
        for key in ('column', 'expected_type', 'actual_type', 'step_id', 'tool_name'):
            value = details.get(key)
            if isinstance(value, str) and len(value)<=100 and not re.search(r'(?i)password|secret|api.key|://|bearer', value):
                info[key] = value
        if info.get('validation_rule')=='COLUMN_NOT_FOUND' and info.get('column'):
            info['reason'] = f"步骤 {info.get('step_id') or '未记录'} 引用了当前固定数据版本中不存在的字段：{info['column']}。"
    if legacy:
        info['reason'] = reason + ' 此记录形成于旧版本，详细诊断未记录。'
    return info


def record_error_info(record):
    if record.error_info_json:
        return record.error_info_json
    if record.error_code:
        return error_info(record.error_code, record.error_message, record=record, legacy=True)
    return None


def classify_model_error(exc):
    name = type(exc).__name__.lower()
    status = getattr(exc, 'status_code', None)
    if 'timeout' in name:
        return 'LLM_CALL_TIMEOUT'
    if status in (401,403) or 'authentication' in name or 'permissiondenied' in name:
        return 'MODEL_AUTH_FAILED'
    if status == 429 or 'ratelimit' in name:
        return 'MODEL_RATE_LIMITED'
    if 'connection' in name or 'connect' in name:
        return 'MODEL_CONNECTION_FAILED'
    return None
