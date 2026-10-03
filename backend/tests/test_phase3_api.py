from sqlalchemy import select
from test_analysis_api import analysis_context
from app.models import AnalysisRecord, AnalysisSession, BackgroundJob, LLMCallRecord, AnalysisArtifact, AnalysisEvent
from datetime import UTC, datetime, timedelta
from app.services.analysis import execute_record
from app.services.analysis_agent import DeepSeekAgent
from app.agent.providers import FakeLLMProvider
from fastapi.testclient import TestClient
from app.main import app


def upload(client, name):
    response = client.post('/api/v1/datasets/upload', files={'file': (name, b'region,sales\nEast,10\n', 'text/csv')})
    return response.json()['data']['id']


def test_session_and_general_chat_run_can_start_without_dataset(analysis_context):
    client, sessions, _ = analysis_context
    created = client.post('/api/v1/analysis/sessions', json={})
    assert created.status_code == 201
    session_id = created.json()['data']['id']
    assert client.get('/api/v1/analysis/sessions').json()['data']['items'][0]['dataset_id'] is None
    assert client.get(f'/api/v1/analysis/sessions/{session_id}').json()['data']['dataset'] is None
    submitted = client.post('/api/v1/analysis/runs', json={
        'session_id': session_id, 'question': '你好', 'request_id': 'general-1'})
    assert submitted.status_code == 202
    with sessions() as db:
        record = db.get(AnalysisRecord, submitted.json()['data']['record_id'])
        assert record.dataset_id is None and record.dataset_version_id is None


def test_same_session_can_switch_dataset_without_rewriting_old_run(analysis_context):
    client, sessions, _ = analysis_context
    first_id, second_id = upload(client, 'first.csv'), upload(client, 'second.csv')
    session_id = client.post('/api/v1/analysis/sessions', json={'dataset_id': first_id}).json()['data']['id']
    first = client.post('/api/v1/analysis/runs', json={
        'session_id': session_id, 'dataset_id': first_id, 'question': '汇总', 'request_id': 'switch-a'})
    assert first.status_code == 202
    with sessions() as db:
        record = db.get(AnalysisRecord, first.json()['data']['record_id'])
        record.status = 'succeeded'
        job = db.scalar(select(BackgroundJob).where(BackgroundJob.resource_id == record.id))
        job.status = 'succeeded'
        db.commit()
    second = client.post('/api/v1/analysis/runs', json={
        'session_id': session_id, 'dataset_id': second_id, 'question': '用第二个文件', 'request_id': 'switch-b'})
    assert second.status_code == 202
    with sessions() as db:
        assert db.get(AnalysisSession, session_id).dataset_id == second_id
        assert db.get(AnalysisRecord, first.json()['data']['record_id']).dataset_id == first_id
        assert db.get(AnalysisRecord, second.json()['data']['record_id']).dataset_id == second_id


def test_dataset_free_general_chat_finishes_without_analysis_plan(analysis_context):
    client, sessions, _ = analysis_context
    session_id = client.post('/api/v1/analysis/sessions', json={}).json()['data']['id']
    record_id = client.post('/api/v1/analysis/runs', json={
        'session_id': session_id, 'question': '你好', 'request_id': 'general-execute'}).json()['data']['record_id']
    provider = FakeLLMProvider([
        {'intent': 'GENERAL_CHAT', 'confidence': 0.99, 'requires_dataset': False,
         'requires_analysis': False, 'dataset_reference': None, 'follow_up': False},
        '你好，请选择数据集后告诉我想分析什么。',
    ])
    agent = DeepSeekAgent(provider_factory=lambda emit: provider)
    with sessions() as db:
        execute_record(db, record_id, agent, db.bind, db.bind)
    with sessions() as db:
        record = db.get(AnalysisRecord, record_id)
        assert record.status == 'succeeded', (record.error_code, record.error_message)
        assert record.plan_json is None
        assert record.dataset_id is None
        assert '选择数据集' in record.final_answer


def test_v2_analysis_binds_fact_to_pinned_version(analysis_context):
    client, sessions, _ = analysis_context
    dataset_id = upload(client, 'sales.csv')
    session_id = client.post('/api/v1/analysis/sessions', json={'dataset_id': dataset_id}).json()['data']['id']
    record_id = client.post('/api/v1/analysis/runs', json={
        'session_id': session_id, 'question': '销售额是多少', 'request_id': 'v2-run'}).json()['data']['record_id']
    with sessions() as db:
        version_id = db.get(AnalysisRecord, record_id).dataset_version_id
    provider = FakeLLMProvider([
        {'intent': 'DATA_AGGREGATION', 'confidence': 0.99, 'requires_dataset': True,
         'requires_analysis': True, 'dataset_reference': None, 'follow_up': False},
        {'task_id': str(record_id), 'goal': '销售额', 'intent': 'DATA_AGGREGATION',
         'dataset_id': dataset_id, 'dataset_version_id': version_id,
         'steps': [{'step_id': 'total', 'tool_name': 'aggregate_data',
                    'arguments': {'metrics': [{'column': 'sales', 'aggregation': 'sum'}]}}],
         'expected_outputs': ['total']},
        {'template': '销售额为 {sales}。', 'facts': [{'key': 'sales', 'step_id': 'total',
          'path': ['metric_values', 'sales_sum']}], 'evidence_refs': ['total']},
    ])
    agent = DeepSeekAgent(provider_factory=lambda emit: provider)
    with sessions() as db:
        execute_record(db, record_id, agent, db.bind, db.bind)
    with sessions() as db:
        record = db.get(AnalysisRecord, record_id)
        assert record.status == 'succeeded', record.error_code
        assert record.plan_json['version'] == '2.0'
        assert record.plan_json['steps'][0]['status'] == 'COMPLETED'
        assert record.plan_json['steps'][0]['result_ref'].startswith('artifact:')
        assert record.final_answer == '销售额为 10。'
        event_types = [item.event_type for item in db.scalars(select(AnalysisEvent).where(
            AnalysisEvent.record_id == record_id).order_by(AnalysisEvent.id))]
        assert event_types.index('plan_created') < event_types.index('plan_validated')
    response = client.get(f'/api/v1/analysis/runs/{record_id}').json()['data']
    assert response['agent_response']['task_id'] == str(record_id)
    assert response['agent_response']['conversation_id'] == str(session_id)
    assert response['evidence'][0]['fact_path'] == ['metric_values', 'sales_sum']
    assert response['evidence'][0]['result_ref'].startswith('artifact:')


def test_chart_follow_up_reuses_completed_compute_artifact(analysis_context):
    client, sessions, _ = analysis_context
    dataset_id = client.post('/api/v1/datasets/upload', files={
        'file': ('regions.csv', b'region,sales\nEast,10\nWest,20\n', 'text/csv')}).json()['data']['id']
    session_id = client.post('/api/v1/analysis/sessions', json={'dataset_id': dataset_id}).json()['data']['id']
    with sessions() as db:
        from app.models import Dataset
        version_id = db.get(Dataset, dataset_id).current_version_id

    def run(question, request_id, intent, chart_type, follow_up):
        record_id = client.post('/api/v1/analysis/runs', json={
            'session_id': session_id, 'question': question, 'request_id': request_id}).json()['data']['record_id']
        steps = [
            {'step_id': 'group', 'tool_name': 'group_by_analysis',
             'arguments': {'group_columns': ['region'], 'value_column': 'sales', 'aggregation': 'sum'}},
            {'step_id': 'chart', 'tool_name': 'generate_chart', 'depends_on': ['group'],
             'source_ref': 'group', 'arguments': {'type': chart_type, 'dimension': 'region',
             'metrics': [{'field': 'sales_sum'}], 'title': '地区销售额'}},
        ]
        if not follow_up:
            # 同一 source_ref 写在参数里或步骤上，含义一致，应复用同一工件。
            steps[0]['arguments']['source_ref'] = 'dataset'
        provider = FakeLLMProvider([
            {'intent': intent, 'confidence': 0.99, 'requires_dataset': True,
             'requires_analysis': True, 'dataset_reference': None, 'follow_up': follow_up},
            {'task_id': str(record_id), 'goal': '地区销售额', 'intent': intent,
             'dataset_id': dataset_id, 'dataset_version_id': version_id,
             'steps': steps, 'expected_outputs': ['group', 'chart']},
            {'template': '首个地区销售额为 {sales}。', 'facts': [{'key': 'sales', 'step_id': 'group',
              'path': ['rows', 0, 'sales_sum']}], 'evidence_refs': ['group']},
        ])
        with sessions() as db:
            execute_record(db, record_id, DeepSeekAgent(provider_factory=lambda emit: provider), db.bind, db.bind)
        return client.get(f'/api/v1/analysis/runs/{record_id}').json()['data']

    first = run('按地区画饼图', 'chart-first', 'CHART_GENERATION', 'pie', False)
    assert first['status'] == 'succeeded', [(c['step_id'], c['status'], c.get('error_code')) for c in first['tool_calls']]
    second = run('换成柱状图', 'chart-second', 'CHART_GENERATION', 'bar', True)
    assert second['status'] == 'succeeded', [(c['step_id'], c['status'], c.get('error_code')) for c in second['tool_calls']]
    assert next(call for call in second['tool_calls'] if call['step_id'] == 'group')['reused'] is True
    assert not next(call for call in second['tool_calls'] if call['step_id'] == 'chart').get('reused', False)
    assert second['chart']['type'] == 'bar'
    assert second['evidence'][0]['dataset_version_id'] == version_id
    assert second['evidence'][0]['artifact_id'] == first['evidence'][0]['artifact_id']
    with sessions() as db:
        artifact = db.get(AnalysisArtifact, first['evidence'][0]['artifact_id'])
        artifact.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        db.commit()
    third = run('再换成饼图', 'chart-third', 'CHART_GENERATION', 'pie', True)
    assert third['status'] == 'succeeded'
    assert not next(call for call in third['tool_calls'] if call['step_id'] == 'group').get('reused', False)
    assert third['evidence'][0]['artifact_id'] != first['evidence'][0]['artifact_id']


def test_new_run_trace_events_and_cancel_are_owner_scoped(analysis_context):
    client, _, _ = analysis_context
    session_id = client.post('/api/v1/analysis/sessions', json={}).json()['data']['id']
    record_id = client.post('/api/v1/analysis/runs', json={
        'session_id': session_id, 'question': '你好', 'request_id': 'owner-scope'}).json()['data']['record_id']
    bob = TestClient(app, headers={'Origin': 'http://localhost:5173'})
    assert bob.post('/api/v1/auth/register', json={'username': 'bob_user', 'password': 'safe-password-123'}).status_code == 201
    for path in (f'/api/v1/analysis/runs/{record_id}',
                 f'/api/v1/analysis/runs/{record_id}/trace',
                 f'/api/v1/analysis/runs/{record_id}/events'):
        assert bob.get(path).status_code == 404
    assert bob.post(f'/api/v1/analysis/runs/{record_id}/cancel').status_code == 404
    assert bob.post('/api/v1/analysis/runs', json={
        'session_id': session_id, 'question': '你好', 'request_id': 'bob-foreign'}).status_code == 404


def test_model_call_log_keeps_metadata_without_raw_question(analysis_context):
    client, sessions, _ = analysis_context
    session_id = client.post('/api/v1/analysis/sessions', json={}).json()['data']['id']
    record_id = client.post('/api/v1/analysis/runs', json={
        'session_id': session_id, 'question': '私密问题', 'request_id': 'model-audit'}).json()['data']['record_id']
    responses = [{'intent': 'GENERAL_CHAT', 'confidence': 0.99, 'requires_dataset': False,
                  'requires_analysis': False, 'follow_up': False}, '你好']
    agent = DeepSeekAgent(provider_factory=lambda emit: FakeLLMProvider(responses, emit))
    with sessions() as db:
        execute_record(db, record_id, agent, db.bind, db.bind)
    with sessions() as db:
        calls = db.scalars(select(LLMCallRecord).where(LLMCallRecord.record_id == record_id)).all()
        assert [item.prompt_version for item in calls] == ['intent_router.v2', 'general_chat.v1']
        assert all(item.request_id == 'model-audit' and item.conversation_id == session_id for item in calls)
        assert all(item.provider == 'fake' and item.status == 'succeeded' for item in calls)
        assert '私密问题' not in str([item.__dict__ for item in calls])


def test_ambiguous_dataset_returns_clarification_without_plan(analysis_context):
    client, sessions, _ = analysis_context
    first_id, second_id = upload(client, 'first.csv'), upload(client, 'second.csv')
    session_id = client.post('/api/v1/analysis/sessions', json={}).json()['data']['id']
    record_id = client.post('/api/v1/analysis/runs', json={
        'session_id': session_id, 'question': '汇总销售额', 'request_id': 'ambiguous'}).json()['data']['record_id']
    provider = FakeLLMProvider([{'intent': 'DATA_AGGREGATION', 'confidence': 0.99,
        'requires_dataset': True, 'requires_analysis': True, 'follow_up': False}])
    with sessions() as db:
        execute_record(db, record_id, DeepSeekAgent(provider_factory=lambda emit: provider), db.bind, db.bind)
    response = client.get(f'/api/v1/analysis/runs/{record_id}').json()['data']
    assert response['status'] == 'waiting' and response['agent_response']['plan_summary'] is None
    assert response['agent_response']['clarification']['candidate_dataset_ids'] == [first_id, second_id]


def test_natural_ordinal_reference_switches_pinned_dataset(analysis_context):
    client, sessions, _ = analysis_context
    first_id, second_id = upload(client, 'first.csv'), upload(client, 'second.csv')
    session_id = client.post('/api/v1/analysis/sessions', json={'dataset_id': first_id}).json()['data']['id']
    record_id = client.post('/api/v1/analysis/runs', json={
        'session_id': session_id, 'question': '用第二个文件汇总销售额', 'request_id': 'ordinal'}).json()['data']['record_id']
    with sessions() as db:
        from app.models import Dataset
        version_id = db.get(Dataset, second_id).current_version_id
    provider = FakeLLMProvider([
        {'intent': 'DATA_AGGREGATION', 'confidence': 0.99, 'requires_dataset': True,
         'requires_analysis': True, 'dataset_reference': {'ordinal': 2}, 'follow_up': False},
        {'task_id': str(record_id), 'goal': '第二个文件销售额', 'intent': 'DATA_AGGREGATION',
         'dataset_id': second_id, 'dataset_version_id': version_id,
         'steps': [{'step_id': 'total', 'tool_name': 'aggregate_data',
                    'arguments': {'metrics': [{'column': 'sales', 'aggregation': 'sum'}]}}],
         'expected_outputs': ['total']},
        {'template': '销售额为 {sales}。', 'facts': [{'key': 'sales', 'step_id': 'total',
          'path': ['metric_values', 'sales_sum']}], 'evidence_refs': ['total']},
    ])
    with sessions() as db:
        execute_record(db, record_id, DeepSeekAgent(provider_factory=lambda emit: provider), db.bind, db.bind)
    with sessions() as db:
        record = db.get(AnalysisRecord, record_id)
        session = db.get(AnalysisSession, session_id)
        assert record.status == 'succeeded'
        assert record.dataset_id == session.dataset_id == second_id
        assert record.dataset_version_id == version_id


def test_filter_follow_up_inherits_metric_and_recomputes_only_affected_path(analysis_context):
    client, sessions, _ = analysis_context
    dataset_id = client.post('/api/v1/datasets/upload', files={
        'file': ('sales.csv', 'region,sales\n华南,10\n华东,20\n'.encode(), 'text/csv')}).json()['data']['id']
    session_id = client.post('/api/v1/analysis/sessions', json={'dataset_id': dataset_id}).json()['data']['id']
    with sessions() as db:
        from app.models import Dataset
        version_id = db.get(Dataset, dataset_id).current_version_id
    def submit(question, request_id):
        return client.post('/api/v1/analysis/runs', json={
            'session_id': session_id, 'question': question, 'request_id': request_id}).json()['data']['record_id']
    first_id = submit('销售额总计', 'filter-first')
    first_provider = FakeLLMProvider([
        {'intent': 'DATA_AGGREGATION', 'confidence': 1, 'requires_dataset': True,
         'requires_analysis': True, 'follow_up': False},
        {'task_id': str(first_id), 'goal': '销售额总计', 'intent': 'DATA_AGGREGATION',
         'dataset_id': dataset_id, 'dataset_version_id': version_id,
         'steps': [{'step_id': 'total', 'tool_name': 'aggregate_data',
                    'arguments': {'metrics': [{'column': 'sales', 'aggregation': 'sum'}]}}],
         'expected_outputs': ['total']},
        {'template': '总销售额为 {sales}。', 'facts': [{'key': 'sales', 'step_id': 'total',
          'path': ['metric_values', 'sales_sum']}], 'evidence_refs': ['total']},
    ])
    with sessions() as db:
        execute_record(db, first_id, DeepSeekAgent(provider_factory=lambda emit: first_provider), db.bind, db.bind)
    assert client.get(f'/api/v1/analysis/runs/{first_id}').json()['data']['answer'] == '总销售额为 30。'
    second_id = submit('只看华南', 'filter-second')
    class CapturingProvider(FakeLLMProvider):
        planner_payload = None
        def generate_structured(self, prompt_name, payload, schema):
            if prompt_name == 'analysis_planner':
                self.planner_payload = payload
            return super().generate_structured(prompt_name, payload, schema)
    second_provider = CapturingProvider([
        {'intent': 'DATA_FILTER', 'confidence': 1, 'requires_dataset': True,
         'requires_analysis': True, 'follow_up': True},
        {'task_id': str(second_id), 'goal': '华南销售额', 'intent': 'DATA_FILTER',
         'dataset_id': dataset_id, 'dataset_version_id': version_id,
         'steps': [
             {'step_id': 'filtered', 'tool_name': 'filter_data',
              'arguments': {'conditions': [{'column': 'region', 'operator': 'eq', 'value': '华南'}]}},
             {'step_id': 'total', 'tool_name': 'aggregate_data', 'depends_on': ['filtered'],
              'source_ref': 'filtered',
              'arguments': {'metrics': [{'column': 'sales', 'aggregation': 'sum'}]}}],
         'expected_outputs': ['total']},
        {'template': '华南销售额为 {sales}。', 'facts': [{'key': 'sales', 'step_id': 'total',
          'path': ['metric_values', 'sales_sum']}], 'evidence_refs': ['total']},
    ])
    with sessions() as db:
        execute_record(db, second_id, DeepSeekAgent(provider_factory=lambda emit: second_provider), db.bind, db.bind)
    second = client.get(f'/api/v1/analysis/runs/{second_id}').json()['data']
    assert second['answer'] == '华南销售额为 10。'
    assert second_provider.planner_payload['metrics'] == ['sales']
    assert second['dataset_version_id'] == version_id
    assert [call['step_id'] for call in second['tool_calls']] == ['filtered', 'total']


def test_unavailable_pinned_version_requests_user_action(analysis_context):
    client, sessions, _ = analysis_context
    dataset_id = upload(client, 'versioned.csv')
    session_id = client.post('/api/v1/analysis/sessions', json={'dataset_id': dataset_id}).json()['data']['id']
    record_id = client.post('/api/v1/analysis/runs', json={
        'session_id': session_id, 'question': '汇总销售额', 'request_id': 'lost-version'}).json()['data']['record_id']
    with sessions() as db:
        from app.models import DatasetVersion
        record = db.get(AnalysisRecord, record_id)
        db.get(DatasetVersion, record.dataset_version_id).status = 'failed'
        db.commit()
    provider = FakeLLMProvider([{'intent': 'DATA_AGGREGATION', 'confidence': 1,
        'requires_dataset': True, 'requires_analysis': True, 'follow_up': False}])
    with sessions() as db:
        execute_record(db, record_id, DeepSeekAgent(provider_factory=lambda emit: provider), db.bind, db.bind)
    response = client.get(f'/api/v1/analysis/runs/{record_id}').json()['data']
    assert response['status'] == 'waiting'
    assert response['error_code'] == 'DATASET_VERSION_UNAVAILABLE'
    assert '恢复该版本' in response['answer']


def test_version_already_unavailable_at_submission_still_returns_durable_clarification(analysis_context):
    client, sessions, _ = analysis_context
    dataset_id = upload(client, 'unavailable.csv')
    session_id = client.post('/api/v1/analysis/sessions', json={'dataset_id': dataset_id}).json()['data']['id']
    with sessions() as db:
        from app.models import Dataset, DatasetVersion
        version_id = db.get(Dataset, dataset_id).current_version_id
        db.get(DatasetVersion, version_id).status = 'failed'
        db.commit()
    submitted = client.post('/api/v1/analysis/runs', json={
        'session_id': session_id, 'question': '换成柱状图', 'request_id': 'already-unavailable'})
    assert submitted.status_code == 202
    record_id = submitted.json()['data']['record_id']
    provider = FakeLLMProvider([{'intent': 'CHART_GENERATION', 'confidence': 1,
        'requires_dataset': True, 'requires_analysis': True, 'follow_up': True}])
    with sessions() as db:
        execute_record(db, record_id, DeepSeekAgent(provider_factory=lambda emit: provider), db.bind, db.bind)
    result = client.get(f'/api/v1/analysis/runs/{record_id}').json()['data']
    assert result['status'] == 'waiting'
    assert result['dataset_version_id'] == version_id
    assert result['error_code'] == 'DATASET_VERSION_UNAVAILABLE'
    assert result['tool_calls'] == []
    assert result['agent_response']['clarification'] is not None
