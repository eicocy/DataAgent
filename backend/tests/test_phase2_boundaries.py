import pandas as pd
import pytest
from sqlalchemy import select, inspect
from app.analysis.catalog import build_registry
from app.analysis.context import DatasetContext
from app.analysis.errors import ToolError
from app.analysis.models import Permission, ToolExecutionRequest
from app.models import Dataset, User, CleanupTask, ToolExecutionRecord, BackgroundJob
from app.services.tool_execution import ToolExecutionService
from test_analysis_api import analysis_context


def test_bigint_grouping_and_rolling_preserve_exact_values():
    frame=pd.DataFrame({'g':['a','b','a'],'x':pd.array([2**53+1,None,0],dtype='Int64'),'t':[1,2,3]})
    registry=build_registry();context=DatasetContext.from_frame(frame)
    grouped=registry.execute('groupby_aggregate',context,{'dimensions':['g'],'metrics':[{'column':'x','aggregation':'sum'}]})
    assert grouped.data.rows==[{'g':'a','x_sum':2**53+1},{'g':'b','x_sum':None}]
    rolled=registry.execute('rolling_statistics',context,{'column':'x','order_by':[{'column':'t'}],'window':1,'aggregation':'sum'})
    assert rolled.data.rows[0]['x_rolling_statistics']==2**53+1
    stats=registry.execute('descriptive_statistics',context,{'columns':['x']})
    assert {v.statistic:v.value for v in stats.data.values}['max']==2**53+1


def test_tiny_correlation_is_defined():
    result=build_registry().execute('correlation',DatasetContext.from_frame(pd.DataFrame({'x':[1e-300,2e-300,3e-300],'y':[2e-300,4e-300,6e-300]})),{})
    assert result.data.pairs[1].coefficient==pytest.approx(1)


def test_typed_result_invariants_and_pivot_preflight():
    from pydantic import ValidationError
    from app.analysis.models import TableResult,CorrelationResult
    with pytest.raises(ValidationError):TableResult(columns=[],rows=[],row_count=99,truncated=False)
    with pytest.raises(ValidationError):CorrelationResult(method='pearson',columns=['x'],matrix=[[999]],pairs=[])
    context=DatasetContext.from_frame(pd.DataFrame({'a':['a','b'],'b':['x','y'],'c':['z','z'],'v':[1,2]}),max_cells=2)
    with pytest.raises(ToolError):build_registry().execute('pivot_table',context,{'index':['a','b'],'column':'c','value':'v','drop_missing':False})


def test_permissions_filter_chat_manifest():
    registry=build_registry(include_legacy=True)
    assert 'sql_query' not in {t['name'] for t in registry.get_llm_tool_manifest()}
    granted=registry.get_llm_tool_manifest(frozenset({Permission.READ_DATA,Permission.READ_DATABASE,Permission.TRANSFORM_DATA}))
    names={t['name'] for t in granted}
    assert 'sql_query' in names and 'rename_columns' not in names and 'chart_spec' not in names


def test_integer_growth_uses_exact_difference_and_zero_reason():
    registry=build_registry()
    context=DatasetContext.from_frame(pd.DataFrame({'x':pd.array([2**53+1,2**53+2],dtype='Int64'),'t':[1,2]}))
    args={'column':'x','order_by':[{'column':'t'}]}
    expected=1/(2**53+1)
    growth=registry.execute('growth_rate',context,args)
    change=registry.execute('percentage_change',context,args)
    assert growth.data.rows[0]['growth_rate']==pytest.approx(expected,abs=1e-25)
    assert change.data.rows[1]['x_percentage_change']==pytest.approx(expected,abs=1e-25)
    zero=registry.execute('growth_rate',DatasetContext.from_frame(pd.DataFrame({'x':[0,10],'t':[1,2]})),args)
    assert zero.data.rows[0]['status']=='zero_denominator' and zero.warnings


def test_stale_version_conflict_and_compensation(analysis_context,monkeypatch):
    from app.config import get_settings
    from app.services.jobs import perform_cleanup
    client,sessions,root=analysis_context
    monkeypatch.setattr(get_settings(),'artifact_dir',str(root/'artifacts'))
    identifier=client.post('/api/v1/datasets/upload',files={'file':('a.csv',b'x\n1\n\n3\n','text/csv')}).json()['data']['id']
    with sessions() as db:
        user=db.scalar(select(User));service=ToolExecutionService(db,db.get_bind(),db.get_bind())
        grants=frozenset({Permission.READ_DATA,Permission.TRANSFORM_DATA})
        first,_=service.submit(user.id,ToolExecutionRequest(tool_name='rename_columns',dataset_id=identifier,parameters={'columns':['x'],'names':{'x':'new'}},request_id='one'),grants)
        second,_=service.submit(user.id,ToolExecutionRequest(tool_name='rename_columns',dataset_id=identifier,parameters={'columns':['x'],'names':{'x':'other'}},request_id='two'),grants)
        service.execute(first.id);service.execute(second.id)
        assert first.status=='succeeded' and second.status=='failed'
        assert second.error_json['code']=='DATASET_VERSION_CONFLICT'
        tasks=list(db.scalars(select(CleanupTask).where(CleanupTask.status=='pending')))
        assert tasks
        for task in tasks: perform_cleanup(db,task,db.get_bind(),db.get_bind())
        assert not inspect(db.get_bind()).has_table(second.staging_projection)
        assert inspect(db.get_bind()).has_table(db.get(Dataset,identifier).projection_table)


def test_request_conflict_permissions_and_artifact_ownership(analysis_context,monkeypatch):
    from app.config import get_settings
    client,sessions,root=analysis_context
    monkeypatch.setattr(get_settings(),'artifact_dir',str(root/'artifacts'))
    identifier=client.post('/api/v1/datasets/upload',files={'file':('a.csv',b'x\n1\n2\n','text/csv')}).json()['data']['id']
    with sessions() as db:
        user=db.scalar(select(User));service=ToolExecutionService(db,db.get_bind(),db.get_bind())
        request=ToolExecutionRequest(tool_name='select_columns',dataset_id=identifier,parameters={'columns':['x']},request_id='read')
        record,_=service.submit(user.id,request);service.execute(record.id)
        assert service.read_artifact(user.id,record.id)['rows']==[{'x':1},{'x':2}]
        with pytest.raises(ToolError):service.read_artifact(user.id+100,record.id)
        with pytest.raises(ToolError):service.submit(user.id,request.model_copy(update={'parameters':{}}))
        with pytest.raises(ToolError):service.submit(user.id,ToolExecutionRequest(tool_name='rename_columns',dataset_id=identifier,parameters={'columns':['x'],'names':{'x':'y'}},request_id='forbidden'))
        job=db.scalar(select(BackgroundJob).where(BackgroundJob.kind=='tool',BackgroundJob.resource_id==record.id))
        assert job.completed_at is not None


def test_lost_lease_does_not_publish_or_leave_artifact(analysis_context,monkeypatch):
    from app.config import get_settings
    from app.services.jobs import terminate_job,perform_cleanup
    from app.services import tool_execution
    client,sessions,root=analysis_context
    monkeypatch.setattr(get_settings(),'artifact_dir',str(root/'artifacts'))
    identifier=client.post('/api/v1/datasets/upload',files={'file':('a.csv',b'x\n1\n2\n','text/csv')}).json()['data']['id']
    with sessions() as db:
        user=db.scalar(select(User));service=ToolExecutionService(db,db.get_bind(),db.get_bind());old=db.get(Dataset,identifier).current_version_id
        record,_=service.submit(user.id,ToolExecutionRequest(tool_name='rename_columns',dataset_id=identifier,parameters={'columns':['x'],'names':{'x':'y'}},request_id='interrupt'),frozenset({Permission.READ_DATA,Permission.TRANSFORM_DATA}))
        job=db.scalar(select(BackgroundJob).where(BackgroundJob.resource_id==record.id,BackgroundJob.kind=='tool'))
        job.status='running';job.lease_token='valid';db.commit()
        original=tool_execution.write_projection
        def interrupt(*args):
            original(*args);terminate_job(sessions,job.id)
        monkeypatch.setattr(tool_execution,'write_projection',interrupt)
        service.execute(record.id,job.id,'valid');db.expire_all()
        assert db.get(Dataset,identifier).current_version_id==old
        assert db.get(ToolExecutionRecord,record.id).status=='failed'
        for task in db.scalars(select(CleanupTask).where(CleanupTask.status=='pending')):perform_cleanup(db,task,db.get_bind(),db.get_bind())
        assert not list((root/'artifacts').glob('*.json'))


def test_large_preview_keeps_full_artifact(analysis_context,monkeypatch):
    from app.config import get_settings
    client,sessions,root=analysis_context
    monkeypatch.setattr(get_settings(),'artifact_dir',str(root/'artifacts'))
    data=('x\n'+'\n'.join(map(str,range(125)))+'\n').encode()
    identifier=client.post('/api/v1/datasets/upload',files={'file':('a.csv',data,'text/csv')}).json()['data']['id']
    with sessions() as db:
        user=db.scalar(select(User));service=ToolExecutionService(db,db.get_bind(),db.get_bind())
        record,_=service.submit(user.id,ToolExecutionRequest(tool_name='select_columns',dataset_id=identifier,parameters={'columns':['x']},request_id='preview'))
        service.execute(record.id)
        result=record.result_json
        assert len(result['data']['rows'])==100 and result['data']['row_count']==125 and result['data']['truncated']
        assert result['artifact_ref'] and len(service.read_artifact(user.id,record.id)['rows'])==125


def test_internal_legacy_adapter_uses_same_engine(analysis_context,monkeypatch):
    from app.config import get_settings
    client,sessions,root=analysis_context
    monkeypatch.setattr(get_settings(),'artifact_dir',str(root/'artifacts'))
    identifier=client.post('/api/v1/datasets/upload',files={'file':('a.csv',b'x\n10\n20\n','text/csv')}).json()['data']['id']
    with sessions() as db:
        user=db.scalar(select(User));service=ToolExecutionService(db,db.get_bind(),db.get_bind())
        record,_=service.submit(user.id,ToolExecutionRequest(tool_name='aggregate_data',dataset_id=identifier,parameters={'metrics':[{'column':'x','aggregation':'sum'}]},request_id='legacy-internal'))
        service.execute(record.id)
        assert record.status=='succeeded'
        assert record.result_json['data']['payload']['metric_values']=={'x_sum':30}


def test_timeout_after_artifact_write_rolls_back_and_compensates(analysis_context,monkeypatch):
    from app.config import get_settings
    from app.services.artifacts import ArtifactStore
    from app.services.jobs import perform_cleanup
    import time
    client,sessions,root=analysis_context
    monkeypatch.setattr(get_settings(),'artifact_dir',str(root/'artifacts'))
    identifier=client.post('/api/v1/datasets/upload',files={'file':('a.csv',b'x\n1\n2\n','text/csv')}).json()['data']['id']
    expired=[False];clock=time.monotonic;write=ArtifactStore.write
    def write_then_expire(*args,**kwargs):
        result=write(*args,**kwargs);expired[0]=True;return result
    monkeypatch.setattr(ArtifactStore,'write',write_then_expire)
    monkeypatch.setattr(time,'monotonic',lambda:clock()+(1000 if expired[0] else 0))
    with sessions() as db:
        user=db.scalar(select(User));service=ToolExecutionService(db,db.get_bind(),db.get_bind());old=db.get(Dataset,identifier).current_version_id
        record,_=service.submit(user.id,ToolExecutionRequest(tool_name='rename_columns',dataset_id=identifier,parameters={'columns':['x'],'names':{'x':'y'}},request_id='expire-after-file'),frozenset({Permission.READ_DATA,Permission.TRANSFORM_DATA}))
        service.execute(record.id);expired[0]=False
        assert record.status=='failed' and record.error_json['code']=='TOOL_TIMEOUT'
        assert db.get(Dataset,identifier).current_version_id==old
        assert list((root/'artifacts').glob('*.json'))
        for task in db.scalars(select(CleanupTask).where(CleanupTask.status=='pending')):perform_cleanup(db,task,db.get_bind(),db.get_bind())
        assert not list((root/'artifacts').glob('*.json'))


def test_delete_collects_all_version_projections_and_artifacts(analysis_context,monkeypatch):
    from app.config import get_settings
    from app.models import DatasetVersion
    client,sessions,root=analysis_context
    monkeypatch.setattr(get_settings(),'artifact_dir',str(root/'artifacts'))
    identifier=client.post('/api/v1/datasets/upload',files={'file':('a.csv',b'x\n1\n2\n','text/csv')}).json()['data']['id']
    with sessions() as db:
        user=db.scalar(select(User));service=ToolExecutionService(db,db.get_bind(),db.get_bind())
        record,_=service.submit(user.id,ToolExecutionRequest(tool_name='rename_columns',dataset_id=identifier,parameters={'columns':['x'],'names':{'x':'y'}},request_id='before-delete'),frozenset({Permission.READ_DATA,Permission.TRANSFORM_DATA}))
        service.execute(record.id)
        assert record.status=='succeeded'
        projections=[version.projection_table for version in db.scalars(select(DatasetVersion).where(DatasetVersion.dataset_id==identifier))]
        original=root/db.get(Dataset,identifier).stored_name
        bind=db.get_bind()
    assert len(projections)==2 and original.exists()
    assert client.delete(f'/api/v1/datasets/{identifier}').status_code==200
    assert not original.exists() and not list((root/'artifacts').glob('*.json'))
    assert all(not inspect(bind).has_table(name) for name in projections)


def test_old_schema_queued_analysis_sql_and_history_survive_rename(analysis_context,monkeypatch):
    from app.config import get_settings
    from app.models import DatasetVersion,AnalysisRecord
    from app.services.datasets import DatasetService
    from app.services.analysis import submit_analysis,execute_record
    from app.routers.analysis import AnalysisChatRequest
    from app.agent.executor import WorkflowExecutor
    from app.agent.schemas import ExecutionPlan
    from app.services.analysis_agent import AgentOutcome
    from test_analysis_api import make_session
    client,sessions,root=analysis_context
    monkeypatch.setattr(get_settings(),'artifact_dir',str(root/'artifacts'))
    identifier=client.post('/api/v1/datasets/upload',files={'file':('a.csv',b'day,x\n2026-01-01,9007199254740993\n2026-01-02,\n','text/csv')}).json()['data']['id']
    session_id=make_session(sessions,identifier)
    with sessions() as db:
        user=db.scalar(select(User));dataset=db.get(Dataset,identifier);old_version=dataset.current_version_id
        old=db.get(DatasetVersion,old_version)
        old.schema_json=dict(old.schema_json,columns=[{k:v for k,v in column.items() if k!='storage_type'} for column in old.schema_json['columns']]);db.commit()
        analysis,_=submit_analysis(db,user.id,AnalysisChatRequest(session_id=session_id,dataset_id=identifier,question='sum',request_id='queued-before-transform'))
        service=ToolExecutionService(db,db.get_bind(),db.get_bind())
        record,_=service.submit(user.id,ToolExecutionRequest(tool_name='rename_columns',dataset_id=identifier,parameters={'columns':['x','day'],'names':{'x':'renamed','day':'renamed_day'}},request_id='rename'),frozenset({Permission.READ_DATA,Permission.TRANSFORM_DATA}))
        service.execute(record.id)
        dataset=db.get(Dataset,identifier)
        _,columns=DatasetService(db,db.get_bind()).get(identifier,user.id)
        frame=DatasetService(db,db.get_bind()).load_frame(dataset,columns,old_version)
        assert frame.x.iloc[0]==2**53+1 and str(frame.x.dtype)=='Int64'
        assert pd.api.types.is_datetime64_any_dtype(frame.day)
        class Agent:
            def analyze(self,question,tools):
                assert set(tools.schema)=={'day','x'}
                sql=tools.execute('sql_query',{'query':f'SELECT x FROM dataset_{identifier}','max_rows':5})
                assert sql.data['rows'][0]['x']==2**53+1
                plan=ExecutionPlan.model_validate({'intent':'sum','steps':[{'step_id':'sum','tool_name':'aggregate','arguments':{'metrics':[{'column':'x','aggregation':'sum'}]}}]})
                executor=WorkflowExecutor(tools,get_settings(),emit=tools.on_event)
                report=executor.execute(plan,question)
                assert executor.results['sum']['rows'][0]['x_sum']==2**53+1
                return AgentOutcome(executor.calls,executor.results['sum'],None,None,report.status,report=report.model_dump())
        execute_record(db,analysis.id,Agent(),db.get_bind(),db.get_bind(),db.get_bind())
        assert db.get(AnalysisRecord,analysis.id).dataset_version_id==old_version
        step=db.scalar(select(ToolExecutionRecord).where(ToolExecutionRecord.analysis_record_id==analysis.id))
        assert step.status=='succeeded' and step.dataset_version_id==old_version and step.result_json['artifact_ref']
        assert step.parameters_json['metrics'][0]['column']=='x'
    history=client.get(f'/api/v1/analysis/runs/{analysis.id}').json()['data']
    assert history['status']=='partial' and history['tool_result']['rows'][0]['x_sum']==2**53+1
