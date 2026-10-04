from decimal import Decimal
from types import SimpleNamespace
import inspect
import pandas as pd
import pytest
from app.execution.evidence import ReportContent, render_report
from app.datasets.profiler import build_profile
from app.services.datasets import DatasetService, _data_type
from app.services.analysis_tools import DatasetTools
from app.agent.graph_executor import InputWorkspace
from app.semantic.detectors import detect_semantics
from app.semantic.mappings import parse_corrections
from app.profiles.catalog import profile_catalog
from app.agent.schemas import AnalysisPlan
from app.agent.plan_validator import PlanValidator
from app.analysis.models import Permission


def test_decimal_evidence_exact_and_bounded():
    content=ReportContent(template='金额 {amount}',facts=[{'key':'amount','step_id':'k','path':['amount']}],evidence_refs=['k'])
    assert render_report(content,{'k':{'amount':'9007199254740993.03'}})=='金额 9007199254740993.03'
    for bad in ['text','NaN','Infinity','1e1000000','9'*1001]:
        with pytest.raises(ValueError): render_report(content,{'k':{'amount':bad}})


def test_decimal_profile_and_publication_type():
    frame=pd.DataFrame({'amount':[Decimal('9007199254740993.01234567891'),Decimal('0.2')]})
    schema,profile=build_profile(frame)
    assert schema.columns[0].storage_type=='decimal'
    assert schema.columns[0].semantic_type=='Numeric'
    assert _data_type(frame.amount)[0]=='decimal'


def test_explicit_precision_loader_opt_in():
    assert inspect.signature(DatasetService.load_frame).parameters['preserve_decimal'].default is False


def test_decimal_metric_concepts_and_user_currency_correction():
    frame=pd.DataFrame({k:[Decimal('1')] for k in ['cost','expense','budget','actual','profit','quantity']})
    assert {m.concept for m in detect_semantics(frame,3)}=={'cost','operating_expense','budget','actual','profit','quantity'}
    correction=parse_corrections('amount 是销售额，币种 USD，单位 美元',['amount'],3)[0]
    assert correction.currency=='USD' and correction.unit=='美元' and correction.source=='user'


def test_unit_only_correction_preserves_confirmed_currency_without_invention():
    previous=[{'column':'amount','concept':'revenue','role':'metric','source':'user','dataset_version_id':3,'currency':'USD','unit':'dollar'}]
    item=parse_corrections('amount 单位改为 美分',['amount'],3,previous)[0]
    assert item.currency=='USD' and item.unit=='美分' and item.concept=='revenue'
    inferred=parse_corrections('amount 是销售额，单位是元',['amount'],3)[0]
    assert inferred.currency is None and inferred.unit=='元'


def business_plan(**arguments):
    return AnalysisPlan(task_id='1',goal='calculate',intent='DATA_ANALYSIS',dataset_id=1,dataset_version_id=3,
        steps=[{'step_id':'k','tool_name':'kpi_analysis','arguments':{'metrics':{'revenue':'amount'},**arguments}}],expected_outputs=['k'])


def test_plan_cannot_fabricate_money_unit():
    with pytest.raises(ValueError,match='BUSINESS_METADATA_REQUIRED'):
        PlanValidator().validate(business_plan(currency='USD',unit='dollar'),dataset_id=1,dataset_version_id=3,
            columns={'amount':'decimal'},permissions=frozenset({Permission.READ_DATA}))


def test_plan_trusted_mapping_and_conflict():
    args=dict(dataset_id=1,dataset_version_id=3,columns={'amount':'decimal'},permissions=frozenset({Permission.READ_DATA}),
        semantic_snapshot=[{'column':'amount','concept':'revenue','source':'user','dataset_version_id':3,'currency':'USD','unit':'dollar'}])
    assert PlanValidator().validate(business_plan(currency='USD',unit='dollar'),**args).status=='READY'
    with pytest.raises(ValueError,match='BUSINESS_METADATA_CONFLICT'):
        PlanValidator().validate(business_plan(currency='CNY',unit='dollar'),**args)


def test_serial_join_keeps_exact_business_and_generic_numeric_compatibility():
    left=DatasetTools.from_frame(1,[{'id':1,'amount':Decimal('9007199254740993.01')},{'id':2,'amount':Decimal('0.02')}])
    right=DatasetTools.from_frame(2,[{'id':1,'label':'a'},{'id':2,'label':'b'}])
    left.dataset_version_id=3;right.dataset_version_id=4
    workspace=InputWorkspace({'left':left,'right':right});workspace.deadline=None;workspace.select('left')
    out=workspace.execute('join_data',{'right_alias':'right','left_on':['id'],'right_on':['id'],'how':'left','relationship':'many_to_one'},call_id='j')
    assert out.data['source_versions']=={'left':3,'right':4}
    result=workspace.execute('kpi_analysis',{'metrics':{'revenue':'amount'},'currency':'USD','unit':'dollar'},source_ref='j',call_id='k')
    assert result.data['metrics']['revenue']['value']=='9007199254740993.03'
    assert isinstance(workspace.frame_results['j'].amount.iloc[0],Decimal)
    generic=workspace.execute('descriptive_statistics',{'columns':['amount']},source_ref='j')
    assert generic.data


def test_profiles_new_capabilities_have_new_versions():
    items={p['id']:p for p in profile_catalog()['items']}
    for key,tool in [('sales-decline','contribution_analysis'),('finance-profit','kpi_analysis'),('forecast-sales','forecast'),('general-quality','data_quality_score')]:
        assert items[key]['version']=='2.0'
        assert tool in items[key]['preferred_tools']
        assert items[key]['availability']!='planned'
    assert items['finance-cash-flow']['availability']=='planned'


def test_workspace_discloses_actual_formats():
    from app.routers.workspace import capabilities
    data=capabilities(SimpleNamespace())['data']
    assert 'jsonl' in data['file_formats']
    assert data['document_formats']==['txt','pdf','docx']
    assert data['cross_dataset_join'] is True


def test_known_money_generic_aggregate_cannot_bypass_metadata():
    tools=DatasetTools.from_frame(1,[{'amount':1,'currency':'USD'},{'amount':2,'currency':'EUR'}])
    tools.dataset_version_id=3
    tools.semantic_mappings=[{'column':'amount','concept':'revenue','source':'candidate','dataset_version_id':3}]
    with pytest.raises(ValueError,match='BUSINESS_EXACT_TOOL_REQUIRED'):
        tools.execute('aggregate',{'metrics':[{'column':'amount','aggregation':'sum'}]})
    with pytest.raises(ValueError,match='BUSINESS_EXACT_TOOL_REQUIRED'):
        tools.execute('group_by_analysis',{'group_columns':['currency'],'value_column':'amount'})


def test_user_visible_money_clarification():
    from app.agent.template_router import AnalysisTemplateRouter
    router=AnalysisTemplateRouter(profile_catalog()['items'])
    route=router.route('分析销售额',semantics=[{'column':'amount','concept':'revenue','role':'metric','source':'candidate'}])
    assert route.needs_clarification
    assert any('币种和单位' in text for text in route.missing_requirements)


def test_metadata_columns_are_trusted_and_mixed_override_rejects():
    from app.semantic.business_validation import metadata_evidence,validate_business_arguments
    mappings=[{'column':'amount','concept':'revenue','source':'candidate','dataset_version_id':3}]
    frame=pd.DataFrame({'amount':[1,2],'currency':['USD','USD'],'unit':['dollar','dollar']})
    args={'metrics':{'revenue':'amount'}}
    validate_business_arguments('kpi_analysis',args,mappings,3,metadata_evidence(frame))
    assert args['currency']=='USD' and args['currency_column']=='currency'
    frame.loc[1,'currency']='EUR'
    with pytest.raises(ValueError,match='BUSINESS_METADATA_INVALID'):
        validate_business_arguments('forecast',{'target_column':'amount'},mappings,3,metadata_evidence(frame))


def test_forecast_fields_checked_and_quantity_needs_no_currency():
    kwargs=dict(dataset_id=1,dataset_version_id=3,columns={'date':'datetime','quantity':'integer'},permissions=frozenset({Permission.READ_DATA}))
    plan=business_plan()
    plan.steps[0].tool_name='forecast';plan.steps[0].arguments={'time_column':'missing','target_column':'quantity','horizon':3,'granularity':'month','aggregation':'sum'}
    with pytest.raises(ValueError,match='COLUMN_NOT_FOUND'): PlanValidator().validate(plan,**kwargs)
    plan.steps[0].arguments['time_column']='date'
    assert PlanValidator().validate(plan,**kwargs).status=='READY'


def test_derived_preview_budget_preserved(analysis_context,monkeypatch):
    from app.config import get_settings
    client,_,_=analysis_context
    monkeypatch.setattr(get_settings(),'tool_preview_rows',1)
    dataset=client.post('/api/v1/datasets/upload',files={'file':('a.csv',b'x,label\n1,a\n2,b\n3,c\n','text/csv')}).json()['data']['id']
    version=client.get(f'/api/v1/datasets/{dataset}').json()['data']['current_version_id']
    data=client.post(f'/api/v1/datasets/{dataset}/transformations/preview',json={'dataset_version_id':version,'operations':[{'tool':'normalize_text','parameters':{'columns':['label'],'text_operations':['strip']}}]}).json()['data']
    assert len(data['before']['sample'])==len(data['after']['sample'])==1


from test_analysis_api import analysis_context


def test_persisted_fixed_exact_amount_survives_structural_publication(analysis_context,monkeypatch):
    from app.models import Dataset,DatasetVersion
    from app.services.datasets import write_projection,profile_frame
    from app.services.tool_execution import context_for
    from app.config import get_settings
    from app.datasets.profiler import build_profile
    from sqlalchemy import create_engine
    client,sessions,folder=analysis_context
    monkeypatch.setattr(get_settings(),'artifact_dir',str(folder/'artifacts'))
    dataset_id=client.post('/api/v1/datasets/upload',files={'file':('a.csv',b'amount,label\n1,a\n2,b\n','text/csv')}).json()['data']['id']
    frame=pd.DataFrame({'amount':[Decimal('9007199254740993.01234567891'),Decimal('0.2')],'tiny':[Decimal('0.1'),Decimal('0.2')],'label':[' a ',' a ']})
    with sessions() as db:
        dataset=db.get(Dataset,dataset_id);version=db.get(DatasetVersion,dataset.current_version_id)
        name=f'dataset_{dataset_id}_v_'+('a'*32)
        write_projection(frame,dataset_id,db.get_bind(),name)
        schema,profile=build_profile(frame)
        version.projection_table=name;version.schema_json=schema.model_dump();version.profile_json=profile.model_dump();db.commit()
        source_version=version.id
        exact=DatasetService(db,db.get_bind()).load_frame(dataset,[],source_version,preserve_decimal=True)
        assert exact.amount.tolist()==frame.amount.tolist()
        from app.analysis.catalog import build_registry
        from app.analysis.context import DatasetContext
        result=build_registry().calculate('kpi_analysis',DatasetContext.from_frame(exact,dataset_id,source_version),{'metrics':{'revenue':'amount','cost':'tiny'},'currency':'USD','unit':'dollar'})
        assert result.data.metrics['revenue'].value=='9007199254740993.21234567891'
        assert result.data.metrics['cost'].value=='0.3'
        assert pd.api.types.is_numeric_dtype(DatasetService(db,db.get_bind()).load_frame(dataset,[],source_version).amount)
    body={'dataset_version_id':source_version,'operations':[{'tool':'normalize_text','parameters':{'columns':['label'],'text_operations':['strip']}},{'tool':'rename_columns','parameters':{'columns':['label'],'names':{'label':'text'}}},{'tool':'remove_duplicates','parameters':{'columns':['text'],'keep':'first'}}]}
    preview=client.post(f'/api/v1/datasets/{dataset_id}/transformations/preview',json=body)
    assert preview.status_code==200,preview.text
    response=client.post(f'/api/v1/datasets/{dataset_id}/transformations',json={**body,'confirmed':True,'preview_hash':preview.json()['data']['preview_hash'],'request_id':'exact-clean'})
    assert response.status_code==202,response.text
    result=client.get(f"/api/v1/datasets/{dataset_id}/transformations/{response.json()['data']['execution_id']}").json()['data']
    assert result['status']=='succeeded',result
    with sessions() as db:
        dataset=db.get(Dataset,dataset_id)
        output=DatasetService(db,db.get_bind()).load_frame(dataset,[],dataset.current_version_id,preserve_decimal=True)
        assert output.amount.tolist()==frame.amount.tolist()[:1]
    old=client.get(f'/api/v1/datasets/{dataset_id}/preview?dataset_version_id={source_version}').json()['data']
    assert old['columns']==['amount','tiny','label'] and old['total_rows']==2
    assert old['rows'][0]['amount']=='9007199254740993.01234567891'
    new=client.get(f'/api/v1/datasets/{dataset_id}/preview?dataset_version_id={result["output_version"]["id"]}').json()['data']
    assert new['columns']==['amount','tiny','text'] and new['total_rows']==1
    other=client.post('/api/v1/datasets/upload',files={'file':('b.csv',b'id\n1\n','text/csv')}).json()['data']['id']
    assert client.get(f'/api/v1/datasets/{other}/preview?dataset_version_id={source_version}').status_code in {403,409}


def test_fake_plan3_sales_decline_finance_forecast_and_current_date():
    from app.agent.providers import FakeLLMProvider
    from app.agent.planner import Planner
    from app.agent.context import ConversationContext
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app.agent.schemas import AnalysisPlanV3
    class Captured(FakeLLMProvider):
        def generate_structured(self,name,payload,schema):
            self.payload=payload
            return super().generate_structured(name,payload,schema)
    binding={'alias':'primary','dataset_id':1,'dataset_version_id':3}
    mapping={'column':'amount','concept':'revenue','role':'metric','source':'user','dataset_version_id':3,'currency':'USD','unit':'dollar'}
    config={'inputs':[binding],'profiles':[next(p for p in profile_catalog()['items'] if p['id']=='sales-decline')],'semantic_snapshot':[mapping],'semantic_version':1,'depth':'STANDARD'}
    kwargs=dict(task_id='1',intent='DATA_ANALYSIS',config=config,permissions=frozenset({Permission.READ_DATA}))
    year=datetime.now(ZoneInfo('Asia/Shanghai')).year
    args={'date_column':'date','value_column':'amount','dimension':'region','granularity':'year','start':f'{year}-01-01','end':f'{year+1}-01-01','comparison':'yoy','currency':'USD','unit':'dollar'}
    plan=dict(version='3.0',task_id='1',goal='decline',intent='DATA_ANALYSIS',dataset_id=1,dataset_version_id=3,inputs=[binding],steps=[{'step_id':'c','tool_name':'contribution_analysis','arguments':args}],expected_outputs=['c'])
    provider=Captured([plan]);planner=Planner(provider)
    meta={'primary':{'columns':[{'name':n,'data_type':t} for n,t in [('date','datetime'),('amount','decimal'),('region','string')]]}}
    checked=planner.plan_v3('今年销售额下降的地区贡献',meta,ConversationContext(conversation_id=1,user_id=1),**kwargs)
    assert checked.steps[0].arguments['start']==f'{year}-01-01'
    assert provider.payload['current_date']==datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
    assert {'kpi_analysis','period_comparison','contribution_analysis'}<={tool['name'] for tool in provider.payload['tools']}
    forecast=dict(plan,steps=[{'step_id':'f','tool_name':'forecast','arguments':{'time_column':'date','target_column':'amount','horizon':3,'granularity':'month','aggregation':'sum'}}],expected_outputs=['f'])
    result=Planner(Captured([forecast])).plan_v3('未来三个月',meta,ConversationContext(conversation_id=1,user_id=1),**kwargs)
    tools=DatasetTools.from_frame(1,[{'date':date.isoformat(),'amount':Decimal(str(10+i))} for i,date in enumerate(pd.date_range('2024-01-01',periods=24,freq='MS'))])
    tools.dataset_version_id=3;tools.semantic_mappings=[mapping]
    out=tools.execute('forecast',result.steps[0].arguments)
    assert len(out.data['points'])==3 and out.data['unit_status']=='verified' and out.data['currency']=='USD'


def test_plan_join_authorized_alias_and_source_schema():
    from app.agent.task_graph import validate_graph
    from app.agent.schemas import AnalysisPlanV3
    plan=AnalysisPlanV3(task_id='1',goal='join',intent='DATA_ANALYSIS',dataset_id=1,dataset_version_id=3,
        inputs=[{'alias':'primary','dataset_id':1,'dataset_version_id':3},{'alias':'r','dataset_id':2,'dataset_version_id':4}],
        steps=[{'step_id':'j','tool_name':'join_data','arguments':{'right_alias':'r','left_on':['id'],'right_on':['key'],'how':'left','relationship':'many_to_one'}},
            {'step_id':'a','tool_name':'aggregate','source_ref':'j','depends_on':['j'],'arguments':{'metrics':[{'column':'count','aggregation':'sum'}]}}],expected_outputs=['a'])
    columns={'primary':{'id':'integer'},'r':{'key':'integer','count':'integer'}}
    assert validate_graph(plan,columns).status=='READY'
    plan.steps[1].arguments['metrics'][0]['column']='unknown'
    with pytest.raises(ValueError,match='COLUMN_NOT_FOUND'):validate_graph(plan,columns)
    plan.steps.pop();plan.expected_outputs=['j'];plan.steps[0].arguments['right_alias']='unowned'
    with pytest.raises(ValueError,match='JOIN_INPUT_UNAVAILABLE'):validate_graph(plan,columns)


def test_profile_v1_snapshot_remains_immutable(analysis_context):
    from app.models import AnalysisProfileRecord
    from app.profiles.service import ProfileService
    from datetime import datetime,UTC
    from sqlalchemy import select
    _,sessions,_=analysis_context
    with sessions() as db:
        original={'id':'sales-decline','version':'1.0','marker':'immutable original'}
        db.add(AnalysisProfileRecord(profile_id='sales-decline',version='1.0',definition_json=original,created_at=datetime.now(UTC)));db.flush()
        ProfileService(db).seed()
        versions=db.scalars(select(AnalysisProfileRecord).where(AnalysisProfileRecord.profile_id=='sales-decline')).all()
        assert {r.version for r in versions}=={'1.0','2.0'}
        assert next(r for r in versions if r.version=='1.0').definition_json==original


def test_verified_forecast_aggregates_exact_before_model_normalization():
    from dataclasses import replace
    from app.analysis.context import DatasetContext
    from app.analysis.inputs import ForecastInput
    from app.analysis.forecast_tools import _history
    frame=pd.DataFrame([{'date':date,'amount':amount} for date in pd.date_range('2024-01-01',periods=12,freq='MS') for amount in [Decimal('9007199254740993.01'),Decimal('-9007199254740992'),Decimal('0.02')]])
    context=DatasetContext.from_frame(frame,monetary_metadata={'currency':'USD','unit':'dollar'})
    values=_history(context,ForecastInput(time_column='date',target_column='amount',horizon=3,granularity='month',aggregation='sum'))
    assert values.tolist()==[1.03]*12


def test_statistical_cleaning_normalizes_only_selected_column_and_declares_it():
    from app.analysis.catalog import build_registry
    from app.analysis.context import DatasetContext
    frame=pd.DataFrame({'x':[Decimal('1'),None,Decimal('3')],'amount':[Decimal('9007199254740993.01234567891')]*3})
    out=build_registry().calculate('fill_missing_values',DatasetContext.from_frame(frame),{'columns':['x'],'strategy':'mean'},frozenset({Permission.READ_DATA,Permission.TRANSFORM_DATA}))
    assert out.frame.x.tolist()==[1,2,3]
    assert out.frame.amount.tolist()==frame.amount.tolist()
    assert any(w.code=='APPROXIMATE_NUMERIC_TRANSFORMATION' for w in out.warnings)


def test_schema_compaction_preserves_title_properties_and_arbitrary_defaults():
    from app.agent.planner import compact_tool_schema
    schema={'title':'Annotation','type':'object','required':['title','examples'],'properties':{'title':{'title':'Title annotation','type':'string','default':{'title':'value','examples':[1]},'maxLength':99},'examples':{'type':'array','items':{'type':'integer','minimum':1}}},'$defs':{'title':{'type':'string','title':'Annotation'}},'examples':[{'title':'example'}]}
    compact=compact_tool_schema(schema)
    assert 'title' not in compact and 'examples' not in compact
    assert set(compact['properties'])=={'title','examples'}
    assert compact['properties']['title']['default']=={'title':'value','examples':[1]}
    assert compact['properties']['title']['maxLength']==99 and compact['required']==schema['required']
    assert compact['$defs']['title']=={'type':'string'}


def test_nested_business_result_reaches_final_evidence_table_exactly():
    from app.analysis.result_tables import result_table
    data={'kind':'kpi','metrics':{'revenue':{'value':'9007199254740993.03','status':'valid','explanation':None}},'currency':'USD','unit':'dollar','limitations':['exact stored values']}
    table=result_table(data,'k')
    assert table['rows']==[{'metric':'revenue','value':'9007199254740993.03','status':'valid','explanation':None}]
    assert table['source_ref']=='k' and table['currency']=='USD'


@pytest.mark.parametrize('label,values',[('currency',['USD','EUR']),('unit',['dollar','cent'])])
def test_join_cannot_hide_mixed_monetary_metadata(label,values):
    left=DatasetTools.from_frame(1,[{'id':i,'amount':Decimal(str(10+i*10)),'currency':values[i] if label=='currency' else 'USD','unit':values[i] if label=='unit' else 'dollar'} for i in range(2)])
    right=DatasetTools.from_frame(2,[{'id':i,'currency':'USD','unit':'dollar'} for i in range(2)])
    left.dataset_version_id=3;right.dataset_version_id=4
    left.semantic_mappings=[{'column':'amount','concept':'revenue','source':'user','dataset_version_id':3,'currency':'USD','unit':'dollar'}];right.semantic_mappings=[]
    workspace=InputWorkspace({'left':left,'right':right});workspace.deadline=None;workspace.select('left')
    with pytest.raises(ValueError,match='BUSINESS_METADATA_INVALID'):
        workspace.execute('kpi_analysis',{'metrics':{'revenue':'amount'},'currency':'USD','unit':'dollar'})
    workspace.execute('join_data',{'right_alias':'right','left_on':['id'],'right_on':['id'],'how':'left','relationship':'many_to_one'},call_id='j')
    with pytest.raises(ValueError,match='BUSINESS_METADATA_INVALID'):
        workspace.execute('kpi_analysis',{'metrics':{'revenue':'amount'},'currency':'USD','unit':'dollar'},source_ref='j')


def test_join_homogeneous_metadata_remains_verified():
    from app.semantic.business_validation import metadata_evidence
    data=pd.DataFrame({'currency_left':['USD','USD'],'currency_right':['USD','USD'],'unit_left':['dollar','dollar'],'unit_right':['dollar','dollar']})
    evidence=metadata_evidence(data)
    assert evidence['currency']['status']=='valid' and evidence['unit']['value']=='dollar'
    original=pd.DataFrame({'c_left':['USD'],'c_right':['USD'],'u_left':['dollar'],'u_right':['dollar']})
    original.attrs['original_columns']=['币种_left','currency_right','单位_left','unit_right']
    assert metadata_evidence(original)['currency']['value']=='USD'


@pytest.mark.parametrize('keys',[['id'],['id','currency']])
def test_join_homogeneous_money_executes_with_suffixed_or_shared_metadata(keys):
    left=DatasetTools.from_frame(1,[{'id':i,'amount':Decimal(str(10+i*10)),'currency':'USD','unit':'dollar'} for i in range(2)])
    right=DatasetTools.from_frame(2,[{'id':i,'currency':'USD','unit':'dollar'} for i in range(2)])
    left.dataset_version_id=3;right.dataset_version_id=4
    left.semantic_mappings=[{'column':'amount','concept':'revenue','source':'user','dataset_version_id':3,'currency':'USD','unit':'dollar'}];right.semantic_mappings=[]
    workspace=InputWorkspace({'left':left,'right':right});workspace.deadline=None;workspace.select('left')
    workspace.execute('join_data',{'right_alias':'right','left_on':keys,'right_on':keys,'how':'left','relationship':'many_to_one'},call_id='j')
    out=workspace.execute('kpi_analysis',{'metrics':{'revenue':'amount'}},source_ref='j')
    assert out.data['metrics']['revenue']['value']=='30' and out.data['currency']=='USD'


def test_parallel_copies_combined_budget_rejected_before_second_allocation(monkeypatch):
    from app.agent.graph_executor import GraphExecutor
    from app.agent.budget import RuntimeBudget
    from app.agent.schemas import AnalysisStep
    from app.config import get_settings
    tools=DatasetTools.from_frame(1,[{'x':'a'*200}]*10);workspace=InputWorkspace({'primary':tools})
    size=int(tools.frame.memory_usage(deep=True).sum());monkeypatch.setattr(get_settings(),'dataframe_max_bytes',size*2+size//2)
    runner=GraphExecutor(workspace,SimpleNamespace(max_tool_attempts=5,analysis_timeout_seconds=30),budget=RuntimeBudget.for_depth('STANDARD'))
    first=runner._source_context(AnalysisStep(step_id='a',tool_name='dataset_overview'))
    with pytest.raises(ValueError,match='WORKSPACE_MEMORY_BUDGET'):
        runner._source_context(AnalysisStep(step_id='b',tool_name='column_summary'))


from test_datasets_api import dataset_context


def test_ready_file_detail_retains_positional_preview_compatibility(dataset_context,monkeypatch):
    from app.main import app
    monkeypatch.setattr(app.state,'task_supervisor',None,raising=False)
    client,_,_=dataset_context
    upload=client.post('/api/v1/files/upload',files={'file':('a.jsonl',b'{"x":1}\n{"x":2}\n','application/x-ndjson')})
    assert upload.status_code==202,upload.text
    info=client.get(f"/api/v1/datasets/{upload.json()['data']['dataset']['id']}").json()['data']
    assert info['row_count']==2,info
    detail=client.get(f"/api/v1/files/{upload.json()['data']['file']['id']}")
    assert detail.status_code==200,detail.text
    assert detail.json()['data']['table_preview']['rows']==[{'x':1},{'x':2}]


def test_parallel_budget_counts_roots_exact_cache_contexts_and_results(monkeypatch):
    from app.agent.graph_executor import GraphExecutor
    from app.agent.budget import RuntimeBudget
    from app.agent.schemas import AnalysisStep
    from app.analysis.context import DatasetContext
    from app.config import get_settings
    tools=DatasetTools.from_frame(1,[{'x':'a'*200}]*10);right=DatasetTools.from_frame(2,[{'y':'b'*200}]*10)
    workspace=InputWorkspace({'primary':tools,'right':right})
    tools._exact_frame=tools.frame.copy();tools._contexts={'cache':DatasetContext.from_frame(tools.frame.copy())}
    workspace.frame_results['old']=tools.frame.copy();workspace.deadline=None;workspace.select('primary')
    size=int(tools.frame.memory_usage(deep=True).sum());monkeypatch.setattr(get_settings(),'dataframe_max_bytes',size*5+size//2)
    runner=GraphExecutor(workspace,SimpleNamespace(max_tool_attempts=5,analysis_timeout_seconds=30),budget=RuntimeBudget.for_depth('STANDARD'))
    with pytest.raises(ValueError,match='WORKSPACE_MEMORY_BUDGET'):runner._source_context(AnalysisStep(step_id='a',tool_name='dataset_overview'))


def test_parallel_result_retention_counts_live_contexts_before_copy(monkeypatch):
    from dataclasses import replace
    from app.agent.graph_executor import GraphExecutor
    from app.agent.budget import RuntimeBudget
    from app.agent.schemas import AnalysisStep,AnalysisPlanV3
    from app.analysis.catalog import build_registry
    from app.analysis.registry import FunctionTool
    from app.config import get_settings
    tools=DatasetTools.from_frame(1,[{'x':'a'*200}]*10);tools.dataset_version_id=3
    registry=build_registry(True);tool=registry.get('filter_rows')
    registry._tools['filter_rows']=FunctionTool(replace(tool.metadata,parallel_safe=True),tool.input_schema,tool.output_schema,tool.calculate)
    tools._registry=registry;workspace=InputWorkspace({'primary':tools})
    size=int(tools.frame.memory_usage(deep=True).sum());monkeypatch.setattr(get_settings(),'dataframe_max_bytes',size*4+size//2)
    steps=[AnalysisStep(step_id='f',tool_name='filter_rows',status='READY'),AnalysisStep(step_id='a',tool_name='dataset_overview',status='READY')]
    runner=GraphExecutor(workspace,SimpleNamespace(max_tool_attempts=5,analysis_timeout_seconds=30),budget=RuntimeBudget.for_depth('STANDARD'))
    runner.final_plan=AnalysisPlanV3(task_id='1',goal='budget',intent='DATA_ANALYSIS',dataset_id=1,dataset_version_id=3,inputs=[{'alias':'primary','dataset_id':1,'dataset_version_id':3}],steps=steps)
    runner._run_parallel(steps)
    assert steps[0].status=='FAILED' and 'f' not in workspace.frame_results
    assert steps[1].status=='COMPLETED'


def test_parallel_timeout_reservations_survive_batches_and_release_on_completion(monkeypatch):
    import threading
    from dataclasses import replace
    from app.agent.graph_executor import GraphExecutor
    from app.agent.budget import RuntimeBudget
    from app.agent.schemas import AnalysisStep,AnalysisPlanV3
    from app.analysis.catalog import build_registry
    from app.analysis.registry import FunctionTool
    from app.config import get_settings
    tools=DatasetTools.from_frame(1,[{'x':'a'*200}]*10);tools.dataset_version_id=3
    registry=build_registry(True);release=threading.Event();completed=[];started=[]
    for name in ['dataset_overview','column_summary']:
        original=registry.get(name)
        def blocked(context,args,original=original):
            started.append(id(context.frame))
            release.wait(5)
            try:return original.execute(context,args)
            finally:completed.append(id(context.frame))
        registry._tools[name]=FunctionTool(replace(original.metadata,timeout_seconds=.01),original.input_schema,original.output_schema,blocked)
    tools._registry=registry;workspace=InputWorkspace({'primary':tools})
    size=int(tools.frame.memory_usage(deep=True).sum());monkeypatch.setattr(get_settings(),'dataframe_max_bytes',size*5+size//2)
    runner=GraphExecutor(workspace,SimpleNamespace(max_tool_attempts=20,analysis_timeout_seconds=30),budget=RuntimeBudget.for_depth('STANDARD'))
    def batch(index):
        steps=[AnalysisStep(step_id=f'a{index}',tool_name='dataset_overview',status='READY'),AnalysisStep(step_id=f'b{index}',tool_name='column_summary',status='READY')]
        runner.final_plan=AnalysisPlanV3(task_id='1',goal='budget',intent='DATA_ANALYSIS',dataset_id=1,dataset_version_id=3,inputs=[{'alias':'primary','dataset_id':1,'dataset_version_id':3}],steps=steps)
        runner._run_parallel(steps)
    try:
        batch(1);batch(2)
        assert len(started)==4 and len(runner.pending_frames)==4
        with pytest.raises(ValueError,match='WORKSPACE_MEMORY_BUDGET'):batch(3)
        assert len(started)==4 and len(runner.pending_frames)==4
    finally:
        release.set()
    for future in list(runner.pending_workers):future.result(timeout=3)
    batch(4)
    assert len(completed)==6 and not runner.pending_frames and not runner.pending_workers
