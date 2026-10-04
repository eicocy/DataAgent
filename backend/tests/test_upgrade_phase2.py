"""The new workspace Phase 2, separate from historical v1 phase names."""
import pytest
import pandas as pd
from test_analysis_api import analysis_context
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.models import Base


def test_profiles_are_versioned_and_unsupported_templates_stay_blocked():
    from app.profiles.service import ProfileService
    with Session(create_engine('sqlite://')) as db:
        Base.metadata.create_all(db.bind)
        service = ProfileService(db)
        service.seed()
        service.seed()
        assert len(service.catalog()['items']) == 105
        assert service.get('general-quality').availability == 'available'
        with pytest.raises(ValueError, match='PROFILE_UNAVAILABLE'):
            service.selected(['finance-cash-flow'])


def test_semantics_distinguish_metrics_ids_and_versioned_user_corrections():
    from app.semantic.detectors import detect_semantics
    from app.semantic.mappings import SemanticMapping, merge_mappings
    frame = pd.DataFrame({'sales_amount': [10, 20], 'sales': [1, 2], 'customer_id': [1, 2], 'region': ['a', 'b']})
    candidates = detect_semantics(frame, 7)
    assert next(m for m in candidates if m.column == 'sales_amount').concept == 'revenue'
    assert not any(m.role == 'metric' and m.column == 'customer_id' for m in candidates)
    corrected = SemanticMapping(column='sales', concept='quantity', role='metric', dataset_version_id=7, source='user', confidence=1)
    merged = merge_mappings(candidates, [corrected], 7)
    assert next(m for m in merged if m.column == 'sales').concept == 'quantity'
    assert not any(m.source == 'user' for m in merge_mappings(candidates, [corrected], 8))


def test_router_combines_profiles_and_clarifies_unavailable_forecast():
    from app.agent.template_router import AnalysisTemplateRouter
    from app.profiles.catalog import profile_catalog
    router = AnalysisTemplateRouter(profile_catalog()['items'])
    result = router.route('分析销售下降原因，并预测下季度销量')
    assert 'sales-decline' in result.profile_ids
    assert not result.needs_clarification
    assert not result.missing_requirements
    assert len(result.profile_ids) <= 3


def test_model_budget_reserves_before_call_and_missing_usage_is_conservative():
    from app.agent.budget import BudgetProvider, RuntimeBudget, BudgetExceeded
    class Provider:
        usage = {}
        calls = 0
        def generate_text(self, name, payload):
            self.calls += 1
            return 'ok'
    provider = Provider()
    budget = RuntimeBudget.for_depth('FAST')
    wrapped = BudgetProvider(provider, budget)
    for _ in range(6):
        wrapped.generate_text('general_chat', {'question': 'hello'})
    with pytest.raises(BudgetExceeded):
        wrapped.generate_text('general_chat', {})
    assert provider.calls == 6
    assert budget.tokens > 0


def test_task_graph_deduplicates_by_input_version_and_mapping_not_just_tool():
    from app.agent.task_graph import deduplicate_steps
    from app.agent.schemas import AnalysisStep
    steps = [AnalysisStep(step_id=k, tool_name='dataset_overview', input_alias=a) for k, a in [('a', 'one'), ('b', 'one'), ('c', 'two')]]
    unique, aliases = deduplicate_steps(steps, {'one': 7, 'two': 8}, 2)
    assert [s.step_id for s in unique] == ['a', 'c']
    assert aliases == {'b': 'a'}


def test_v3_plan_rejects_cycle_and_cross_input_result_without_join():
    from app.agent.schemas import AnalysisPlanV3, InputBinding, AnalysisStep
    from app.agent.task_graph import validate_graph
    inputs = [InputBinding(alias='one', dataset_id=1, dataset_version_id=7), InputBinding(alias='two', dataset_id=2, dataset_version_id=8)]
    plan = AnalysisPlanV3(task_id='1', goal='quality', intent='DATA_ANALYSIS', dataset_id=1, dataset_version_id=7, inputs=inputs,
        steps=[AnalysisStep(step_id='a', tool_name='dataset_overview', input_alias='one'), AnalysisStep(step_id='b', tool_name='column_summary', input_alias='two', source_ref='a', depends_on=['a'])])
    with pytest.raises(ValueError, match='CROSS_INPUT_SOURCE'):
        validate_graph(plan, {'one': {}, 'two': {}})
    plan.steps[1].input_alias = 'one'
    plan.steps[0].tool_name = 'column_summary'
    plan.steps[0].depends_on = ['b']
    with pytest.raises(ValueError, match='DEPENDENCY_CYCLE'):
        validate_graph(plan, {'one': {}, 'two': {}})


def test_v3_submission_snapshots_all_inputs_and_full_config_idempotency(analysis_context):
    from app.models import AnalysisRecord
    client, sessions, _ = analysis_context
    ids = [client.post('/api/v1/datasets/upload', files={'file': (f'{i}.csv', b'revenue,region\n10,East\n', 'text/csv')}).json()['data']['id'] for i in range(2)]
    sid = client.post('/api/v1/analysis/sessions', json={'dataset_id': ids[0]}).json()['data']['id']
    payload = {'session_id': sid, 'dataset_id': ids[0], 'question': '检查数据质量', 'request_id': 'v3-1',
        'inputs': [{'alias': 'primary', 'dataset_id': ids[0]}, {'alias': 'second', 'dataset_id': ids[1]}], 'depth': 'FAST', 'profile_ids': ['general-quality']}
    response = client.post('/api/v1/analysis/runs', json=payload)
    assert response.status_code == 202, response.text
    assert client.post('/api/v1/analysis/runs', json=payload).json()['data']['record_id'] == response.json()['data']['record_id']
    assert client.post('/api/v1/analysis/runs', json=dict(payload, depth='DEEP')).status_code == 409
    with sessions() as db:
        config = db.get(AnalysisRecord, response.json()['data']['record_id']).request_config_json
        assert all(x['dataset_version_id'] for x in config['inputs'])
        assert config['profiles'][0]['id'] == 'general-quality'


def test_session_semantic_mapping_is_validated_and_restored(analysis_context):
    from app.models import Dataset
    client, sessions, _ = analysis_context
    did = client.post('/api/v1/datasets/upload', files={'file': ('a.csv', b'sales\n10\n', 'text/csv')}).json()['data']['id']
    sid = client.post('/api/v1/analysis/sessions', json={'dataset_id': did}).json()['data']['id']
    with sessions() as db:
        vid = db.get(Dataset, did).current_version_id
    url = f'/api/v1/analysis/sessions/{sid}/semantic-mappings'
    mapping = {'column': 'sales', 'concept': 'quantity', 'role': 'metric', 'dataset_version_id': vid}
    response = client.patch(url, json={'mappings': [mapping]})
    assert response.status_code == 200, response.text
    assert response.json()['data']['mappings'][0]['source'] == 'user'
    assert client.get(url).json()['data']['mappings'][0]['concept'] == 'quantity'
    assert client.patch(url, json={'mappings': [dict(mapping, column='missing')]}).status_code == 422
    assert client.post('/api/v1/analysis/runs', json={'session_id': sid, 'dataset_id': did, 'question': '分析', 'request_id': 'bad-model', 'model_id': 'http://evil/model'}).status_code == 422


def test_v3_planner_binds_trusted_inputs_and_deduplicates_profile_steps():
    from app.agent.planner import Planner
    from app.agent.providers import FakeLLMProvider
    from app.agent.context import ConversationContext
    from app.analysis.models import Permission
    binding = {'alias': 'primary', 'dataset_id': 1, 'dataset_version_id': 7}
    provider = FakeLLMProvider([{'version': '3.0', 'task_id': '1', 'goal': 'quality', 'intent': 'DATA_ANALYSIS', 'dataset_id': 1, 'dataset_version_id': 7,
        'inputs': [binding], 'steps': [{'step_id': 'a', 'tool_name': 'dataset_overview'}, {'step_id': 'b', 'tool_name': 'dataset_overview'}], 'expected_outputs': ['a', 'b']}])
    plan = Planner(provider).plan_v3('检查表', {'primary': {'columns': [{'name': 'x', 'data_type': 'integer'}]}}, ConversationContext(conversation_id=1, user_id=1),
        task_id='1', intent='DATA_ANALYSIS', config={'inputs': [binding], 'profiles': [], 'semantic_snapshot': [], 'semantic_version': 0, 'depth': 'STANDARD'},
        permissions=frozenset({Permission.READ_DATA}))
    assert len(plan.steps) == 1
    assert plan.expected_outputs == ['a']


def test_v3_parallel_execution_copies_frames_and_persists_on_main_thread():
    import threading
    import time
    from dataclasses import replace
    from app.agent.schemas import AnalysisPlanV3, InputBinding, AnalysisStep
    from app.agent.graph_executor import GraphExecutor, InputWorkspace
    from app.agent.budget import RuntimeBudget
    from app.services.analysis_tools import DatasetTools
    from app.analysis.registry import FunctionTool
    from types import SimpleNamespace
    tools = DatasetTools.from_frame(1, [{'x': 10}, {'x': 20}])
    barrier = threading.Barrier(2)
    seen = []
    registry = __import__('app.analysis.catalog', fromlist=['build_registry']).build_registry(True)
    for name in ['dataset_overview', 'column_summary']:
        old = registry.get(name)
        def calculate(context, args, original=old):
            seen.append(threading.get_ident())
            barrier.wait(timeout=3)
            context.frame.iloc[0, 0] = 99
            return original.execute(context, args)
        registry._tools[name] = FunctionTool(replace(old.metadata, parallel_safe=True), old.input_schema, old.output_schema, calculate)
    tools._registry = registry
    events = []
    def emit(kind, payload):
        events.append((kind, threading.get_ident()))
    workspace = InputWorkspace({'primary': tools})
    plan = AnalysisPlanV3(task_id='1', goal='quality', intent='DATA_ANALYSIS', dataset_id=1, dataset_version_id=7,
        inputs=[InputBinding(alias='primary', dataset_id=1, dataset_version_id=7)], steps=[AnalysisStep(step_id='a', tool_name='dataset_overview'), AnalysisStep(step_id='b', tool_name='column_summary')])
    runner = GraphExecutor(workspace, SimpleNamespace(analysis_timeout_seconds=30, max_tool_attempts=10, max_retries_per_step=0), budget=RuntimeBudget.for_depth('STANDARD'), emit=emit)
    report = runner.execute(plan, '检查数据')
    assert len(set(seen)) == 2
    assert tools.frame.iloc[0, 0] == 10
    assert all(t == threading.get_ident() for _, t in events)
    assert len(runner.results) == 2
    assert report.status == 'partial'


@pytest.mark.parametrize('depth', ['FAST', 'STANDARD', 'DEEP'])
@pytest.mark.parametrize('with_summary', [False, True])
def test_fake_provider_v3_runs_compute_and_persist_evidence(analysis_context, depth, with_summary, monkeypatch, tmp_path):
    from app.models import AnalysisRecord, AnalysisArtifact, AnalysisEvent, ToolExecutionRecord, Dataset
    from app.services.analysis import execute_record
    from app.services.analysis_agent import DeepSeekAgent
    from app.agent.providers import FakeLLMProvider
    from app.config import get_settings
    from sqlalchemy import select
    client, sessions, _ = analysis_context
    monkeypatch.setattr(get_settings(), 'artifact_dir', str(tmp_path / 'artifacts'))
    did = client.post('/api/v1/datasets/upload', files={'file': ('a.csv', b'revenue\n10\n20\n', 'text/csv')}).json()['data']['id']
    sid = client.post('/api/v1/analysis/sessions', json={'dataset_id': did}).json()['data']['id']
    rid = client.post('/api/v1/analysis/runs', json={'session_id': sid, 'dataset_id': did, 'question': '检查数据质量', 'request_id': depth,
        'depth': depth, 'profile_ids': ['general-quality']}).json()['data']['record_id']
    with sessions() as db:
        vid = db.get(Dataset, did).current_version_id
        provider = FakeLLMProvider([{'intent': 'DATA_ANALYSIS', 'confidence': .99, 'requires_dataset': True, 'requires_analysis': True},
            {'task_id': str(rid), 'goal': 'quality', 'intent': 'DATA_ANALYSIS', 'dataset_id': did, 'dataset_version_id': vid,
             'inputs': [{'alias': 'primary', 'dataset_id': did, 'dataset_version_id': vid}], 'steps': [{'step_id': 'quality', 'tool_name': 'missing_value_analysis'}]}])
        if with_summary:
            responses = list(provider.responses)
            if depth == 'DEEP':
                responses.append({'steps': []})
            responses.append({'template': '字段缺失数为 {missing}。', 'facts': [{'key': 'missing', 'step_id': 'quality', 'path': ['findings', 0, 'count']}], 'evidence_refs': ['quality']})
            provider.responses = iter(responses)
        execute_record(db, rid, DeepSeekAgent(provider_factory=lambda emit: provider), db.get_bind(), db.get_bind())
        record = db.get(AnalysisRecord, rid)
        assert record.status == ('succeeded' if with_summary else 'partial'), (record.status, record.error_code, record.final_answer)
        if with_summary:
            assert record.final_answer == '字段缺失数为 0。'
        assert record.plan_json['version'] == '3.0'
        assert record.plan_json['steps'][0]['status'] == 'COMPLETED'
        assert db.scalar(select(AnalysisArtifact).where(AnalysisArtifact.record_id == rid))
        assert db.scalar(select(ToolExecutionRecord).where(ToolExecutionRecord.analysis_record_id == rid)).dataset_version_id == vid
        assert db.scalar(select(AnalysisEvent).where(AnalysisEvent.record_id == rid, AnalysisEvent.event_type == 'profile_selected'))


def test_graph_uses_each_inputs_column_types_not_a_merged_schema():
    from app.agent.schemas import AnalysisPlanV3, InputBinding, AnalysisStep
    from app.agent.task_graph import validate_graph
    plan = AnalysisPlanV3(task_id='1', goal='total', intent='DATA_ANALYSIS', dataset_id=1, dataset_version_id=7,
        inputs=[InputBinding(alias='primary', dataset_id=1, dataset_version_id=7), InputBinding(alias='second', dataset_id=2, dataset_version_id=8)],
        steps=[AnalysisStep(step_id='sum', tool_name='aggregate', arguments={'metrics': [{'column': 'x', 'aggregation': 'sum'}]})])
    assert validate_graph(plan, {'primary': {'x': 'integer'}, 'second': {'x': 'string'}}).status == 'READY'
    plan.steps[0].input_alias = 'second'
    with pytest.raises(ValueError, match='COLUMN_TYPE_MISMATCH'):
        validate_graph(plan, {'primary': {'x': 'integer'}, 'second': {'x': 'string'}})


def test_deep_exploration_reuses_evidence_and_adds_valid_tasks():
    from types import SimpleNamespace
    from app.agent.schemas import AnalysisPlanV3, InputBinding, AnalysisStep
    from app.agent.providers import FakeLLMProvider
    from app.agent.graph_executor import GraphExecutor, InputWorkspace
    from app.agent.budget import RuntimeBudget
    from app.services.analysis_tools import DatasetTools
    tools = DatasetTools.from_frame(1, [{'x': 10}, {'x': 20}])
    provider = FakeLLMProvider([{'trigger_step_id': 'inspect', 'reason': '已有概览支持检查缺失值', 'steps': [{'step_id': 'quality', 'tool_name': 'missing_value_analysis'}]}, {'steps': []}])
    plan = AnalysisPlanV3(task_id='1', goal='quality', intent='DATA_ANALYSIS', dataset_id=1, dataset_version_id=7, depth='DEEP',
        inputs=[InputBinding(alias='primary', dataset_id=1, dataset_version_id=7)], steps=[AnalysisStep(step_id='inspect', tool_name='dataset_overview')])
    events = []
    runner = GraphExecutor(InputWorkspace({'primary': tools}), SimpleNamespace(analysis_timeout_seconds=30, max_tool_attempts=10), provider, lambda kind, data: events.append(kind), RuntimeBudget.for_depth('DEEP'))
    runner.execute(plan, '检查数据')
    assert set(runner.results) == {'inspect', 'quality'}
    assert plan.steps[-1].exploration_parent == 'inspect'
    assert 'exploration_created' in events


def test_natural_language_semantic_correction_is_explicit_and_column_scoped():
    from app.semantic.mappings import parse_corrections
    correction = parse_corrections('sales字段不是销售额，是销量。继续分析', ['sales', 'region'], 7)
    assert correction[0].concept == 'quantity'
    assert correction[0].source == 'user'
    assert not parse_corrections('unknown字段是销量', ['sales'], 7)
    assert not parse_corrections('可能销量下降了', ['sales'], 7)


def test_replan_preserves_completed_definitions_and_required_nodes():
    from app.agent.schemas import AnalysisPlanV3, InputBinding, AnalysisStep
    from app.agent.graph_executor import validate_replacement
    old = AnalysisPlanV3(task_id='1', goal='quality', intent='DATA_ANALYSIS', dataset_id=1, dataset_version_id=7,
        inputs=[InputBinding(alias='primary', dataset_id=1, dataset_version_id=7)], steps=[AnalysisStep(step_id='done', tool_name='dataset_overview'), AnalysisStep(step_id='failed', tool_name='column_summary')])
    replacement = old.model_copy(deep=True)
    validate_replacement(old, replacement, {'done'})
    replacement.steps = replacement.steps[:1]
    with pytest.raises(ValueError, match='REQUIRED_STEP_REMOVED'):
        validate_replacement(old, replacement, {'done'})
    replacement = old.model_copy(deep=True)
    replacement.steps[0].arguments = {'limit': 10}
    with pytest.raises(ValueError, match='COMPLETED_STEP_CHANGED'):
        validate_replacement(old, replacement, {'done'})


def test_multiple_inputs_keep_artifact_and_execution_lineage(analysis_context, monkeypatch, tmp_path):
    from app.models import AnalysisRecord, AnalysisArtifact, ToolExecutionRecord
    from app.services.analysis import execute_record
    from app.services.analysis_agent import DeepSeekAgent
    from app.agent.providers import FakeLLMProvider
    from app.config import get_settings
    from sqlalchemy import select
    client, sessions, _ = analysis_context
    monkeypatch.setattr(get_settings(), 'artifact_dir', str(tmp_path / 'artifacts'))
    ids = [client.post('/api/v1/datasets/upload', files={'file': (f'{i}.csv', f'revenue\n{10+i}\n'.encode(), 'text/csv')}).json()['data']['id'] for i in range(2)]
    sid = client.post('/api/v1/analysis/sessions', json={'dataset_id': ids[0]}).json()['data']['id']
    rid = client.post('/api/v1/analysis/runs', json={'session_id': sid, 'dataset_id': ids[0], 'question': '检查表的数据质量', 'request_id': 'lineage', 'depth': 'STANDARD',
        'inputs': [{'alias': 'primary', 'dataset_id': ids[0]}, {'alias': 'second', 'dataset_id': ids[1]}], 'profile_ids': ['general-quality']}).json()['data']['record_id']
    with sessions() as db:
        bindings = db.get(AnalysisRecord, rid).request_config_json['inputs']
        provider = FakeLLMProvider([{'intent': 'DATA_ANALYSIS', 'confidence': .99, 'requires_dataset': True, 'requires_analysis': True},
            {'task_id': str(rid), 'goal': 'quality', 'intent': 'DATA_ANALYSIS', 'dataset_id': ids[0], 'dataset_version_id': bindings[0]['dataset_version_id'], 'inputs': bindings,
             'steps': [{'step_id': 'a', 'tool_name': 'missing_value_analysis'}, {'step_id': 'b', 'input_alias': 'second', 'tool_name': 'missing_value_analysis'}]}])
        execute_record(db, rid, DeepSeekAgent(provider_factory=lambda emit: provider), db.get_bind(), db.get_bind())
        assert db.get(AnalysisRecord, rid).status == 'partial', (db.get(AnalysisRecord, rid).error_code, db.get(AnalysisRecord, rid).plan_json)
        assert set(db.scalars(select(AnalysisArtifact.dataset_id).where(AnalysisArtifact.record_id == rid))) == set(ids)
        assert set(db.execute(select(ToolExecutionRecord.dataset_id, ToolExecutionRecord.dataset_version_id).where(ToolExecutionRecord.analysis_record_id == rid))) == {(b['dataset_id'], b['dataset_version_id']) for b in bindings}


def test_sales_route_requires_a_confirmed_metric_and_time_when_requested():
    from app.agent.template_router import AnalysisTemplateRouter
    from app.profiles.catalog import profile_catalog
    router = AnalysisTemplateRouter(profile_catalog()['items'])
    assert router.route('分析今年销售额', semantics=[]).needs_clarification
    assert router.route('分析今年销售额', semantics=[{'column': 'revenue', 'concept': 'revenue', 'role': 'metric'}]).needs_clarification
    assert not router.route('分析今年销售额', semantics=[{'column': 'revenue', 'concept': 'revenue', 'role': 'metric','source':'user','currency':'USD','unit':'dollar'}, {'column': 'day', 'concept': 'time', 'role': 'dimension'}]).needs_clarification


def test_question_correction_is_saved_at_submission_for_future_runs(analysis_context):
    from app.models import AnalysisRecord, AnalysisSession
    client, sessions, _ = analysis_context
    did = client.post('/api/v1/datasets/upload', files={'file': ('a.csv', b'sales\n10\n', 'text/csv')}).json()['data']['id']
    sid = client.post('/api/v1/analysis/sessions', json={'dataset_id': did}).json()['data']['id']
    submitted = client.post('/api/v1/analysis/runs', json={'session_id': sid, 'dataset_id': did, 'question': 'sales字段不是销售额，是销量。分析数据', 'depth': 'STANDARD', 'request_id': 'correction'})
    assert submitted.status_code == 202
    with sessions() as db:
        record = db.get(AnalysisRecord, submitted.json()['data']['record_id'])
        assert record.request_config_json['semantic_snapshot'][0]['concept'] == 'quantity'
        assert db.get(AnalysisSession, sid).context_json['semantic_mappings'][0]['concept'] == 'quantity'


def test_router_does_not_treat_negated_semantic_meaning_as_requested_metric():
    from app.agent.template_router import AnalysisTemplateRouter
    from app.profiles.catalog import profile_catalog
    route = AnalysisTemplateRouter(profile_catalog()['items']).route('sales字段不是销售额，是销量。分析销量', semantics=[{'concept': 'quantity', 'role': 'metric', 'column': 'sales', 'source': 'user'}])
    assert not route.needs_clarification


def test_v3_planning_inherits_same_version_followup_context():
    from app.agent.planner import Planner
    from app.agent.providers import FakeLLMProvider
    from app.agent.context import ConversationContext
    from app.analysis.models import Permission
    class Capture(FakeLLMProvider):
        def generate_structured(self, name, payload, schema):
            self.payload = payload
            return super().generate_structured(name, payload, schema)
    binding = {'alias': 'primary', 'dataset_id': 1, 'dataset_version_id': 7}
    provider = Capture([{'task_id': '1', 'goal': 'quality', 'intent': 'FOLLOW_UP_ANALYSIS', 'dataset_id': 1, 'dataset_version_id': 7, 'inputs': [binding], 'steps': [{'step_id': 'a', 'tool_name': 'dataset_overview'}]}])
    context = ConversationContext(conversation_id=1, user_id=1, active_filters=[{'column': 'region', 'value': 'south'}], active_metrics=['sales'], previous_plan={'goal': 'sales'})
    Planner(provider).plan_v3('只看华南', {'primary': {'columns': []}}, context, task_id='1', intent='FOLLOW_UP_ANALYSIS',
        config={'inputs': [binding], 'profiles': [], 'semantic_snapshot': [], 'semantic_version': 0, 'depth': 'STANDARD'}, permissions=frozenset({Permission.READ_DATA}))
    assert provider.payload['filters'] == context.active_filters
    assert provider.payload['previous_plan'] == context.previous_plan


def test_graph_rejects_non_table_sources_and_unknown_result_fields():
    from app.agent.schemas import AnalysisPlanV3, InputBinding, AnalysisStep
    from app.agent.task_graph import validate_graph
    plan = AnalysisPlanV3(task_id='1', goal='quality', intent='DATA_ANALYSIS', dataset_id=1, dataset_version_id=7,
        inputs=[InputBinding(alias='primary', dataset_id=1, dataset_version_id=7)],
        steps=[AnalysisStep(step_id='inspect', tool_name='dataset_overview'), AnalysisStep(step_id='child', tool_name='column_summary', source_ref='inspect', depends_on=['inspect'])])
    with pytest.raises(ValueError, match='SOURCE_RESULT_TYPE'):
        validate_graph(plan, {'primary': {'x': 'integer'}})
    plan.steps[1] = AnalysisStep(step_id='child', tool_name='filter_data', depends_on=['inspect'], arguments={'conditions': [{'column': 'x', 'operator': 'in', 'value': {'$ref': 'inspect', 'field': 'imaginary'}}]})
    with pytest.raises(ValueError, match='RESULT_FIELD_UNKNOWN'):
        validate_graph(plan, {'primary': {'x': 'integer'}})


def test_semantic_patch_refreshes_stale_context_and_preserves_other_changes(analysis_context):
    from app.models import AnalysisSession, Dataset, User
    from app.routers.sessions import update_semantics, SemanticPatch
    client, sessions, _ = analysis_context
    did = client.post('/api/v1/datasets/upload', files={'file': ('a.csv', b'sales,cost\n10,5\n', 'text/csv')}).json()['data']['id']
    sid = client.post('/api/v1/analysis/sessions', json={'dataset_id': did}).json()['data']['id']
    with sessions() as stale_db:
        stale = stale_db.get(AnalysisSession, sid)
        user = stale_db.get(User, stale.user_id)
        vid = stale_db.get(Dataset, did).current_version_id
        first = {'column': 'sales', 'concept': 'quantity', 'role': 'metric', 'dataset_version_id': vid}
        assert client.patch(f'/api/v1/analysis/sessions/{sid}/semantic-mappings', json={'mappings': [first]}).status_code == 200
        update_semantics(sid, SemanticPatch(mappings=[dict(first, column='cost', concept='cost')]), user, stale_db)
        assert {m['column'] for m in stale.context_json['semantic_mappings']} == {'sales', 'cost'}
        assert stale.context_json['semantic_version'] == 2


def test_parallel_result_failure_is_not_replanned_but_independent_result_survives():
    from app.agent.graph_executor import GraphExecutor, InputWorkspace
    from app.agent.schemas import AnalysisPlanV3, AnalysisStep, InputBinding
    from app.agent.budget import RuntimeBudget
    from app.services.analysis_tools import DatasetTools
    from app.analysis.registry import FunctionTool
    from app.analysis.errors import ToolResultError
    from types import SimpleNamespace
    tools = DatasetTools.from_frame(1, [{'x': 1}, {'x': 2}])
    registry = __import__('app.analysis.catalog', fromlist=['build_registry']).build_registry(True)
    original = registry.get('dataset_overview')
    def invalid_result(context, arguments):
        raise ToolResultError('RESULT_NON_FINITE')
    registry._tools['dataset_overview'] = FunctionTool(original.metadata, original.input_schema, original.output_schema, invalid_result)
    tools._registry = registry
    workspace = InputWorkspace({'primary': tools})
    plan = AnalysisPlanV3(task_id='1', goal='quality', intent='DATA_ANALYSIS', dataset_id=1, dataset_version_id=7,
        inputs=[InputBinding(alias='primary', dataset_id=1, dataset_version_id=7)],
        steps=[AnalysisStep(step_id='invalid', tool_name='dataset_overview'), AnalysisStep(step_id='valid', tool_name='column_summary')])
    runner = GraphExecutor(workspace, SimpleNamespace(analysis_timeout_seconds=30, max_tool_attempts=10, max_retries_per_step=0), budget=RuntimeBudget.for_depth('STANDARD'))
    report = runner.execute(plan, '检查数据')
    assert 'valid' in runner.results
    assert 'invalid' in runner.unrecoverable_steps
    assert report.status == 'partial'


def test_dedup_never_reuses_filtered_source_for_a_dataset_root():
    from app.agent.task_graph import deduplicate_steps
    from app.agent.schemas import AnalysisStep
    args = {'metrics': [{'column': 'sales', 'aggregation': 'sum'}]}
    steps = [AnalysisStep(step_id='filtered_total', tool_name='aggregate', arguments=args, source_ref='filter', depends_on=['filter']),
        AnalysisStep(step_id='full_total', tool_name='aggregate', arguments=args)]
    unique, aliases = deduplicate_steps(steps, {'primary': 7}, 1)
    assert [step.step_id for step in unique] == ['filtered_total', 'full_total']
    assert aliases == {}


def test_dedup_preserves_required_completion_for_optional_first_duplicate():
    from app.agent.task_graph import deduplicate_steps
    from app.agent.schemas import AnalysisStep
    unique, aliases = deduplicate_steps([AnalysisStep(step_id='optional', tool_name='dataset_overview', required=False),
        AnalysisStep(step_id='required', tool_name='dataset_overview', required=True)], {'primary': 7}, 1)
    assert len(unique) == 1 and unique[0].required
    assert aliases == {'required': 'optional'}


def test_replanning_preserves_trusted_exploration_and_rejects_forged_provenance():
    from app.agent.planner import Planner
    from app.agent.schemas import AnalysisPlanV3, AnalysisStep, InputBinding
    from app.agent.providers import FakeLLMProvider
    from app.agent.context import ConversationContext
    from app.analysis.models import Permission
    binding = InputBinding(alias='primary', dataset_id=1, dataset_version_id=7)
    old = AnalysisPlanV3(task_id='1', goal='quality', intent='DATA_ANALYSIS', dataset_id=1, dataset_version_id=7, inputs=[binding], depth='DEEP',
        steps=[AnalysisStep(step_id='root', tool_name='dataset_overview', status='COMPLETED'),
            AnalysisStep(step_id='explored', tool_name='column_summary', status='COMPLETED', exploration_parent='root', exploration_depth=1)])
    raw = old.model_dump()
    for step in raw['steps']:
        step['status'] = 'PENDING'
    config = {'inputs': [binding.model_dump()], 'profiles': [], 'semantic_snapshot': [], 'semantic_version': 0, 'depth': 'DEEP'}
    def plan(payload, trusted):
        return Planner(FakeLLMProvider([payload, payload])).plan_v3('检查表', {'primary': {'columns': []}}, ConversationContext(conversation_id=1, user_id=1),
            task_id='1', intent='DATA_ANALYSIS', config=config, permissions=frozenset({Permission.READ_DATA}), prior_plan=trusted)
    assert plan(raw, old).steps[1].exploration_parent == 'root'
    with pytest.raises(ValueError, match='PLAN_INVALID'):
        plan(raw, None)
    forged = dict(raw, steps=[*raw['steps'], dict(raw['steps'][1], step_id='forged')])
    with pytest.raises(ValueError, match='PLAN_INVALID'):
        plan(forged, old)


def test_replacement_expected_outputs_are_required_for_completion(monkeypatch):
    from app.agent.graph_executor import GraphExecutor, InputWorkspace
    from app.agent.schemas import AnalysisPlanV3, AnalysisStep, InputBinding
    from app.agent.budget import RuntimeBudget
    from app.agent.planner import Planner
    from app.agent.providers import FakeLLMProvider
    from app.services.analysis_tools import DatasetTools
    from types import SimpleNamespace
    tools = DatasetTools.from_frame(1, [{'x': 1}, {'x': 2}])
    workspace = InputWorkspace({'primary': tools})
    workspace.configuration = {'configured': True}
    workspace.metadata_by_input = {'primary': {'columns': [{'name': 'x', 'data_type': 'integer'}]}}
    initial = AnalysisPlanV3(task_id='1', goal='quality', intent='DATA_ANALYSIS', dataset_id=1, dataset_version_id=7,
        inputs=[InputBinding(alias='primary', dataset_id=1, dataset_version_id=7)],
        steps=[AnalysisStep(step_id='root', tool_name='dataset_overview'), AnalysisStep(step_id='repair', tool_name='column_summary', arguments={'columns': ['missing']})])
    replacement = initial.model_copy(deep=True)
    replacement.steps[1].arguments = {'columns': ['x']}
    replacement.steps.append(AnalysisStep(step_id='new_output', tool_name='descriptive_statistics', arguments={'columns': ['missing']}, required=False))
    replacement.expected_outputs = ['new_output']
    monkeypatch.setattr(Planner, 'plan_v3', lambda *args, **kwargs: replacement)
    provider = FakeLLMProvider([{'template': '记录数为 {rows}。', 'facts': [{'key': 'rows', 'step_id': 'root', 'path': ['row_count']}], 'evidence_refs': ['root']}])
    runner = GraphExecutor(workspace, SimpleNamespace(analysis_timeout_seconds=30, max_tool_attempts=10, max_retries_per_step=0, max_replans=1), provider, budget=RuntimeBudget.for_depth('STANDARD'))
    report = runner.execute(initial, '检查数据')
    assert runner.replanned and 'repair' in runner.results
    assert report.status == 'partial'
    assert 'new_output' in report.incomplete_steps


def test_quality_plan_for_cleaning_intent_allows_readonly_inspection_and_never_offers_writes():
    from app.agent.planner import Planner
    from app.agent.providers import FakeLLMProvider
    from app.agent.context import ConversationContext
    from app.analysis.models import Permission
    class Capture(FakeLLMProvider):
        def generate_structured(self, name, payload, schema):
            self.payload = payload
            return super().generate_structured(name, payload, schema)
    binding = {'alias': 'primary', 'dataset_id': 1, 'dataset_version_id': 7}
    raw = {'task_id': '1', 'goal': 'quality', 'intent': 'DATA_CLEANING', 'dataset_id': 1, 'dataset_version_id': 7, 'inputs': [binding],
        'steps': [{'step_id': 'overview', 'tool_name': 'dataset_overview'}, {'step_id': 'summary', 'tool_name': 'column_summary'},
            {'step_id': 'missing', 'tool_name': 'missing_value_analysis'}, {'step_id': 'duplicate', 'tool_name': 'duplicate_analysis'}]}
    provider = Capture([raw, raw])
    plan = Planner(provider).plan_v3('检查缺失和重复', {'primary': {'columns': []}}, ConversationContext(conversation_id=1, user_id=1),
        task_id='1', intent='DATA_CLEANING', config={'inputs': [binding], 'profiles': [], 'semantic_snapshot': [], 'semantic_version': 0, 'depth': 'FAST'}, permissions=frozenset({Permission.READ_DATA}))
    assert len(plan.steps) == 4
    offered = {tool['name'] for tool in provider.payload['tools']}
    assert {'dataset_overview', 'column_summary', 'missing_value_analysis'} <= offered
    assert not offered & {'aggregate', 'generate_chart', 'cleaning_fill_missing', 'cleaning_drop_duplicates'}
