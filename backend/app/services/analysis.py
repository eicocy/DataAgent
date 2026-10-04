"""Submission, idempotency and persistence shared by synchronous and queued APIs."""
import threading
import time
import uuid
from datetime import datetime, UTC
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.config import get_settings
from app.models import User, Dataset, DatasetVersion, DatasetColumn, AnalysisSession, AnalysisRecord, AnalysisMessage, BackgroundJob, ToolExecutionRecord, CleanupTask, AnalysisEvent, LLMCallRecord, AnalysisArtifact
from app.services.artifacts import ArtifactStore
from app.services.analysis_tools import DatasetTools
from app.services.datasets import DatasetService
from app.agent.executor import clip_context

resource_lock = threading.RLock()
ACTIVE = ("pending", "running")


def append_event(db, record, event_type, payload=None):
    db.add(AnalysisEvent(record_id=record.id, user_id=record.user_id, event_type=event_type,
                         payload_json=payload or {}, created_at=datetime.now(UTC)))


def domain_error(status, code, message, data=None):
    return HTTPException(status_code=status, detail={"code": code, "message": message, "data": data})


def submit_analysis(db, user_id, request, allow_switch=False):
    from app.services.run_configuration import public_config, snapshot_config
    settings = get_settings()
    with resource_lock:
        # Row locks make submission/delete serialize at the database resource boundary.
        db.scalar(select(User).where(User.id == user_id).with_for_update())
        existing = db.scalar(select(AnalysisRecord).where(AnalysisRecord.user_id == user_id, AnalysisRecord.request_id == request.request_id))
        if existing:
            if existing.session_id != request.session_id or existing.question != request.question or (request.dataset_id is not None and existing.dataset_id != request.dataset_id) or (existing.request_config_json or {}).get('public', public_config(type('Legacy', (), {})())) != public_config(request):
                raise domain_error(409, "ANALYSIS_REQUEST_ID_CONFLICT", "request_id 已用于另一请求")
            return existing, False
        if not request.question.strip():
            raise domain_error(400, "ANALYSIS_QUESTION_EMPTY", "请输入分析问题")
        session = db.scalar(select(AnalysisSession).where(AnalysisSession.id == request.session_id).with_for_update())
        if not session or session.user_id != user_id:
            raise domain_error(404, "ANALYSIS_SESSION_NOT_FOUND", "分析会话不存在")
        dataset_id = request.dataset_id if request.dataset_id is not None else session.dataset_id
        if not allow_switch and dataset_id != session.dataset_id:
            raise domain_error(409, "ANALYSIS_SESSION_DATASET_MISMATCH", "分析会话与数据集不匹配")
        dataset = db.scalar(select(Dataset).where(Dataset.id == dataset_id).with_for_update()) if dataset_id else None
        if dataset_id and not dataset:
            raise domain_error(404, "DATASET_NOT_FOUND", "数据集不存在")
        if dataset and dataset.user_id != user_id:
            raise domain_error(403, "ANALYSIS_DATASET_FORBIDDEN", "你没有权限分析这个数据集")
        if dataset and dataset.status != "ready":
            raise domain_error(409, "DATASET_NOT_READY", "数据集尚未解析完成")
        # 提交只固定授权版本；可用性由执行入口验证并保存正式澄清响应。
        # 版本已失效也不能在入队前丢失这轮对话，且绝不自动换用新版本。
        version = db.get(DatasetVersion, dataset.current_version_id) if dataset and dataset.current_version_id else None
        if dataset and dataset.current_version_id and (version is None or version.dataset_id != dataset.id):
            raise domain_error(409, 'DATASET_VERSION_UNAVAILABLE', '数据版本不可用')
        requested_inputs = getattr(request, 'inputs', [])
        if requested_inputs and dataset and requested_inputs[0].dataset_id == dataset.id and requested_inputs[0].dataset_version_id:
            version = DatasetService(db).get_version(dataset, requested_inputs[0].dataset_version_id)
        configuration = snapshot_config(db, user_id, session, request, dataset, version)
        if db.scalar(select(AnalysisRecord.id).where(AnalysisRecord.session_id == session.id, AnalysisRecord.status.in_(ACTIVE)).limit(1)):
            raise domain_error(409, "ANALYSIS_SESSION_BUSY", "此会话已有分析任务")
        count = db.scalar(select(func.count()).select_from(AnalysisRecord).where(AnalysisRecord.user_id == user_id, AnalysisRecord.status.in_(ACTIVE))) or 0
        if count >= settings.max_user_active_runs:
            raise domain_error(429, "ANALYSIS_USER_LIMIT", "未完成的分析任务已达上限")
        queued = db.scalar(select(func.count()).select_from(BackgroundJob).where(BackgroundJob.status.in_(ACTIVE))) or 0
        if queued >= settings.max_pending_jobs:
            raise domain_error(429, "TASK_QUEUE_FULL", "任务队列已满，请稍后重试")
        now = datetime.now(UTC)
        message = AnalysisMessage(session_id=session.id, role="user", content=request.question, status="complete", created_at=now)
        db.add(message)
        db.flush()
        if allow_switch and dataset and session.dataset_id != dataset.id:
            from app.agent.context import ConversationContext
            context = ConversationContext.from_session(session)
            state = context.with_dataset(dataset.id, version.id) if version else context
            session.context_json = {**(session.context_json or {}), **state.model_dump(mode='json')}
            session.dataset_id = dataset.id
        record = AnalysisRecord(user_id=user_id, dataset_id=dataset.id if dataset else None, session_id=session.id, request_id=request.request_id,
                                question=request.question, user_message_id=message.id, status="pending", created_at=now,
                                dataset_version_id=version.id if version else None, schema_version='1.1',
                                version_binding='snapshot' if version else 'legacy_unversioned')
        db.add(record)
        record.request_config_json = configuration
        db.flush()
        db.add(BackgroundJob(kind="analysis", resource_id=record.id, dataset_id=dataset.id if dataset else None, user_id=user_id, status="pending", created_at=now))
        append_event(db, record, 'analysis_queued', {'status': 'pending'})
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.scalar(select(AnalysisRecord).where(AnalysisRecord.user_id == user_id, AnalysisRecord.request_id == request.request_id))
            if existing and existing.session_id == request.session_id and existing.question == request.question and (request.dataset_id is None or existing.dataset_id == request.dataset_id) and (existing.request_config_json or {}).get('public', public_config(type('Legacy', (), {})())) == public_config(request):
                return existing, False
            raise domain_error(409, "ANALYSIS_REQUEST_ID_CONFLICT", "重复提交发生冲突") from None
        return record, True


def select_projection_bind(dataset, business_bind, projection_bind):
    schema = dataset.projection_schema
    if not schema or schema == business_bind.url.database:
        return business_bind
    if schema == projection_bind.url.database:
        return projection_bind
    raise ValueError("Unknown server projection location")


class WorkerLeaseLost(Exception):
    pass


class VersionUnavailable(Exception):
    code = 'DATASET_VERSION_UNAVAILABLE'
    public_message = '原分析所用的数据集版本已不可用，请恢复该版本或选择数据集重新分析。'


def execute_record(db, record_id, agent, business_bind, projection_bind, readonly_bind=None, job_id=None, lease_token=None):
    if lease_token:
        job = db.scalar(select(BackgroundJob).where(BackgroundJob.id == job_id).with_for_update().execution_options(populate_existing=True))
        if not job or job.status != "running" or job.lease_token != lease_token or job.cancel_requested:
            db.rollback()
            return
    record = db.get(AnalysisRecord, record_id)
    if not record or record.status not in ACTIVE:
        return
    record.status = "running"
    db.commit()
    started = time.monotonic()
    dataset = None
    columns = []
    pinned_version = None
    tools = None
    prepared = None
    preflight_error = None
    store = ArtifactStore(db)

    def check_lease():
        if lease_token:
            job = db.scalar(select(BackgroundJob).where(BackgroundJob.id == job_id).with_for_update().execution_options(populate_existing=True))
            if not job or job.status != "running" or job.lease_token != lease_token or job.cancel_requested:
                raise WorkerLeaseLost()

    active_execution=None

    def event(kind, payload):
        nonlocal active_execution
        check_lease()
        if kind == "plan":
            first_plan = record.plan_json is None
            record.plan_json = payload
            steps = payload.get('steps', [])
            running = next((item.get('step_id') for item in steps if item.get('status') == 'RUNNING'), None)
            append_event(db, record, 'plan_created' if first_plan else 'plan_updated',
                         {'status': payload.get('status'), 'current_step': running,
                          'completed': sum(item.get('status') == 'COMPLETED' for item in steps), 'total': len(steps)})
        elif kind == "usage":
            record.usage_json = payload
        elif kind == 'intent':
            record.intent_summary = payload['intent']
            append_event(db, record, 'intent_resolved', payload)
        elif kind == 'llm_call':
            db.add(LLMCallRecord(request_id=record.request_id, record_id=record.id,
                conversation_id=record.session_id, user_id=record.user_id,
                provider=payload['provider'], model=payload['model'],
                prompt_version=payload['prompt_version'], input_tokens=payload.get('input_tokens'),
                output_tokens=payload.get('output_tokens'), latency_ms=payload.get('latency_ms'),
                status=payload['status'], error_code=payload.get('error_code'), created_at=datetime.now(UTC)))
            append_event(db, record, 'model_call_completed',
                         {'prompt_version': payload['prompt_version'], 'status': payload['status']})
        elif kind == "call":
            from app.analysis.catalog import build_registry
            registry=build_registry(include_legacy=True)
            request_id='agent-'+uuid.uuid5(uuid.NAMESPACE_OID,f'{record.id}:{payload["call_id"]}').hex
            execution=db.scalar(select(ToolExecutionRecord).where(ToolExecutionRecord.user_id==record.user_id,ToolExecutionRecord.request_id==request_id))
            if execution is None:
                alias = payload.get('input_alias') or next((s.get('input_alias', 'primary') for s in (record.plan_json or {}).get('steps', []) if s['step_id'] == payload.get('step_id')), 'primary')
                binding = next((i for i in (record.request_config_json or {}).get('inputs', []) if i['alias'] == alias), {})
                tool_version=registry.get(payload['tool_name']).metadata.version if registry.exists(payload['tool_name']) else 'legacy'
                execution=ToolExecutionRecord(user_id=record.user_id,dataset_id=binding.get('dataset_id', record.dataset_id),dataset_version_id=binding.get('dataset_version_id', record.dataset_version_id),analysis_record_id=record.id,tool_name=payload['tool_name'],tool_version=tool_version,request_id=request_id,parameters_json={},permissions_json=[p.value for p in tools.permissions],status=payload['status'],created_at=datetime.now(UTC),started_at=datetime.now(UTC) if payload['status']=='running' else None)
                db.add(execution)
            execution.status=payload['status'];execution.duration_ms=payload.get('duration_ms',0)
            if payload.get('reused') and payload.get('artifact_id'):
                execution.result_json = {'artifact_ref': payload['artifact_id'],
                    'dataset_version': record.dataset_version_id, 'source_ref': payload['step_id'], 'reused': True}
            if payload['status'] in {'succeeded','failed','skipped'}:
                execution.finished_at=datetime.now(UTC)
                if payload.get('error_code'):
                    execution.error_json={'code':payload['error_code'],'message':'工具步骤未完成','details':{},'recoverable':False,'suggestion':'检查参数或数据后显式重试'}
            active_execution=execution
            calls = list(record.tool_calls_json or [])
            index = next((i for i, call in enumerate(calls) if call.get("call_id", call.get("tool_call_id")) == payload["call_id"]), None)
            if index is None:
                calls.append(dict(payload, tool_call_id=payload["call_id"]))
            else:
                calls[index] = dict(payload, tool_call_id=payload["call_id"])
            record.tool_calls_json = calls
            event_name = {'running': 'step_started', 'succeeded': 'step_completed',
                          'failed': 'step_failed', 'skipped': 'step_skipped'}.get(payload['status'], 'step_updated')
            append_event(db, record, event_name,
                         {'step_id': payload.get('step_id'), 'tool_name': payload.get('tool_name'),
                          'status': payload['status'], 'error_code': payload.get('error_code')})
            if payload['status'] == 'running':
                append_event(db, record, 'tool_started', {'step_id': payload.get('step_id'),
                    'tool_name': payload.get('tool_name')})
        elif kind=='tool_parameters' and active_execution:
            active_execution.parameters_json=payload['parameters']
        elif kind == "result":
            artifact_name=uuid.uuid4().hex+'.json'
            cleanup=CleanupTask(payload_json={'artifacts':[artifact_name],'analysis_record_id':record.id},status='reserved',created_at=datetime.now(UTC))
            db.add(cleanup);db.commit();check_lease()
            from types import SimpleNamespace
            artifact_owner = SimpleNamespace(id=record.id, user_id=record.user_id, dataset_id=active_execution.dataset_id if active_execution else record.dataset_id)
            result = store.write(artifact_owner, payload["step_id"], payload["data"], payload["frame"], "chart" if payload["tool_name"] == "generate_chart" else "table",stored_name=artifact_name)
            check_lease()
            cleanup.status='succeeded'
            if active_execution:
                active_execution.result_json={'artifact_ref':result['artifact_id'],'dataset_version':active_execution.dataset_version_id,'source_ref':payload['step_id'],'data':clip_context(payload['data'],max_rows=100)}
            if payload["tool_name"] != "generate_chart":
                record.tool_result_json = clip_context(payload["data"], max_rows=100)
            else:
                record.chart_json = dict(payload["data"], artifact_id=result["artifact_id"])
            append_event(db, record, 'tool_completed', {'step_id': payload['step_id'], 'artifact_id': result['artifact_id']})
            db.commit()
            return result
        elif kind == "stage" and job_id:
            job = db.get(BackgroundJob, job_id)
            if job:
                job.active_stage = payload["stage"]
                job.stage_timeout_seconds=payload.get('timeout_seconds')
                job.stage_started_at = datetime.now(UTC).replace(tzinfo=None)
            if payload['stage'] != 'idle':
                append_event(db, record, 'stage_changed', {'stage': payload['stage']})
        elif kind in {'plan_validated', 'step_ready', 'result_validated', 'retry', 'replan',
                      'plan_completed', 'interpretation_started', 'interpretation_rejected', 'interpretation_retry', 'profile_selected', 'exploration_created'}:
            append_event(db, record, kind, payload)
        db.commit()

    if hasattr(agent, 'prepare'):
        try:
            from app.agent.context import ConversationContext, DatasetCandidate
            session = db.get(AnalysisSession, record.session_id)
            context = ConversationContext.from_session(session,
                active_dataset_version_id=record.dataset_version_id if session.dataset_id == record.dataset_id else None)
            owned = db.scalars(select(Dataset).where(Dataset.user_id == record.user_id,
                                                     Dataset.status == 'ready').order_by(Dataset.id.asc())).all()
            candidates = []
            for item in owned:
                try:
                    version = DatasetService(db).get_version(item)
                except HTTPException:
                    continue
                if version:
                    candidates.append(DatasetCandidate(id=item.id, name=item.original_name, version_id=version.id))
            if record.request_config_json and record.request_config_json.get('inputs'):
                from app.agent.budget import RuntimeBudget
                runtime_budget = RuntimeBudget.for_depth(record.request_config_json['depth'])
                prepared = agent.prepare(record.question, context, candidates, record.dataset_id, event, runtime_budget=runtime_budget)
            else:
                prepared = agent.prepare(record.question, context, candidates, record.dataset_id, event)
            _, decision, resolution = prepared
            if record.request_config_json and record.request_config_json.get('inputs') and decision.requires_dataset:
                pinned = record.request_config_json['inputs'][0]
                if resolution.dataset_id not in {i['dataset_id'] for i in record.request_config_json['inputs']}:
                    resolution.needs_clarification = True
                resolution.dataset_id, resolution.dataset_version_id = pinned['dataset_id'], pinned['dataset_version_id']
            if decision.requires_dataset and not decision.dataset_reference and record.version_binding == 'snapshot':
                try:
                    if record.dataset_version_id is None:
                        raise VersionUnavailable()
                    DatasetService(db).get_version(db.get(Dataset, record.dataset_id), record.dataset_version_id)
                except HTTPException as exc:
                    raise VersionUnavailable() from exc
            if resolution.dataset_id is not None:
                if (record.dataset_id, record.dataset_version_id) != (resolution.dataset_id, resolution.dataset_version_id):
                    record.dataset_id, record.dataset_version_id = resolution.dataset_id, resolution.dataset_version_id
                    record.version_binding = 'snapshot'
                if session.dataset_id != resolution.dataset_id:
                    session.dataset_id = resolution.dataset_id
                context = context.with_dataset(resolution.dataset_id, resolution.dataset_version_id)
            context.current_intent = decision.intent
            session.context_json = {**(session.context_json or {}), **context.model_dump(mode='json')}
            db.commit()
        except Exception as exc:
            preflight_error = exc
    try:
        if preflight_error:
            raise preflight_error
        if not prepared or ((prepared[1].requires_analysis or prepared[1].intent == 'DATA_CLEANING') and
                            not prepared[2].needs_clarification and prepared[2].dataset_id is not None):
            dataset = db.get(Dataset, record.dataset_id) if record.dataset_id else None
            if dataset is None:
                raise ValueError('DATASET_REQUIRED')
            if record.version_binding == 'snapshot' and record.dataset_version_id is None:
                raise VersionUnavailable()
            columns = db.scalars(select(DatasetColumn).where(DatasetColumn.dataset_id == dataset.id).order_by(DatasetColumn.ordinal_position)).all()
            try:
                pinned_version = DatasetService(db).get_version(dataset, record.dataset_version_id)
            except HTTPException as exc:
                raise VersionUnavailable() from exc
            if prepared and pinned_version is None:
                raise VersionUnavailable()
            tools = DatasetTools(dataset, columns, select_projection_bind(pinned_version or dataset, business_bind, projection_bind), readonly_bind)
            tools.check_lease = check_lease
            tools.on_event = event
            if prepared:
                tools.prepared = prepared
                tools.conversation_state = context
                tools.record_id = record.id
            previous = db.scalars(select(AnalysisRecord).where(AnalysisRecord.session_id == record.session_id, AnalysisRecord.id != record.id,
                                                         AnalysisRecord.user_id == record.user_id, AnalysisRecord.status.in_(("succeeded", "partial"))).order_by(AnalysisRecord.id.desc()).limit(3)).all()
            tools.conversation_context = clip_context({"analyses": [{"question": item.question, "report": {"answer": item.final_answer, "status": item.status}} for item in reversed(previous)]}, max_chars=8000).get("analyses", [])
            tools.reuse_steps = {}
            if prepared and (prepared[1].follow_up or prepared[1].intent in {'CHART_GENERATION', 'DATA_FILTER', 'FOLLOW_UP_ANALYSIS'}):
                source = next((item for item in previous if item.dataset_id == record.dataset_id and
                               item.dataset_version_id == record.dataset_version_id and
                               (item.plan_json or {}).get('version') == '2.0'), None)
                if source:
                    for old_step in source.plan_json.get('steps', []):
                        ref = old_step.get('result_ref') or ''
                        if old_step.get('status') != 'COMPLETED' or not ref.startswith('artifact:'):
                            continue
                        try:
                            artifact = db.get(AnalysisArtifact, int(ref.split(':', 1)[1]))
                            if artifact is None or artifact.record_id != source.id or artifact.user_id != record.user_id or artifact.dataset_id != record.dataset_id:
                                continue
                            payload = store.read(artifact)
                            tools.reuse_steps[old_step['step_id']] = {'step': old_step,
                                'artifact_id': artifact.id, 'payload': payload}
                        except (LookupError, ValueError):
                            continue
        service = DatasetService(db, tools.writer_bind) if tools else None
        if tools and record.dataset_version_id is not None:
            service.get_version(dataset, record.dataset_version_id)
            try:
                tools.frame = service.load_frame(dataset, columns, record.dataset_version_id)
            except (LookupError, HTTPException) as exc:
                raise VersionUnavailable() from exc
            tools.dataset_version_id=record.dataset_version_id
            tools.projection_table=pinned_version.projection_table
            from types import SimpleNamespace
            from app.datasets.schemas import DatasetSchema,column_storage_type
            schema=DatasetSchema.model_validate(pinned_version.schema_json)
            tools.version_schema=schema
            from app.datasets.schemas import DatasetProfile
            tools.version_profile=DatasetProfile.model_validate(pinned_version.profile_json)
            columns=[SimpleNamespace(name=column.name,original_name=column.original_name,data_type=column_storage_type(column),nullable=bool(tools.frame[column.name].isna().any()),missing_count=int(tools.frame[column.name].isna().sum()),unique_count=int(tools.frame[column.name].nunique()),sample_values_json=[]) for column in schema.columns]
            tools.columns=columns;tools.schema={column.name:column for column in columns}
        if tools:
            tools.model_metadata = service.model_metadata(dataset, columns, record.dataset_version_id)
            if record.request_config_json and record.request_config_json.get('inputs'):
                from app.services.input_workspace import load_workspace
                from copy import deepcopy
                tools = load_workspace(db, record.user_id, deepcopy(record.request_config_json), tools, business_bind, projection_bind, readonly_bind, event, check_lease)
            outcome = agent.analyze(record.question, tools)
            if getattr(tools, 'configuration', None):
                record.request_config_json = tools.configuration
            if prepared and prepared[1].intent == 'DATA_CLEANING':
                notice = '当前聊天入口只能进行数据质量分析并提供建议，不能执行清洗或发布新版本。'
                outcome.answer = (outcome.answer + '\n' if outcome.answer else '') + notice
                if outcome.report:
                    outcome.report['answer'] = outcome.answer
                    outcome.report.setdefault('warnings', []).append(notice)
        else:
            outcome = agent.respond_without_analysis(record.question, prepared)
        record.tool_calls_json = outcome.tool_calls
        record.tool_result_json = clip_context(outcome.tool_result, max_rows=100)
        record.chart_json = outcome.chart
        record.final_answer = outcome.answer
        record.status = outcome.status
        record.plan_json = getattr(outcome, "plan", None) or record.plan_json
        record.report_json = getattr(outcome, "report", None)
        record.usage_json = getattr(outcome, "usage", None)
        record.primary_tool_name = next((call["tool_name"] for call in outcome.tool_calls if call.get("status") == "succeeded" and call["tool_name"] not in {"get_dataset_info", "preview_data", "generate_chart"}), None)
    except WorkerLeaseLost:
        db.rollback()
        return
    except VersionUnavailable as exc:
        db.rollback()
        record = db.get(AnalysisRecord, record_id)
        record.status = 'waiting'
        record.error_code = exc.code
        record.final_answer = exc.public_message
        record.report_json = {'version': '1.0', 'status': 'waiting', 'answer': exc.public_message,
            'tables': [], 'charts': [], 'warnings': [exc.public_message],
            'evidence_refs': [], 'incomplete_steps': []}
    except Exception as exc:
        db.rollback()
        try:
            check_lease()
        except WorkerLeaseLost:
            db.rollback()
            return
        record = db.get(AnalysisRecord, record_id)
        for task in db.scalars(select(CleanupTask).where(CleanupTask.status=='reserved')):
            if task.payload_json.get('analysis_record_id')==record.id:task.status='pending'
        code = getattr(exc, "code", "ANALYSIS_FAILED")
        message = getattr(exc, "public_message", "分析失败，请稍后重试")
        for execution in db.scalars(select(ToolExecutionRecord).where(ToolExecutionRecord.analysis_record_id==record.id,ToolExecutionRecord.status=='running')):
            execution.status='failed';execution.finished_at=datetime.now(UTC)
            execution.error_json={'code':code,'message':message,'details':{},'recoverable':False,'suggestion':'显式重试分析'}
        record.status = "partial" if record.tool_result_json else "failed"
        calls = list(record.tool_calls_json or [])
        for call in calls:
            if call.get("status") == "running":
                call.update(status="failed", error_code=code, result_summary="执行中断")
        record.tool_calls_json = calls
        record.error_code, record.error_message = code, message
        if record.status == "partial":
            record.report_json = {"version": "1.0", "status": "partial", "answer": None, "tables": [record.tool_result_json], "charts": [record.chart_json] if record.chart_json else [], "warnings": [message], "evidence_refs": [], "incomplete_steps": []}
    record.intent_summary = record.intent_summary or record.question[:500]
    try:
        check_lease()
    except WorkerLeaseLost:
        db.rollback()
        return
    record.execution_time_ms = int((time.monotonic() - started) * 1000)
    record.completed_at = datetime.now(UTC)
    message = AnalysisMessage(session_id=record.session_id, role="assistant", content=record.final_answer or record.error_message or "计算已完成，模型总结暂不可用", status=record.status, created_at=record.completed_at)
    db.add(message)
    db.flush()
    record.assistant_message_id = message.id
    session = db.get(AnalysisSession, record.session_id)
    session.updated_at = record.completed_at
    if hasattr(agent, 'prepare'):
        from app.agent.context import ConversationContext
        context = ConversationContext.from_session(session)
        context.current_goal = (record.plan_json or {}).get('goal')
        if record.request_config_json:
            context.selected_profiles = (record.plan_json or {}).get('profiles', context.selected_profiles)
        if record.plan_json and record.status in {'succeeded', 'partial'}:
            context.previous_plan = clip_context(record.plan_json, max_chars=8000)
            context.previous_analysis = {'record_id': record.id, 'dataset_id': record.dataset_id,
                'dataset_version_id': record.dataset_version_id, 'question': record.question[:500],
                'answer': (record.final_answer or '')[:1000]}
            context.previous_result_ref = next((step.get('result_ref') for step in reversed(record.plan_json.get('steps', []))
                if step.get('result_ref') and step.get('tool_name') != 'generate_chart'), None)
            context.last_chart_spec = record.chart_json if record.chart_json else context.last_chart_spec
            filters, dimensions, metrics = [], [], []
            for step in record.plan_json.get('steps', []):
                args = step.get('arguments') or {}
                filters.extend(args.get('conditions') or [])
                dimensions.extend(value for key in ('group_column', 'date_column')
                    if isinstance(value := args.get(key), str))
                metrics.extend(item.get('column') for item in args.get('metrics', [])
                    if isinstance(item, dict) and isinstance(item.get('column'), str))
            context.active_filters = filters[:20]
            context.active_dimensions = list(dict.fromkeys(dimensions))[:20]
            context.active_metrics = list(dict.fromkeys(metrics))[:20]
        context.messages_summary = (context.messages_summary + '\n用户：' + record.question[:300] +
            '\n助手：' + (record.final_answer or record.error_message or '')[:500])[-4000:]
        session.context_json = {**(session.context_json or {}), **context.model_dump(mode='json')}
    if session.title == "新分析":
        session.title = record.question[:60]
    if job_id:
        job = db.get(BackgroundJob, job_id)
        job.status = "succeeded" if record.status in {"succeeded", "partial", "waiting"} else "failed"
        job.completed_at = datetime.now(UTC).replace(tzinfo=None)
        job.error_code = record.error_code
    append_event(db, record, 'clarification_required' if record.status == 'waiting' else
                 'response_ready' if record.status in {'succeeded', 'partial'} else 'analysis_failed',
                 {'status': record.status, 'record_id': record.id})
    db.commit()
    return record
