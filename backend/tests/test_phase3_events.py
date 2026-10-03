from datetime import UTC, datetime
from sqlalchemy import select
from test_analysis_api import analysis_context
from test_phase3_api import upload
from app.models import AnalysisEvent, AnalysisRecord, BackgroundJob
from app.services.jobs import terminate_job


def prepare(client):
    dataset_id = upload(client, 'events.csv')
    session_id = client.post('/api/v1/analysis/sessions', json={'dataset_id': dataset_id}).json()['data']['id']
    result = client.post('/api/v1/analysis/runs', json={
        'session_id': session_id, 'dataset_id': dataset_id, 'question': '汇总', 'request_id': 'events-1'})
    return result.json()['data']['record_id']


def test_submission_event_is_replayable_with_last_event_id(analysis_context):
    client, sessions, _ = analysis_context
    record_id = prepare(client)
    with sessions() as db:
        record = db.get(AnalysisRecord, record_id)
        record.status = 'succeeded'
        db.add(AnalysisEvent(record_id=record_id, user_id=record.user_id, event_type='response_ready',
            payload_json={'status': 'succeeded'}, created_at=datetime.now(UTC)))
        db.commit()
    response = client.get(f'/api/v1/analysis/runs/{record_id}/events')
    assert response.status_code == 200
    assert 'event: response_ready' in response.text
    last_id = max(item.id for item in sessions().scalars(select(AnalysisEvent).where(AnalysisEvent.record_id == record_id)))
    replay = client.get(f'/api/v1/analysis/runs/{record_id}/events', headers={'Last-Event-ID': str(last_id)})
    assert 'event: response_ready' not in replay.text


def test_cancel_pending_run_is_terminal_and_idempotent(analysis_context):
    client, sessions, _ = analysis_context
    record_id = prepare(client)
    first = client.post(f'/api/v1/analysis/runs/{record_id}/cancel')
    second = client.post(f'/api/v1/analysis/runs/{record_id}/cancel')
    assert first.status_code == second.status_code == 200
    assert first.json()['data']['status'] == 'cancelled'
    with sessions() as db:
        record = db.get(AnalysisRecord, record_id)
        job = db.scalar(select(BackgroundJob).where(BackgroundJob.resource_id == record_id))
        assert record.status == job.status == 'cancelled'
        assert any(event.event_type == 'analysis_cancelled' for event in db.scalars(
            select(AnalysisEvent).where(AnalysisEvent.record_id == record_id)))


def test_running_cancel_marks_unfinished_steps_and_keeps_completed_artifact(analysis_context):
    client, sessions, _ = analysis_context
    record_id = prepare(client)
    with sessions() as db:
        record = db.get(AnalysisRecord, record_id)
        record.status = 'running'
        record.plan_json = {'version': '2.0', 'status': 'RUNNING', 'steps': [
            {'step_id': 'done', 'status': 'COMPLETED', 'result_ref': 'artifact:4'},
            {'step_id': 'next', 'status': 'PENDING'}]}
        job = db.scalar(select(BackgroundJob).where(BackgroundJob.resource_id == record_id))
        job.status = 'running'
        job.cancel_requested = True
        db.commit()
    terminate_job(sessions, job.id, 'TASK_CANCELLED')
    with sessions() as db:
        record = db.get(AnalysisRecord, record_id)
        assert record.status == 'cancelled'
        assert record.plan_json['steps'][0]['result_ref'] == 'artifact:4'
        assert record.plan_json['steps'][1]['status'] == 'CANCELLED'
        assert db.get(BackgroundJob, job.id).status == 'cancelled'
