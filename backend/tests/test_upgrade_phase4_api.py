from datetime import UTC, datetime
from sqlalchemy import select
from test_analysis_api import analysis_context, make_session
from test_upgrade_phase4_artifacts import source
from app.models import AnalysisRecord, AnalysisArtifact, Dataset, User, BackgroundJob
from app.services.artifacts import ArtifactStore


def setup_source(client, sessions):
    rid, sid = source(client, sessions)
    with sessions() as db:
        record = db.get(AnalysisRecord, rid)
        record.dataset_version_id = db.get(Dataset, record.dataset_id).current_version_id
        item = ArtifactStore(db).write(record, 'full', {'columns':['x'], 'rows':[{'x':x} for x in range(150)]})
        from app.artifacts.manager import ArtifactManager
        ArtifactManager(db).finalize_record(record)
        db.commit()
        return rid, sid, item['artifact_id'], record.dataset_id, record.dataset_version_id


def test_workspace_restores_artifacts_report_and_selection(analysis_context):
    client, sessions, _ = analysis_context
    rid, sid, aid, did, vid = setup_source(client, sessions)
    saved = client.patch(f'/api/v1/analysis/sessions/{sid}/workspace', json={'selected_artifact_id':aid})
    assert saved.status_code == 200, saved.text
    value = client.get(f'/api/v1/analysis/sessions/{sid}/workspace')
    assert value.status_code == 200, value.text
    data = value.json()['data']
    assert data['selected_artifact_id'] == aid
    assert data['latest_analysis']['record_id'] == rid
    assert data['artifacts']['items'][0]['session_id'] == sid
    assert client.get('/api/v1/artifacts', params={'session_id':sid,'type':'table','status':'READY'}).json()['data']['items'][0]['id'] == aid
    with sessions() as db:
        ArtifactStore(db)._path(db.get(AnalysisArtifact,aid).stored_name).unlink()
    assert client.get('/api/v1/artifacts',params={'session_id':sid,'status':'READY'}).json()['data']['items']==[]
    assert client.get('/api/v1/artifacts',params={'session_id':sid,'status':'EXPIRED'}).json()['data']['items'][0]['id']==aid


def test_reference_rejects_other_session_and_pins_complete_source(analysis_context):
    client, sessions, _ = analysis_context
    rid, sid, aid, did, vid = setup_source(client, sessions)
    from app.artifacts.references import resolve_references
    with sessions() as db:
        user_id = db.get(AnalysisRecord,rid).user_id
        refs = resolve_references(db,user_id,sid,[aid])
        assert refs[0]['dataset_versions'][0]['dataset_version_id'] == vid
        payload = ArtifactStore(db).read(db.get(AnalysisArtifact,refs[0]['source_artifact_id']))
        assert len(payload['rows']) == 150
    other = make_session(sessions, did)
    request = dict(session_id=other,dataset_id=did,question='分析引用',request_id='ref-wrong',artifact_refs=[aid])
    rejected = client.post('/api/v1/analysis/runs',json=request)
    assert rejected.status_code == 422 and rejected.json()['code']=='ARTIFACT_SESSION_MISMATCH'
    assert client.patch(f'/api/v1/analysis/sessions/{other}/workspace',json={'selected_artifact_id':aid}).status_code == 404


def test_report_create_and_export_request_id_replay_and_conflict(analysis_context):
    client, sessions, _ = analysis_context
    rid, sid, aid, did, vid = setup_source(client,sessions)
    body = dict(session_id=sid, source_record_ids=[rid], request_id='report-stable',
        spec={'title':'report','dataset_id':did,'dataset_version_id':vid})
    first = client.post('/api/v1/reports',json=body)
    assert first.status_code == 202, first.text
    replay = client.post('/api/v1/reports',json=body)
    assert replay.status_code == 200, replay.text
    assert replay.json()['data']['record_id'] == first.json()['data']['record_id']
    changed = client.post('/api/v1/reports',json={**body,'spec':{**body['spec'],'title':'changed'}})
    assert changed.status_code == 409
    from test_reports_api import run_report_task
    run_report_task(sessions,first.json()['data']['record_id'])
    report = client.get(first.json()['data']['status_url']).json()['data']['report']['report']
    url = f"/api/v1/reports/{report['id']}/versions/1/exports/json"
    exported = client.post(url,json={'request_id':'export-stable'})
    again = client.post(url,json={'request_id':'export-stable'})
    assert again.status_code == 200
    assert again.json()['data']['record_id'] == exported.json()['data']['record_id']


def test_regeneration_has_new_identity_and_source_relation(analysis_context):
    client,sessions,_ = analysis_context
    rid,sid,aid,did,vid = setup_source(client,sessions)
    result = client.post(f'/api/v1/artifacts/{aid}/regenerations')
    assert result.status_code == 201, result.text
    item = result.json()['data']
    assert item['id'] != aid and item['source_artifact_ids'] == [aid]
    assert item['expires_at'] is None
    assert len(client.get(f"/api/v1/artifacts/{item['id']}/preview").json()['data']['preview']['rows']) == 100
