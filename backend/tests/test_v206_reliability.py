"""Regression checks for persisted failures and bounded conversation state."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import User, AnalysisSession, AnalysisRecord, BackgroundJob
from app.services.jobs import terminate_job
from test_analysis_api import analysis_context


def test_model_timeout_survives_history_and_emits_one_terminal_event():
    from app.models import AnalysisEvent
    bind = create_engine('sqlite://')
    Base.metadata.create_all(bind)
    factory = sessionmaker(bind=bind, expire_on_commit=False)
    now = datetime.now(UTC).replace(tzinfo=None)
    with factory() as db:
        user = User(username='diagnostic', password_hash='hash', created_at=now, updated_at=now)
        db.add(user); db.flush()
        session = AnalysisSession(user_id=user.id, title='probe', created_at=now, updated_at=now)
        db.add(session); db.flush()
        record = AnalysisRecord(user_id=user.id, session_id=session.id, request_id='probe',
                                question='probe', status='running', created_at=now)
        db.add(record); db.flush()
        job = BackgroundJob(user_id=user.id, kind='analysis', resource_id=record.id, status='running',
                            active_stage='llm', stage_timeout_seconds=30,
                            stage_started_at=now-timedelta(seconds=31),
                            started_at=now-timedelta(seconds=36), created_at=now)
        db.add(job); db.commit()
        rid, jid = record.id, job.id
    terminate_job(factory, jid, 'TASK_TIMEOUT')
    terminate_job(factory, jid, 'TASK_TIMEOUT')
    with factory() as db:
        record = db.get(AnalysisRecord, rid)
        assert record.error_info_json['stage'] == 'llm'
        assert record.error_info_json['reason_code'] == 'LLM_CALL_TIMEOUT'
        assert record.error_info_json['limit_seconds'] == 30
        assert record.error_info_json['stage_elapsed_seconds'] >= 30
        assert record.execution_time_ms >= 35000
        assert db.query(AnalysisEvent).filter_by(record_id=rid, event_type='analysis_failed').count() == 1


def test_recent_context_is_shared_with_general_chat_and_intent():
    from app.agent.context import ConversationContext, DatasetResolution
    from app.agent.intent import IntentRouter
    from app.services.analysis_agent import DeepSeekAgent
    class Provider:
        def generate_structured(self, name, payload, schema):
            self.intent = payload
            return {'intent': 'GENERAL_CHAT', 'confidence': 1}
        def generate_text(self, name, payload):
            self.chat = payload
            return '万元'
    provider = Provider()
    context = ConversationContext(conversation_id=1, user_id=1,
        messages_summary='old'*900+'最新：金额用万元',
        recent_messages=[{'role':'user','content':'金额用万元'}])
    IntentRouter(provider).route('我刚才说了什么', context)
    prepared = (provider, SimpleNamespace(intent='GENERAL_CHAT'), DatasetResolution())
    DeepSeekAgent(settings=SimpleNamespace()).respond_without_analysis('我刚才说了什么', prepared, context=context)
    assert provider.intent['summary'].endswith('金额用万元')
    assert provider.chat['recent_messages'][-1]['content'] == '金额用万元'


def test_explicit_mean_is_not_blocked_by_profile_keywords():
    from app.profiles.catalog import profile_catalog
    from app.agent.template_router import AnalysisTemplateRouter
    route = AnalysisTemplateRouter(profile_catalog()['items']).route('x 的平均值是多少')
    assert not route.needs_clarification


def test_sdk_timeout_is_clamped_to_shared_remaining_budget(monkeypatch):
    from app.agent.model_adapter import ModelAdapter
    from app.config import Settings
    events, options = [], []
    class Model:
        def bind(self, **kwargs):
            options.append(kwargs)
            return self
        def invoke(self, messages, **kwargs):
            options.append(kwargs)
            return SimpleNamespace(usage_metadata={}, content='ok')
    adapter = ModelAdapter(Model(), Settings(_env_file=None, deepseek_api_key='', analysis_timeout_seconds=60,
                                             llm_timeout_seconds=90), lambda k,p:events.append((k,p)))
    adapter.invoke('probe', '{}')
    stage = next(payload for name,payload in events if name=='stage' and payload['stage']=='llm')
    assert 0 < stage['timeout_seconds'] <= 58
    assert any(item.get('timeout', 100) <= 58 for item in options)


def test_context_patch_validates_schema_and_clears_then_replaces_conditions():
    import pytest
    from app.agent.context import ConversationContext, ContextPatch, apply_context_patch, extract_plan_state
    from app.analysis.errors import ToolInputError
    context = ConversationContext(conversation_id=1,user_id=1,active_filters=[{'column':'region','operator':'eq','value':'East'}])
    apply_context_patch(context, ContextPatch(filters=[{'column':'region','operator':'eq','value':'West'}]), ['region','sales'])
    assert context.active_filters[0]['value']=='West'
    with pytest.raises(ToolInputError):
        apply_context_patch(context, ContextPatch(dimensions=['unknown']), ['region','sales'])
    apply_context_patch(context,None,['region','sales'],'取消所有筛选条件')
    assert context.active_filters==[]
    extract_plan_state(context,{'steps':[{'tool_name':'aggregate','arguments':{'filters':[{'column':'region','operator':'eq','value':'West'}],
                       'dimensions':['region'],'metrics':[{'column':'sales','aggregation':'sum'}]}}]})
    assert context.active_dimensions==['region'] and context.active_metrics==['sales']
    assert context.with_dataset(2,3).active_filters==[]


def test_model_errors_do_not_serialize_exception_values():
    from app.diagnostics import classify_model_error,error_info
    import json
    for status, expected in [(401,'MODEL_AUTH_FAILED'),(429,'MODEL_RATE_LIMITED')]:
        exc=RuntimeError('password=private-token')
        exc.status_code=status
        assert classify_model_error(exc)==expected
        assert 'private-token' not in json.dumps(error_info('MODEL_UNAVAILABLE',reason_code=expected,exception=exc))


def test_deep_deadline_and_selective_filter_removal(monkeypatch):
    from app.agent.budget import task_deadline_context
    from app.agent.model_adapter import ModelAdapter
    from app.config import Settings
    from app.agent.context import ConversationContext,ContextPatch,apply_context_patch,extract_plan_state,conversation_payload
    clock=[100.0]
    monkeypatch.setattr('app.agent.model_adapter.time.monotonic',lambda:clock[0])
    token=task_deadline_context.set(700.0)
    try:
        adapter=ModelAdapter(SimpleNamespace(),Settings(_env_file=None,deepseek_api_key=''))
        clock[0]=301.0
        assert adapter.deadline-clock[0]==399
    finally:
        task_deadline_context.reset(token)
    context=ConversationContext(conversation_id=1,user_id=1,active_filters=[
        {'column':'region','operator':'eq','value':'East'}, {'column':'year','operator':'eq','value':2026}])
    apply_context_patch(context,ContextPatch(clear_filter_columns=['region']),['region','year'],'取消筛选条件中的地区限制，保留年份')
    assert context.active_filters==[{'column':'year','operator':'eq','value':2026}]
    extract_plan_state(context,{'steps':[{'input_alias':'primary','source_ref':'dataset','arguments':{'logic':'or','filters':[
        {'column':'region','operator':'eq','value':'East'},{'column':'region','operator':'eq','value':'West'}]}}]})
    assert any(g['logic']=='or' for g in conversation_payload(context)['filter_groups'])
    assert all(f['column']!='region' for f in context.active_filters)
    from app.diagnostics import error_info
    assert error_info('COLUMN_TYPE',suggestion='请改用数值字段')['suggestion']=='请改用数值字段'


def test_plan_group_merge_retains_unrelated_inherited_filter():
    from app.agent.context import ConversationContext,ContextPatch,apply_context_patch,extract_plan_state
    context=ConversationContext(conversation_id=1,user_id=1,active_filters=[
        {'column':'region','operator':'eq','value':'East'}, {'column':'year','operator':'eq','value':2026}])
    apply_context_patch(context,ContextPatch(filters=[{'column':'region','operator':'eq','value':'West'}]),['region','year'])
    extract_plan_state(context,{'steps':[{'arguments':{'filters':[{'column':'region','operator':'eq','value':'West'}]}}]})
    assert {f['column'] for g in context.active_filter_groups for f in g['filters']}=={'region','year'}
    assert {f['column'] for f in context.active_filters}=={'region','year'}
    context.active_filter_groups=[{'input_alias':'primary','source_ref':'dataset','logic':'or','filters':[
        {'column':'year','operator':'eq','value':2025},{'column':'region','operator':'eq','value':'East'}]}]
    context.active_filters=[]
    apply_context_patch(context,ContextPatch(filters=[{'column':'region','operator':'eq','value':'West'}]),['region','year'])
    extract_plan_state(context,{'steps':[{'arguments':{'filters':[{'column':'region','operator':'eq','value':'West'}]}}]})
    assert len(context.active_filter_groups)==1 and context.active_filter_groups[0]['logic']=='or'
    assert {f['column'] for f in context.active_filter_groups[0]['filters']}=={'year','region'}


def test_plan_column_error_keeps_safe_step_and_field_details():
    from app.diagnostics import error_info
    cause=ValueError('COLUMN_NOT_FOUND')
    cause.details={'column':'unknown_count','step_id':'count_step','tool_name':'aggregate','raw_input':'private-value'}
    try:
        raise ValueError('PLAN_INVALID') from cause
    except ValueError as error:
        info=error_info('PLAN_INVALID',exception=error,stage='planning')
    assert info['column']=='unknown_count' and info['step_id']=='count_step'
    assert 'unknown_count' in info['reason']
    assert 'private-value' not in str(info)


def test_invalid_plan_diagnostic_survives_run_history_and_session(analysis_context):
    from app.agent.providers import FakeLLMProvider
    from app.services.analysis import execute_record
    from app.services.analysis_agent import DeepSeekAgent
    client,factory,_=analysis_context
    dataset=client.post('/api/v1/datasets/upload',files={'file':('sample.csv',b'x\n1\n3\n','text/csv')}).json()['data']
    did=dataset['id']
    sid=client.post('/api/v1/analysis/sessions',json={'dataset_id':did}).json()['data']['id']
    rid=client.post('/api/v1/analysis/runs',json={'session_id':sid,'dataset_id':did,'question':'分析平均值',
        'depth':'STANDARD','request_id':'diagnostic-history'},headers={'X-Request-ID':'diagnostic-correlation'}).json()['data']['record_id']
    with factory() as db:
        record=db.get(AnalysisRecord,rid)
        plan={'task_id':str(rid),'goal':'mean','intent':'DATA_ANALYSIS','dataset_id':did,'dataset_version_id':record.dataset_version_id,
              'inputs':[{'alias':'primary','dataset_id':did,'dataset_version_id':record.dataset_version_id}],
              'steps':[{'step_id':'bad_field','tool_name':'column_summary','arguments':{'columns':['unknown_count']}}]}
        def provider(emit):
            return FakeLLMProvider([{'intent':'DATA_ANALYSIS','confidence':1},plan,plan],emit)
        execute_record(db,rid,DeepSeekAgent(provider_factory=provider),db.get_bind(),db.get_bind())
    run=client.get(f'/api/v1/analysis/runs/{rid}').json()['data']['error_info']
    assert run['validation_rule']=='COLUMN_NOT_FOUND'
    assert run['column']=='unknown_count' and run['step_id']=='bad_field'
    assert run['stage']=='planning' and run['request_id']=='diagnostic-correlation'
    history=client.get(f'/api/v1/history/{rid}').json()['data']['error_info']
    assert history==run
    session=client.get(f'/api/v1/analysis/sessions/{sid}').json()['data']
    assert any(m.get('analysis_record',{}).get('error_info')==run for m in session['messages'] if m.get('analysis_record'))


def test_group_count_can_sort_by_its_own_output_alias():
    """A top-ten request sorts the computed count, not a raw dataset column."""
    from app.agent.planner import Planner
    from app.agent.providers import FakeLLMProvider
    from app.agent.context import ConversationContext
    from app.analysis.models import Permission
    binding={'alias':'primary','dataset_id':1,'dataset_version_id':4}
    raw={'task_id':'count','goal':'genres top10','intent':'DATA_ANALYSIS','dataset_id':1,'dataset_version_id':4,
         'inputs':[binding],'steps':[{'step_id':'genres_count','tool_name':'groupby_aggregate',
         'arguments':{'dimensions':['genres'],'metrics':[{'column':'movieid','aggregation':'count','alias':'movie_count'}],
                      'sort':[{'column':'movie_count','direction':'desc'}],'limit':10}}]}
    class CaptureProvider(FakeLLMProvider):
        def generate_structured(self,name,payload,schema):
            self.payload=payload
            return super().generate_structured(name,payload,schema)
    provider=CaptureProvider([raw,raw])
    plan=Planner(provider).plan_v3('按 genres 统计电影数量，取前10组',
        {'primary':{'columns':[{'name':'movieid','data_type':'integer'},{'name':'genres','data_type':'string'}]}},
        ConversationContext(conversation_id=1,user_id=1),task_id='count',intent='DATA_ANALYSIS',
        config={'inputs':[binding],'profiles':[],'semantic_snapshot':[],'semantic_version':0,'depth':'STANDARD'},
        permissions=frozenset({Permission.READ_DATA}))
    assert plan.steps[0].arguments['sort'][0]['column']=='movie_count'
    assert {'top_n','bottom_n'} <= {tool['name'] for tool in provider.payload['tools']}


def test_aggregate_output_sort_still_rejects_unknown_source_and_output_columns():
    import pytest
    from app.agent.schemas import AnalysisPlanV3
    from app.agent.task_graph import validate_graph
    from app.analysis.models import Permission
    binding={'alias':'primary','dataset_id':1,'dataset_version_id':4}
    for metric,sort_column in [('missing_raw','movie_count'),('movieid','missing_result')]:
        plan=AnalysisPlanV3.model_validate({'task_id':'bad','goal':'count','intent':'DATA_ANALYSIS',
            'dataset_id':1,'dataset_version_id':4,'inputs':[binding],
            'steps':[{'step_id':'count','tool_name':'groupby_aggregate','arguments':{
                'dimensions':['genres'],'metrics':[{'column':metric,'aggregation':'count','alias':'movie_count'}],
                'sort':[{'column':sort_column,'direction':'desc'}]}}]})
        with pytest.raises(ValueError,match='COLUMN_NOT_FOUND'):
            validate_graph(plan,{'primary':{'movieid':'integer','genres':'string'}},frozenset({Permission.READ_DATA}))


def test_migration_preserves_legacy_records(tmp_path,monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text,inspect
    from app.config import get_settings
    url='sqlite:///'+(tmp_path/'migration.db').as_posix()
    monkeypatch.setattr(get_settings(),'migration_database_url',url)
    cfg=Config('alembic.ini')
    command.upgrade(cfg,'0012_artifact_workspace')
    bind=create_engine(url)
    with bind.begin() as connection:
        connection.execute(text("INSERT INTO users(username,password_hash,status,created_at,updated_at) VALUES ('keep','hash','active',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
    command.upgrade(cfg,'head')
    command.upgrade(cfg,'head')
    with bind.connect() as connection:
        assert connection.execute(text('SELECT username FROM users')).scalar_one()=='keep'
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()=='0013_error_diagnostics'
    for table in ['analysis_records','background_jobs']:
        assert any(c['name']=='error_info_json' and c['nullable'] for c in inspect(bind).get_columns(table))
    bind.dispose()
