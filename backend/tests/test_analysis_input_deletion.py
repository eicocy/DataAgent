from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import AnalysisRecord, Dataset, DatasetVersion, User
from app.routers.analysis import AnalysisChatRequest
from app.services.analysis import submit_analysis
from test_analysis_api import analysis_context, make_session


def inputs(analysis_context):
    client, sessions, _ = analysis_context
    ids=[]
    for name in ['left.csv','right.csv']:
        response=client.post('/api/v1/datasets/upload',files={'file':(name,b'id,value\n1,10\n2,20\n','text/csv')})
        assert response.status_code==202
        ids.append(response.json()['data']['id'])
    sid=make_session(sessions,ids[0])
    with sessions() as db:
        uid=db.scalar(select(User.id))
        versions=[db.get(Dataset,did).current_version_id for did in ids]
    request=AnalysisChatRequest(session_id=sid,dataset_id=ids[0],question='join owned inputs',request_id='fixed-input-delete',depth='STANDARD',
        inputs=[{'alias':alias,'dataset_id':did,'dataset_version_id':vid} for alias,did,vid in zip(['primary','right'],ids,versions)])
    return client,sessions,uid,ids,versions,request


@pytest.mark.parametrize('status',['pending','running'])
def test_every_fixed_active_input_is_busy_and_version_survives(analysis_context,status):
    client,sessions,uid,ids,versions,request=inputs(analysis_context)
    submitted=client.post('/api/v1/analysis/runs',json=request.model_dump())
    assert submitted.status_code==202
    with sessions() as db:
        record=db.get(AnalysisRecord,submitted.json()['data']['record_id'])
        record.status=status;db.commit()
    for did in ids:
        response=client.delete(f'/api/v1/datasets/{did}')
        assert response.status_code==409
        assert response.json()['code']=='DATASET_BUSY'
    with sessions() as db:
        assert all(db.get(Dataset,did) is not None for did in ids)
        assert all(db.get(DatasetVersion,vid) is not None for vid in versions)


@pytest.mark.parametrize('status',['succeeded','partial','failed','cancelled'])
def test_terminal_inputs_can_be_deleted(analysis_context,status):
    client,sessions,uid,ids,_,request=inputs(analysis_context)
    with sessions() as db:
        record,_=submit_analysis(db,uid,request);record.status=status;db.commit()
    assert client.delete(f'/api/v1/datasets/{ids[1]}').status_code==200


def test_legacy_primary_remains_busy_but_unrelated_secondary_is_free(analysis_context):
    client,sessions,uid,ids,_,request=inputs(analysis_context)
    legacy=request.model_copy(update={'inputs':[],'depth':None})
    with sessions() as db:
        submit_analysis(db,uid,legacy)
    assert client.delete(f'/api/v1/datasets/{ids[0]}').status_code==409
    assert client.delete(f'/api/v1/datasets/{ids[1]}').status_code==200


def test_deleted_secondary_cannot_be_admitted_and_failure_rolls_back(analysis_context):
    from fastapi import HTTPException
    client,sessions,uid,ids,_,request=inputs(analysis_context)
    assert client.delete(f'/api/v1/datasets/{ids[1]}').status_code==200
    with sessions() as db:
        with pytest.raises(HTTPException) as raised:
            submit_analysis(db,uid,request)
        assert raised.value.status_code==403
        assert not db.in_transaction()
    with sessions() as db:
        assert db.scalar(select(AnalysisRecord.id)) is None


def test_repeated_admission_does_not_change_fixed_inputs(analysis_context):
    _,sessions,uid,_,_,request=inputs(analysis_context)
    with sessions() as db:
        first,created=submit_analysis(db,uid,request)
        second,recreated=submit_analysis(db,uid,request)
        assert created and not recreated and first.id==second.id
        assert first.request_config_json['inputs']==second.request_config_json['inputs']


def test_admission_loads_only_requested_versions_despite_large_history(analysis_context):
    from sqlalchemy import event
    _,sessions,uid,ids,versions,request=inputs(analysis_context)
    with sessions() as db:
        for did,vid in zip(ids,versions):
            original=db.get(DatasetVersion,vid)
            for number in range(2,32):
                historical=DatasetVersion(dataset_id=did,version_number=number,status='ready',source_kind='tool_transform',projection_table=f'dataset_{did}',schema_json=original.schema_json,profile_json=original.profile_json,transformations_json=[],original_available=True,created_at=datetime.now(UTC))
                db.add(historical);db.flush()
            db.get(Dataset,did).current_version_id=historical.id
        db.commit()
    loaded=[]
    def observed(version,context):loaded.append(version.id)
    event.listen(DatasetVersion,'load',observed)
    try:
        with sessions() as db:
            record,created=submit_analysis(db,uid,request)
            assert created
            assert [x['dataset_version_id'] for x in record.request_config_json['inputs']]==versions
        assert set(loaded)==set(versions)
        assert len(loaded)<=2
    finally:
        event.remove(DatasetVersion,'load',observed)
