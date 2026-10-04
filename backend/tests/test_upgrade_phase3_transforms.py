import pandas as pd
import pytest
from dataclasses import replace
from app.analysis.catalog import build_registry
from app.analysis.context import DatasetContext
from app.analysis.models import Permission
from app.analysis.errors import ToolError
from test_analysis_api import analysis_context

PERMISSIONS=frozenset({Permission.READ_DATA,Permission.TRANSFORM_DATA})

def test_join_real_full_frame_nonmutation_and_lineage():
    registry=build_registry()
    assert registry.exists('join_data')
    left=pd.DataFrame({'id':[1,2,3],'value':['a','b','c']})
    right=pd.DataFrame({'key':[1,2],'value':['x','y']})
    original=left.copy(deep=True)
    context=DatasetContext.from_frame(left,dataset_version=10,preview_rows=1,related_inputs={'right':DatasetContext.from_frame(right,dataset_id=2,dataset_version=20)})
    out=registry.calculate('join_data',context,{'right_alias':'right','left_on':['id'],'right_on':['key'],'how':'left','relationship':'many_to_one'})
    assert out.frame.value_right.tolist()[:2]==['x','y']
    assert out.data.row_count==3 and out.data.preview_truncated_count==2
    assert out.data.source_versions=={'left':10,'right':20}
    assert out.data.matched_left_rows==2 and out.data.unmatched_left_rows==1
    pd.testing.assert_frame_equal(left,original)
    assert registry.get('join_data').metadata.provides_frame

@pytest.mark.parametrize('right,error',[(pd.DataFrame({'id':[1,1]}),'JOIN_RELATIONSHIP_INVALID'),(pd.DataFrame({'id':['1']}),'JOIN_KEY_TYPE_MISMATCH'),(pd.DataFrame({'id':[None]}),'JOIN_NULL_KEYS')])
def test_join_rejects_unsafe_keys(right,error):
    registry=build_registry()
    context=DatasetContext.from_frame(pd.DataFrame({'id':[1]}),related_inputs={'r':DatasetContext.from_frame(right)})
    with pytest.raises(ToolError) as exc:
        registry.calculate('join_data',context,{'right_alias':'r','left_on':['id'],'right_on':['id'],'how':'left','relationship':'many_to_one'})
    assert exc.value.code==error

def test_join_premerge_budget():
    context=DatasetContext.from_frame(pd.DataFrame({'id':[1]}),max_rows=2,related_inputs={'r':DatasetContext.from_frame(pd.DataFrame({'id':[1,1,1]}))})
    with pytest.raises(ToolError) as exc:
        build_registry().calculate('join_data',context,{'right_alias':'r','left_on':['id'],'right_on':['id'],'how':'left','relationship':'one_to_many'})
    assert exc.value.code=='RESULT_BUDGET_EXCEEDED'

def test_score_public_deterministic_and_empty():
    registry=build_registry()
    assert registry.exists('data_quality_score')
    context=DatasetContext.from_frame(pd.DataFrame({'x':[1,None,1],'label':['a','', 'a']}))
    out=registry.calculate('data_quality_score',context,{})
    assert out.data.rule_version=='quality-score-v1'
    assert out.data.score<100
    assert {f.issue:f.count for f in out.data.findings if f.count}=={'missing':1,'empty':1,'duplicate':1}
    assert out.data==registry.calculate('data_quality_score',context,{}).data
    empty=registry.calculate('data_quality_score',DatasetContext.from_frame(pd.DataFrame({'x':[]})),{}).data
    assert empty.score is None and empty.status=='empty'

def test_cleaning_plan_private_intermediate_and_one_result():
    registry=build_registry()
    assert registry.exists('cleaning_plan')
    frame=pd.DataFrame({'x':[1,None,1]})
    out=registry.calculate('cleaning_plan',DatasetContext.from_frame(frame),{'operations':[{'tool':'fill_missing_values','parameters':{'columns':['x'],'strategy':'constant','value':0}},{'tool':'remove_duplicates','parameters':{'columns':['x'],'keep':'first'}}]},PERMISSIONS)
    assert out.frame.x.tolist()==[1,0]
    assert frame.x.isna().sum()==1
    assert len(out.data.steps)==2 and out.data.before_rows==3

def test_cleaning_preview_confirmation_api(analysis_context,monkeypatch):
    from app.config import get_settings
    client,sessions,folder=analysis_context
    monkeypatch.setattr(get_settings(),'artifact_dir',str(folder/'artifacts'))
    dataset=client.post('/api/v1/datasets/upload',files={'file':('a.csv',b'x\n1\n\n3\n','text/csv')}).json()['data']['id']
    version=client.get(f'/api/v1/datasets/{dataset}').json()['data']['current_version_id']
    body={'dataset_version_id':version,'operations':[{'tool':'rename_columns','parameters':{'columns':['x'],'names':{'x':'y'}}}]}
    preview=client.post(f'/api/v1/datasets/{dataset}/transformations/preview',json=body)
    assert preview.status_code==200,preview.text
    assert client.get(f'/api/v1/datasets/{dataset}').json()['data']['current_version_id']==version
    confirmed={**body,'confirmed':True,'preview_hash':preview.json()['data']['preview_hash'],'request_id':'clean-1'}
    response=client.post(f'/api/v1/datasets/{dataset}/transformations',json=confirmed)
    assert response.status_code==202,response.text
    identifier=response.json()['data']['execution_id']
    result=client.get(f'/api/v1/datasets/{dataset}/transformations/{identifier}')
    assert result.json()['data']['status']=='succeeded',result.text
    assert result.json()['data']['output_version']['id']!=version
    assert client.post(f'/api/v1/datasets/{dataset}/transformations',json=confirmed).json()['data']['execution_id']==identifier


@pytest.mark.parametrize('relationship,left,right',[('one_to_one',[1,1],[1]),('one_to_many',[1,1],[1,2]),('many_to_one',[1,2],[1,1])])
def test_join_rejects_declared_grain_violation(relationship,left,right):
    ctx=DatasetContext.from_frame(pd.DataFrame({'id':left}),related_inputs={'r':DatasetContext.from_frame(pd.DataFrame({'id':right}))})
    with pytest.raises(ToolError,match='JOIN_RELATIONSHIP_INVALID'):
        build_registry().calculate('join_data',ctx,{'right_alias':'r','left_on':['id'],'right_on':['id'],'how':'inner','relationship':relationship})


@pytest.mark.parametrize('budgets',[{'max_columns':1},{'max_bytes':600}])
def test_join_rejects_expanded_columns_and_large_matched_row(budgets):
    left=pd.DataFrame({'id':[1],'large':['x'*100]})
    right=pd.DataFrame({'id':[1,1,1]})
    ctx=DatasetContext.from_frame(left,related_inputs={'r':DatasetContext.from_frame(right)},**budgets)
    with pytest.raises(ToolError,match='RESULT_BUDGET_EXCEEDED'):
        build_registry().calculate('join_data',ctx,{'right_alias':'r','left_on':['id'],'right_on':['id'],'how':'left','relationship':'one_to_many'})


def test_join_rejects_suffix_collision_and_many_to_many():
    registry=build_registry()
    params={'right_alias':'r','left_on':['id'],'right_on':['id'],'how':'left','relationship':'many_to_many'}
    with pytest.raises(ToolError,match='TOOL_INPUT_INVALID'): registry.validate_input('join_data',params)
    params['relationship']='one_to_one'
    ctx=DatasetContext.from_frame(pd.DataFrame({'id':[1],'x':[2],'x_left':[3]}),related_inputs={'r':DatasetContext.from_frame(pd.DataFrame({'id':[1],'x':[4]}))})
    with pytest.raises(ToolError,match='JOIN_COLUMN_AMBIGUOUS'): registry.calculate('join_data',ctx,params)


def test_join_composite_keys_full_counts_and_source_immutability():
    left=pd.DataFrame({'a':[1,1,2],'b':['x','y','z']})
    right=pd.DataFrame({'c':[1,1,3],'d':['x','x','a'],'number':[10,20,30]})
    ctx=DatasetContext.from_frame(left,related_inputs={'r':DatasetContext.from_frame(right)})
    out=build_registry().calculate('join_data',ctx,{'right_alias':'r','left_on':['a','b'],'right_on':['c','d'],'how':'inner','relationship':'one_to_many'})
    assert out.frame.number.tolist()==[10,20]
    assert out.data.matched_left_rows==1 and out.data.matched_right_rows==2
    assert len(right)==3 and right.number.tolist()==[10,20,30]


def test_quality_strict_rules_full_counts_bounded_samples_nullable_and_nonfinite():
    frame=pd.DataFrame({'v':['2','bad','inf',None,'20'],'day':['2024-01-01','bad','NaT',None,'2024-01-05']})
    out=build_registry().calculate('data_quality_score',DatasetContext.from_frame(frame),{'field_rules':{'v':{'type':'numeric','minimum':0,'maximum':10},'day':{'type':'datetime','datetime_format':'%Y-%m-%d'}},'limit':1}).data
    issues={(f.issue,f.column):f.count for f in out.findings}
    assert issues['invalid_numeric','v']==1
    assert issues['invalid_datetime','day']==2
    assert issues['nonfinite','v']==1 and issues['range','v']==2
    assert all(len(f.row_refs)<=1 for f in out.findings)
    nullable=pd.DataFrame({'x':pd.Series([1,None],dtype='Int64')})
    assert build_registry().calculate('data_quality_score',DatasetContext.from_frame(nullable),{}).data.score<100


@pytest.mark.parametrize('step',[{'tool':'remove_duplicates','parameters':{'columns':['x']}},{'tool':'fill_missing_values','parameters':{'columns':['x']}},{'tool':'outlier_treatment','parameters':{'columns':['x']}},{'tool':'eval','parameters':{'columns':['x']}},{'tool':'rename_columns','parameters':{'columns':['x'],'names':{'x':'y'},'path':'a'}}])
def test_cleaning_rejects_implicit_or_unallowlisted_operations(step):
    with pytest.raises(ToolError,match='TOOL_INPUT_INVALID'):
        build_registry().validate_input('cleaning_plan',{'operations':[step]})


def _upload(client,data=b'id,x\n1,1\n2,2\n3,3\n'):
    identifier=client.post('/api/v1/datasets/upload',files={'file':('a.csv',data,'text/csv')}).json()['data']['id']
    version=client.get(f'/api/v1/datasets/{identifier}').json()['data']['current_version_id']
    return identifier,version


def test_join_preview_confirm_lineage_old_data_and_owned_quality(analysis_context,monkeypatch):
    from app.config import get_settings
    from app.models import Dataset,DatasetVersion,User
    from app.services.datasets import DatasetService
    from sqlalchemy import select
    client,sessions,folder=analysis_context
    monkeypatch.setattr(get_settings(),'artifact_dir',str(folder/'artifacts'))
    left,lv=_upload(client);right,rv=_upload(client,b'key,name\n1,A\n2,B\n')
    body={'dataset_version_id':lv,'right_dataset_id':right,'right_version_id':rv,'left_on':['id'],'right_on':['key'],'how':'left','relationship':'many_to_one'}
    preview=client.post(f'/api/v1/datasets/{left}/joins/preview',json=body)
    assert preview.status_code==200,preview.text
    assert preview.json()['data']['after']['column_count']==4
    request={**body,'confirmed':True,'preview_hash':preview.json()['data']['preview_hash'],'request_id':'join-1'}
    response=client.post(f'/api/v1/datasets/{left}/joins',json=request)
    assert response.status_code==202,response.text
    eid=response.json()['data']['execution_id']
    status=client.get(f'/api/v1/datasets/{left}/joins/{eid}').json()['data']
    assert status['status']=='succeeded',status
    out=status['output_version'];assert not out['original_available']
    assert out['transformations'][0]['source_versions']==[{'dataset_id':left,'version_id':lv},{'dataset_id':right,'version_id':rv}]
    with sessions() as db:
        dataset=db.get(Dataset,left);svc=DatasetService(db,db.get_bind());user=db.scalar(select(User))
        _,cols=svc.get(left,user.id)
        assert list(svc.load_frame(dataset,cols,lv).columns)==['id','x']
        assert list(svc.load_frame(dataset,cols,out['id']).columns)==['id','x','key','name']
        assert db.get(Dataset,right).current_version_id==rv
    assert client.get(f'/api/v1/datasets/{left}/quality',params={'dataset_version_id':lv}).status_code==200
    assert len(client.get(f'/api/v1/datasets/{left}/versions').json()['data'])==2
    assert client.post(f'/api/v1/datasets/{left}/joins',json=request).json()['data']['execution_id']==eid


def test_cleaning_stale_preview_hash_conflict_and_confirmation(analysis_context,monkeypatch):
    from app.config import get_settings
    client,_,folder=analysis_context
    monkeypatch.setattr(get_settings(),'artifact_dir',str(folder/'artifacts'))
    dataset,version=_upload(client)
    body={'dataset_version_id':version,'operations':[{'tool':'rename_columns','parameters':{'columns':['x'],'names':{'x':'y'}}}]}
    preview=client.post(f'/api/v1/datasets/{dataset}/transformations/preview',json=body).json()['data']
    confirmed={**body,'confirmed':True,'preview_hash':preview['preview_hash'],'request_id':'first'}
    assert client.post(f'/api/v1/datasets/{dataset}/transformations',json={**confirmed,'confirmed':False}).status_code==422
    assert client.post(f'/api/v1/datasets/{dataset}/transformations',json={**confirmed,'preview_hash':'0'*64}).status_code==409
    assert client.post(f'/api/v1/datasets/{dataset}/transformations',json=confirmed).status_code==202
    assert client.post(f'/api/v1/datasets/{dataset}/transformations',json={**confirmed,'request_id':'stale'}).status_code==409
    assert client.post(f'/api/v1/datasets/{dataset}/transformations/preview',json=body).status_code==409
    changed={**body,'operations':[{'tool':'rename_columns','parameters':{'columns':['x'],'names':{'x':'z'}}}]}
    assert client.post(f'/api/v1/datasets/{dataset}/transformations',json={**confirmed,**changed}).status_code==409


def test_join_cross_owner_right_rejected(analysis_context):
    from fastapi.testclient import TestClient
    from app.main import app
    client,_,_ = analysis_context
    left,lv=_upload(client)
    other=TestClient(app,headers={'Origin':'http://localhost:5173'})
    registration=other.post('/api/v1/auth/register',json={'username':'bobuser','password':'safe-password-123'})
    assert registration.status_code==201,registration.text
    right,rv=_upload(other)
    body={'dataset_version_id':lv,'right_dataset_id':right,'right_version_id':rv,'left_on':['id'],'right_on':['id'],'how':'left','relationship':'many_to_one'}
    assert client.post(f'/api/v1/datasets/{left}/joins/preview',json=body).status_code==404
    assert client.get(f'/api/v1/datasets/{right}/quality',params={'dataset_version_id':rv}).status_code==404


def test_queued_join_blocks_right_deletion_and_competing_cas_cleanup(analysis_context,monkeypatch):
    from app.config import get_settings
    from app.models import Dataset,User,CleanupTask,ToolExecutionRecord
    from app.services.tool_execution import ToolExecutionService
    from app.analysis.models import ToolExecutionRequest
    from sqlalchemy import select
    client,sessions,folder=analysis_context
    monkeypatch.setattr(get_settings(),'artifact_dir',str(folder/'artifacts'))
    left,lv=_upload(client);right,rv=_upload(client)
    params={'right_dataset_id':right,'right_version_id':rv,'left_on':['id'],'right_on':['id'],'how':'left','relationship':'many_to_one'}
    with sessions() as db:
        svc=ToolExecutionService(db,db.get_bind(),db.get_bind());user=db.scalar(select(User))
        first,_=svc.submit(user.id,ToolExecutionRequest(tool_name='publish_join',dataset_id=left,dataset_version=lv,parameters=params,request_id='j1'),PERMISSIONS)
        second,_=svc.submit(user.id,ToolExecutionRequest(tool_name='publish_join',dataset_id=left,dataset_version=lv,parameters=params,request_id='j2'),PERMISSIONS)
        assert client.delete(f'/api/v1/datasets/{right}').status_code==409
        svc.execute(first.id);svc.execute(second.id)
        db.expire_all()
        assert db.get(ToolExecutionRecord,first.id).status=='succeeded',db.get(ToolExecutionRecord,first.id).error_json
        failed=db.get(ToolExecutionRecord,second.id)
        assert failed.status=='failed' and failed.error_json['code']=='DATASET_VERSION_CONFLICT'
        assert any(t.status=='pending' for t in db.scalars(select(CleanupTask)) if t.payload_json.get('tool_execution_id')==second.id)
        assert db.get(Dataset,right).current_version_id==rv


def test_confirmation_rejects_integer_true_and_preview_never_reserves_storage(analysis_context):
    from app.models import CleanupTask,DatasetVersion,ToolExecutionRecord
    from sqlalchemy import select,func
    client,sessions,_=analysis_context
    dataset,version=_upload(client)
    body={'dataset_version_id':version,'operations':[{'tool':'rename_columns','parameters':{'columns':['x'],'names':{'x':'y'}}}]}
    preview=client.post(f'/api/v1/datasets/{dataset}/transformations/preview',json=body).json()['data']
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(ToolExecutionRecord))==0
        assert db.scalar(select(func.count()).select_from(CleanupTask))==0
        assert db.scalar(select(func.count()).select_from(DatasetVersion))==1
    request={**body,'confirmed':1,'preview_hash':preview['preview_hash'],'request_id':'integer-confirm'}
    assert client.post(f'/api/v1/datasets/{dataset}/transformations',json=request).status_code==422


def test_right_source_removed_after_staging_cannot_publish_and_reserves_cleanup(analysis_context,monkeypatch):
    from app.config import get_settings
    from app.models import Dataset,DatasetVersion,User,CleanupTask,ToolExecutionRecord
    from app.services.tool_execution import ToolExecutionService
    from app.analysis.models import ToolExecutionRequest
    from sqlalchemy import select,func
    from app.services import tool_execution
    client,sessions,folder=analysis_context
    monkeypatch.setattr(get_settings(),'artifact_dir',str(folder/'artifacts'))
    left,lv=_upload(client);right,rv=_upload(client)
    params={'right_dataset_id':right,'right_version_id':rv,'left_on':['id'],'right_on':['id'],'how':'left','relationship':'many_to_one'}
    with sessions() as db:
        svc=ToolExecutionService(db,db.get_bind(),db.get_bind());user=db.scalar(select(User))
        record,_=svc.submit(user.id,ToolExecutionRequest(tool_name='publish_join',dataset_id=left,dataset_version=lv,parameters=params,request_id='deleted-source'),PERMISSIONS)
        original=tool_execution.write_projection
        def remove_right_after_write(*args,**kwargs):
            result=original(*args,**kwargs)
            db.delete(db.get(Dataset,right));db.commit()
            return result
        monkeypatch.setattr(tool_execution,'write_projection',remove_right_after_write)
        svc.execute(record.id);db.expire_all()
        failure=db.get(ToolExecutionRecord,record.id)
        assert failure.status=='failed' and failure.error_json['code']=='JOIN_INPUT_UNAVAILABLE'
        assert db.get(Dataset,left).current_version_id==lv
        assert db.scalar(select(func.count()).select_from(DatasetVersion).where(DatasetVersion.dataset_id==left))==1
        cleanup=[t for t in db.scalars(select(CleanupTask)) if t.payload_json.get('tool_execution_id')==record.id]
        assert len(cleanup)==2 and all(t.status=='pending' for t in cleanup)


def test_changed_source_checksum_invalidates_preview(analysis_context):
    from app.models import DatasetVersion
    client,sessions,_=analysis_context
    dataset,version=_upload(client)
    body={'dataset_version_id':version,'operations':[{'tool':'rename_columns','parameters':{'columns':['x'],'names':{'x':'y'}}}]}
    preview=client.post(f'/api/v1/datasets/{dataset}/transformations/preview',json=body).json()['data']
    with sessions() as db:
        db.get(DatasetVersion,version).source_checksum='a'*64;db.commit()
    response=client.post(f'/api/v1/datasets/{dataset}/transformations',json={**body,'confirmed':True,'preview_hash':preview['preview_hash'],'request_id':'changed-source'})
    assert response.status_code==409


def test_cleaning_exact_penalties_original_missing_and_failure_atomicity():
    registry=build_registry()
    frame=pd.DataFrame({'x':[1,None,1],'text':['a','','a']})
    score=registry.calculate('data_quality_score',DatasetContext.from_frame(frame),{}).data
    assert score.score==round(100-30/6-10/6-20/3,6)
    with pytest.raises(ToolError):
        registry.calculate('cleaning_plan',DatasetContext.from_frame(frame),{'operations':[{'tool':'fill_missing_values','parameters':{'columns':['x'],'strategy':'constant','value':0}},{'tool':'rename_columns','parameters':{'columns':['x'],'names':{'x':'text'}}}]},PERMISSIONS)
    assert frame.x.isna().sum()==1 and list(frame.columns)==['x','text']


def test_join_publisher_locks_both_sources_in_stable_order(analysis_context,monkeypatch):
    from app.config import get_settings
    from app.models import Dataset,DatasetVersion,User
    from app.services.tool_execution import ToolExecutionService
    from app.analysis.models import ToolExecutionRequest
    from sqlalchemy import select,event
    client,sessions,folder=analysis_context
    monkeypatch.setattr(get_settings(),'artifact_dir',str(folder/'artifacts'))
    right,rv=_upload(client);left,lv=_upload(client)
    with sessions() as db:
        svc=ToolExecutionService(db,db.get_bind(),db.get_bind());user=db.scalar(select(User))
        request=ToolExecutionRequest(tool_name='publish_join',dataset_id=left,dataset_version=lv,parameters={'right_dataset_id':right,'right_version_id':rv,'left_on':['id'],'right_on':['id'],'how':'left','relationship':'many_to_one'},request_id='lock-order')
        record,_=svc.submit(user.id,request,PERMISSIONS)
        locks=[]
        def capture(state):
            statement=state.statement
            if getattr(statement,'_for_update_arg',None) is not None and getattr(statement,'column_descriptions',None):
                entity=statement.column_descriptions[0].get('entity')
                if entity in {Dataset,DatasetVersion}: locks.append((entity,statement.compile().params['id_1']))
        event.listen(db,'do_orm_execute',capture)
        svc.execute(record.id)
        event.remove(db,'do_orm_execute',capture)
        assert record.status=='succeeded',record.error_json
        dataset_locks=[identifier for entity,identifier in locks if entity is Dataset]
        assert dataset_locks==[right,left,right,left,left]
        assert [identifier for entity,identifier in locks if entity is DatasetVersion]==[rv,lv,rv,lv]


def test_queued_join_missing_right_fails_before_publication(analysis_context):
    from app.models import Dataset,DatasetVersion,User
    from app.services.tool_execution import ToolExecutionService
    from app.analysis.models import ToolExecutionRequest
    from sqlalchemy import select,func
    client,sessions,_=analysis_context
    left,lv=_upload(client);right,rv=_upload(client)
    with sessions() as db:
        svc=ToolExecutionService(db,db.get_bind(),db.get_bind());user=db.scalar(select(User))
        record,_=svc.submit(user.id,ToolExecutionRequest(tool_name='publish_join',dataset_id=left,dataset_version=lv,parameters={'right_dataset_id':right,'right_version_id':rv,'left_on':['id'],'right_on':['id'],'how':'left','relationship':'many_to_one'},request_id='queued-deleted'),PERMISSIONS)
        db.delete(db.get(Dataset,right));db.commit()
        svc.execute(record.id)
        assert record.status=='failed'
        assert db.get(Dataset,left).current_version_id==lv
        assert db.scalar(select(func.count()).select_from(DatasetVersion).where(DatasetVersion.dataset_id==left))==1


def test_submit_cross_owner_right_and_idempotency_payload_misuse(analysis_context):
    from app.models import Dataset,User
    from app.services.tool_execution import ToolExecutionService
    from app.analysis.models import ToolExecutionRequest
    from sqlalchemy import select
    client,sessions,_=analysis_context
    left,lv=_upload(client);right,rv=_upload(client)
    with sessions() as db:
        svc=ToolExecutionService(db,db.get_bind(),db.get_bind());user=db.scalar(select(User))
        params={'right_dataset_id':right,'right_version_id':rv,'left_on':['id'],'right_on':['id'],'how':'left','relationship':'many_to_one'}
        request=ToolExecutionRequest(tool_name='publish_join',dataset_id=left,dataset_version=lv,parameters=params,request_id='retry-key')
        original,_=svc.submit(user.id,request,PERMISSIONS)
        replay,created=svc.submit(user.id,request,PERMISSIONS)
        assert not created and replay.id==original.id
        with pytest.raises(ToolError,match='TOOL_REQUEST_ID_CONFLICT'):
            svc.submit(user.id,request.model_copy(update={'parameters':{**params,'how':'inner'}}),PERMISSIONS)
        db.rollback()
        db.get(Dataset,right).user_id=999;db.commit()
        with pytest.raises(ToolError,match='JOIN_INPUT_UNAVAILABLE'):
            svc.submit(user.id,request.model_copy(update={'request_id':'other-owner'}),PERMISSIONS)


def test_join_rejects_date_vs_timestamp_and_timezone_semantics():
    from datetime import date
    registry=build_registry()
    left=pd.DataFrame({'key':[date(2024,1,1)]})
    right=pd.DataFrame({'key':[pd.Timestamp('2024-01-01')]})
    params={'right_alias':'r','left_on':['key'],'right_on':['key'],'how':'left','relationship':'one_to_one'}
    with pytest.raises(ToolError,match='JOIN_KEY_TYPE_MISMATCH'):
        registry.calculate('join_data',DatasetContext.from_frame(left,related_inputs={'r':DatasetContext.from_frame(right)}),params)
    left=pd.DataFrame({'key':[pd.Timestamp('2024-01-01')]})
    right=pd.DataFrame({'key':[pd.Timestamp('2024-01-01',tz='UTC')]})
    with pytest.raises(ToolError,match='JOIN_KEY_TYPE_MISMATCH'):
        registry.calculate('join_data',DatasetContext.from_frame(left,related_inputs={'r':DatasetContext.from_frame(right)}),params)


@pytest.mark.parametrize('route',['transformations','joins'])
def test_confirmation_request_id_65_rejected_64_accepted_over_http(analysis_context,monkeypatch,route):
    from app.config import get_settings
    from app.main import app
    from fastapi.testclient import TestClient
    client,_,folder=analysis_context
    monkeypatch.setattr(get_settings(),'artifact_dir',str(folder/'artifacts'))
    dataset,version=_upload(client)
    if route=='transformations':
        body={'dataset_version_id':version,'operations':[{'tool':'rename_columns','parameters':{'columns':['x'],'names':{'x':'y'}}}]}
    else:
        right,rv=_upload(client)
        body={'dataset_version_id':version,'right_dataset_id':right,'right_version_id':rv,'left_on':['id'],'right_on':['id'],'how':'left','relationship':'many_to_one'}
    http=TestClient(app,headers={'Origin':'http://localhost:5173'},raise_server_exceptions=False)
    http.cookies.update(client.cookies)
    preview=http.post(f'/api/v1/datasets/{dataset}/{route}/preview',json=body)
    assert preview.status_code==200,preview.text
    confirmed={**body,'confirmed':True,'preview_hash':preview.json()['data']['preview_hash']}
    rejected=http.post(f'/api/v1/datasets/{dataset}/{route}',json={**confirmed,'request_id':'r'*65})
    assert rejected.status_code==422,rejected.text
    accepted=http.post(f'/api/v1/datasets/{dataset}/{route}',json={**confirmed,'request_id':'r'*64})
    assert accepted.status_code==202,accepted.text
    execution_id=accepted.json()['data']['execution_id']
    status=http.get(f'/api/v1/datasets/{dataset}/{route}/{execution_id}')
    assert status.json()['data']['status']=='succeeded',status.text
