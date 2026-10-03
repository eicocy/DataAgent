from fastapi.testclient import TestClient
from datetime import UTC, datetime
from sqlalchemy import select

from test_analysis_api import analysis_context
from app.main import app
from app.models import AnalysisSession, Dataset, User
from app.agent.context import ConversationContext


def test_capabilities_enable_phase2_and_keep_future_tools_closed(analysis_context):
    client, _, _ = analysis_context
    manifest = client.get('/api/v1/workspace/capabilities')
    assert manifest.status_code == 200
    data = manifest.json()['data']
    assert 'csv' in data['file_formats']
    assert data['max_files'] == 10
    assert data['profile_execution'] is True
    assert data['multi_dataset_execution'] is True
    assert data['depth_selection'] is True
    assert data['depths'] == ['FAST', 'STANDARD', 'DEEP']
    assert data['cross_dataset_join'] is False
    assert data['automatic_reports'] is False
    assert not data['sandbox_available']
    assert TestClient(app).get('/api/v1/workspace/capabilities').status_code == 401


def test_catalog_has_fifteen_categories_and_explicit_availability(analysis_context):
    client, _, _ = analysis_context
    response = client.get('/api/v1/analysis/profiles')
    assert response.status_code == 200
    catalog = response.json()['data']
    assert len(catalog['categories']) == 15
    assert all(p['availability'] in ('available', 'limited', 'planned') for p in catalog['items'])
    quality = client.get('/api/v1/analysis/profiles/general-quality').json()['data']
    assert quality['example_questions'] and quality['recommended_data']
    assert quality['availability'] == 'available'
    assert next(p for p in catalog['items'] if p['id'] == 'forecast-sales')['availability'] == 'planned'
    assert client.get('/api/v1/analysis/profiles/does-not-exist').status_code == 404


def test_attachments_authorized_persisted_and_survive_context_round_trip(analysis_context):
    client, sessions, _ = analysis_context
    dataset_id = client.post('/api/v1/datasets/upload', files={'file': ('sales.csv', b'sales\n12\n', 'text/csv')}).json()['data']['id']
    session_id = client.post('/api/v1/analysis/sessions', json={}).json()['data']['id']
    url = f'/api/v1/analysis/sessions/{session_id}'
    assert client.patch(url, json={'attached_dataset_ids': [dataset_id]}).status_code == 200
    restored = client.get(url).json()['data']['session']['attached_dataset_ids']
    assert restored == [dataset_id]
    with sessions() as db:
        context = db.get(AnalysisSession, session_id).context_json
        assert ConversationContext.model_validate(context).with_dataset(dataset_id, 1).model_dump()['attached_dataset_ids'] == [dataset_id]
        other = User(username='other', password_hash='unused', created_at=datetime.now(UTC), updated_at=datetime.now(UTC))
        db.add(other)
        db.flush()
        db.get(Dataset, dataset_id).user_id = other.id
        db.commit()
    assert client.patch(url, json={'attached_dataset_ids': [dataset_id]}).status_code == 403
    assert client.get(url).json()['data']['session']['attached_dataset_ids'] == []
    assert client.patch(url, json={'attached_dataset_ids': [999999]}).status_code == 404
    assert client.patch(url, json={'attached_dataset_ids': [dataset_id] * 11}).status_code == 422


def test_patch_preflight_is_allowed(analysis_context):
    client, _, _ = analysis_context
    response = client.options('/api/v1/analysis/sessions/1', headers={
        'Origin': 'http://localhost:5173', 'Access-Control-Request-Method': 'PATCH',
        'Access-Control-Request-Headers': 'content-type'})
    assert response.status_code == 200
    assert 'PATCH' in response.headers['access-control-allow-methods']


def test_attachments_cannot_change_during_active_analysis(analysis_context):
    client, _, _ = analysis_context
    dataset_id = client.post('/api/v1/datasets/upload', files={'file': ('sales.csv', b'sales\n12\n', 'text/csv')}).json()['data']['id']
    session_id = client.post('/api/v1/analysis/sessions', json={'dataset_id': dataset_id}).json()['data']['id']
    run = client.post('/api/v1/analysis/runs', json={'session_id': session_id, 'question': '分析销售额', 'request_id': 'attachment-lock'})
    assert run.status_code == 202
    assert client.patch(f'/api/v1/analysis/sessions/{session_id}', json={'attached_dataset_ids': []}).status_code == 409
