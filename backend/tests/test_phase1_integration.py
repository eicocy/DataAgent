from sqlalchemy import select
from app.models import Dataset, AnalysisRecord
from app.routers import analysis
from test_analysis_api import analysis_context, make_session, SuccessfulAgent
import pytest


@pytest.mark.parametrize('kind', ['csv', 'xlsx'])
def test_upload_profile_version_analysis_chart_history_flow(kind, analysis_context, monkeypatch):
    from io import BytesIO
    from openpyxl import Workbook
    from app.agent.schemas import ExecutionPlan
    from app.agent.executor import WorkflowExecutor
    from app.services.analysis_agent import AgentOutcome
    from app.models import DatasetVersion
    from test_planner import Adapter, plan
    client, sessions, upload_dir = analysis_context
    source = b'category,amount\nA,10\nA,20\nB,5\n'
    if kind == 'xlsx':
        book = Workbook()
        for row in [('category', 'amount'), ('A', 10), ('A', 20), ('B', 5)]:
            book.active.append(row)
        buffer = BytesIO()
        book.save(buffer)
        book.close()
        source = buffer.getvalue()
    uploaded = client.post('/api/v1/datasets/upload', files={'file': (f'input.{kind}', source, 'application/octet-stream')})
    dataset_id = uploaded.json()['data']['id']
    with sessions() as db:
        dataset = db.get(Dataset, dataset_id)
        version = db.get(DatasetVersion, dataset.current_version_id)
        assert version.profile_json['row_count'] == 3
        assert version.original_available
        assert version.transformations_json
    steps = [{'step_id': 'group', 'tool_name': 'group_by_analysis', 'arguments': {'group_columns': ['category'], 'value_column': 'amount', 'aggregation': 'sum'}}, {'step_id': 'chart', 'tool_name': 'generate_chart', 'source_ref': 'group', 'depends_on': ['group'], 'arguments': {'type': 'bar', 'dimension': 'category', 'metrics': [{'field': 'amount_sum'}], 'title': 'Totals'}}]
    class CoreAgent:
        def analyze(self, question, tools):
            adapter = Adapter([{'template': '{label}：{total}', 'facts': [{'key': 'label', 'step_id': 'group', 'path': ['rows', 0, 'category'], 'format': 'text'}, {'key': 'total', 'step_id': 'group', 'path': ['rows', 0, 'amount_sum']}], 'evidence_refs': ['group']}])
            executor = WorkflowExecutor(tools, adapter.settings, adapter, tools.on_event)
            report = executor.execute(ExecutionPlan.model_validate(plan(steps)), question)
            return AgentOutcome(executor.calls, executor.results['group'], report.answer, report.charts[0], report.status, report=report.model_dump(), plan=executor.final_plan.model_dump())
    monkeypatch.setattr(analysis, 'agent', CoreAgent())
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), 'artifact_dir', str(upload_dir / 'artifacts'))
    response = client.post('/api/v1/analysis/chat', json={'session_id': make_session(sessions, dataset_id), 'dataset_id': dataset_id, 'question': '汇总并绘图', 'request_id': f'core-{kind}'})
    result = response.json()['data']
    assert result['status'] == 'succeeded'
    assert result['answer'] == 'A：30'
    history = client.get(f"/api/v1/history/{result['record_id']}").json()['data']
    assert history['final_answer'] == 'A：30'
    assert history['chart']['series'][0]['data'][0]['value'] == 30
    assert history['report']['tables'][0]['artifact_id']


def test_analysis_pins_uploaded_version_and_rejects_cross_dataset_version(analysis_context, monkeypatch):
    client, sessions, _ = analysis_context
    first = client.post('/api/v1/datasets/upload', files={'file': ('first.csv', b'value\n10\n', 'text/csv')}).json()['data']['id']
    second = client.post('/api/v1/datasets/upload', files={'file': ('second.csv', b'value\n20\n', 'text/csv')}).json()['data']['id']
    monkeypatch.setattr(analysis, 'agent', SuccessfulAgent())
    session_id = make_session(sessions, first)
    payload = {'session_id': session_id, 'dataset_id': first, 'question': '合计', 'request_id': 'pin-version'}
    assert client.post('/api/v1/analysis/chat', json=payload).status_code == 200
    with sessions() as db:
        dataset = db.get(Dataset, first)
        record = db.scalar(select(AnalysisRecord).where(AnalysisRecord.request_id == 'pin-version'))
        assert record.dataset_version_id == dataset.current_version_id
        assert record.version_binding == 'snapshot'
        assert record.schema_version == '1.1'
        dataset.current_version_id = db.get(Dataset, second).current_version_id
        db.commit()
    payload['request_id'] = 'invalid-version'
    response = client.post('/api/v1/analysis/chat', json=payload)
    assert response.status_code == 409


def test_readiness_requires_current_alembic_head(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, text
    from fastapi.testclient import TestClient
    from alembic.script import ScriptDirectory
    import app.main as main
    engine = create_engine(f'sqlite:///{tmp_path / "ready.db"}')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(64))'))
        connection.execute(text("INSERT INTO alembic_version VALUES ('0005_projection_metadata')"))
    monkeypatch.setattr(main, 'engine', engine)
    client = TestClient(main.app)
    assert client.get('/health/ready').status_code == 503
    head = ScriptDirectory(str(__import__('pathlib').Path(__file__).resolve().parents[1] / 'migrations')).get_current_head()
    with engine.begin() as connection:
        connection.execute(text('UPDATE alembic_version SET version_num = :head'), {'head': head})
    assert client.get('/health/ready').status_code == 200
    engine.dispose()


def test_queued_analysis_keeps_submission_version(analysis_context):
    from types import SimpleNamespace
    from app.services.analysis import submit_analysis, execute_record
    from app.models import User
    client, sessions, _ = analysis_context
    dataset_id = client.post('/api/v1/datasets/upload', files={'file': ('queued.csv', b'value\n10\n', 'text/csv')}).json()['data']['id']
    session_id = make_session(sessions, dataset_id)
    with sessions() as db:
        record, _ = submit_analysis(db, db.scalar(select(User.id)), SimpleNamespace(dataset_id=dataset_id, session_id=session_id, question='合计', request_id='queued-pin'))
        version_id = record.dataset_version_id
        db.get(Dataset, dataset_id).current_version_id = None
        db.commit()
        class Agent(SuccessfulAgent):
            def analyze(self, question, tools):
                assert tools.model_metadata['dataset_version_id'] == version_id
                assert int(tools.frame.value.iloc[0]) == 10
                return super().analyze(question, tools)
        outcome = execute_record(db, record.id, Agent(), db.get_bind(), db.get_bind())
        assert outcome.status == 'succeeded'
        assert outcome.dataset_version_id == version_id
