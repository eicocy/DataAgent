from sqlalchemy import select
from test_analysis_api import analysis_context


def test_registered_planner_fallback_persists_fixed_evidence_and_image(analysis_context, monkeypatch, tmp_path):
    import io,base64
    from PIL import Image
    from app.config import get_settings
    from app.sandbox.settings import SandboxSettings
    from app.agent.providers import FakeLLMProvider
    from app.services.analysis_agent import DeepSeekAgent
    from app.services.analysis import execute_record
    from app.models import Dataset,AnalysisRecord,AnalysisArtifact
    client,sessions,_=analysis_context
    monkeypatch.setattr(get_settings(),'artifact_dir',str(tmp_path/'artifacts'))
    monkeypatch.setattr('app.sandbox.settings.get_sandbox_settings',lambda:SandboxSettings(enabled=True,broker_token='test-token-'+'x'*32))
    monkeypatch.setattr('app.sandbox.agent.get_sandbox_settings',lambda:SandboxSettings(enabled=True,broker_token='test-token-'+'x'*32))
    snapshots=[]
    image=io.BytesIO(); Image.new('RGB',(20,10),'white').save(image,format='PNG')
    class FixedBroker:
        def __init__(self,*args): pass
        def health(self): return True
        def run(self,request,**kwargs):
            kwargs['check_lease']()
            snapshots.extend(request['inputs'])
            return {'result':{'gini':0.25},'images':[base64.b64encode(image.getvalue()).decode()]}
    monkeypatch.setattr('app.sandbox.agent.SandboxClient',FixedBroker)
    did=client.post('/api/v1/datasets/upload',files={'file':('sample.csv',b'x\n1\n3\n','text/csv')}).json()['data']['id']
    sid=client.post('/api/v1/analysis/sessions',json={'dataset_id':did}).json()['data']['id']
    rid=client.post('/api/v1/analysis/runs',json={'session_id':sid,'dataset_id':did,'question':'计算 Gini 系数','request_id':'phase5-fixed',
        'depth':'STANDARD','profile_ids':['general-quality']}).json()['data']['record_id']
    with sessions() as db:
        vid=db.get(Dataset,did).current_version_id
        unsupported={'task_id':str(rid),'goal':'Gini','intent':'DATA_ANALYSIS','dataset_id':did,'dataset_version_id':vid,
            'inputs':[{'alias':'primary','dataset_id':did,'dataset_version_id':vid}],'steps':[],'unsupported_capabilities':['custom_gini']}
        class CapturedProvider(FakeLLMProvider):
            def generate_structured(self,name,payload,schema):
                if name=='result_interpreter':
                    assert 'rows' not in payload['results']['sandbox']
                return super().generate_structured(name,payload,schema)
        provider=CapturedProvider([{'intent':'DATA_ANALYSIS','confidence':.99,'requires_dataset':True,'requires_analysis':True},
            unsupported,unsupported,{'missing_capability':'custom_gini','reason':'No registered Gini method','input_alias':'primary',
                'code':'result={"gini":0.25}'},
            {'template':'模拟样例 Gini 系数为 {gini}。','facts':[{'key':'gini','step_id':'sandbox','path':['rows',0,'gini']}],'evidence_refs':['sandbox']}])
        execute_record(db,rid,DeepSeekAgent(provider_factory=lambda emit:provider),db.get_bind(),db.get_bind())
        row=db.get(AnalysisRecord,rid)
        assert row.status=='succeeded',(row.status,row.error_code,row.error_message)
        assert row.tool_result_json['rows']==[{'gini':0.25}]
        assert row.report_json['findings'][0]['kind']=='bound_fact'
        assert any('自定义代码' in w for w in row.report_json['warnings'])
        artifacts=db.scalars(select(AnalysisArtifact).where(AnalysisArtifact.record_id==rid)).all()
        assert {a.kind for a in artifacts}=={'image','table'}
        image_id=next(a.id for a in artifacts if a.kind=='image')
    assert snapshots[0]['dataset_version_id']==vid and snapshots[0]['rows']==[{'x':1},{'x':3}]
    workspace=client.get(f'/api/v1/analysis/sessions/{sid}/workspace').json()['data']
    assert workspace['latest_analysis']['record_id']==rid
    assert client.get(f'/api/v1/artifacts/{image_id}/download').content.startswith(b'\x89PNG')
