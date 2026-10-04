import importlib.util
from types import SimpleNamespace
import pytest


def agent_api():
    assert importlib.util.find_spec('app.sandbox.agent'), 'Internal sandbox agent seam is missing'
    from app.sandbox.agent import propose_plan, execute_sandbox, UnknownToolCapability
    return propose_plan, execute_sandbox, UnknownToolCapability


def config():
    return {'inputs':[{'alias':'primary','dataset_id':1,'dataset_version_id':2}], 'profiles':[],
        'depth':'STANDARD','semantic_snapshot':[],'semantic_version':0}


def test_disabled_sandbox_does_not_call_model(monkeypatch):
    propose, _, Unknown = agent_api()
    from app.sandbox.settings import SandboxSettings
    monkeypatch.setattr('app.sandbox.agent.get_sandbox_settings',lambda:SandboxSettings(enabled=False))
    provider=SimpleNamespace(generate_structured=lambda *a:pytest.fail('Disabled sandbox called model'))
    from app.sandbox.validator import SandboxError
    with pytest.raises(SandboxError,match='SANDBOX_DISABLED'):
        propose('question',provider,config(),{},'1','DATA_ANALYSIS',Unknown(['custom_gini']))


def test_registered_capability_never_enters_code_fallback(monkeypatch):
    propose, _, Unknown = agent_api()
    from app.sandbox.validator import SandboxError
    with pytest.raises(SandboxError,match='SANDBOX_FALLBACK_DENIED'):
        propose('sum',None,config(),{},'1','DATA_ANALYSIS',Unknown(['aggregate']))
    with pytest.raises(SandboxError,match='SANDBOX_FALLBACK_DENIED'):
        propose('clean',None,config(),{},'1','DATA_CLEANING',Unknown(['custom_clean']))


def test_sealed_proposal_uses_only_fixed_input_and_tamper_is_denied(monkeypatch):
    propose, execute, Unknown = agent_api()
    from app.sandbox.settings import SandboxSettings
    from app.sandbox.validator import SandboxError
    from app.agent.graph_executor import InputWorkspace
    from app.services.analysis_tools import DatasetTools
    from app.agent.providers import FakeLLMProvider
    from app.agent.budget import BudgetProvider, RuntimeBudget
    snapshots=[]
    class Client:
        def __init__(self,*args): pass
        def health(self): return True
        def run(self,request,**kwargs):
            snapshots.extend(request['inputs'])
            return {'result':{'columns':['gini'],'rows':[{'gini':0.25}]},'images':[]}
    monkeypatch.setattr('app.sandbox.agent.SandboxClient',Client)
    monkeypatch.setattr('app.sandbox.agent.get_sandbox_settings',lambda:SandboxSettings(enabled=True,broker_token='t'*32))
    provider=BudgetProvider(FakeLLMProvider([{'missing_capability':'custom_gini','reason':'Catalog has no Gini calculation',
        'input_alias':'primary','code':'result = {"gini": 0.25}'}]),RuntimeBudget.for_depth('STANDARD'))
    plan, seal=propose('gini',provider,config(),{},'1','DATA_ANALYSIS',Unknown(['custom_gini']))
    adapter=DatasetTools.from_frame(1,[{'x':1},{'x':3}]); adapter.dataset_version_id=2
    workspace=InputWorkspace({'primary':adapter}); workspace.configuration=config(); workspace.deadline=provider.budget.deadline
    workspace.sandbox_authorization=seal
    workspace.sandbox_owner='a'*64
    step=plan.steps[0]
    output=execute(workspace,step.arguments,step.step_id)
    assert output.data['rows']==[{'gini':0.25}]
    assert snapshots[0]['dataset_version_id']==2 and snapshots[0]['rows']==[{'x':1},{'x':3}]
    assert set(snapshots[0]) <= {'alias','dataset_id','dataset_version_id','columns','rows','dtypes'}
    with pytest.raises(SandboxError,match='SANDBOX_PROPOSAL_MISMATCH'):
        execute(workspace,dict(step.arguments,code='result = {"gini": 999}'),step.step_id)


def test_python_export_of_sandbox_plan_reuses_broker_without_host_exec():
    import ast
    from app.reports.code_exporter import export_plan
    plan={'dataset_id':1,'dataset_version_id':2,'inputs':config()['inputs'],
        'steps':[{'step_id':'sandbox','tool_name':'python_sandbox','status':'COMPLETED',
                  'input_alias':'primary','arguments':{'code':'result = {"gini": 0.25}','input_alias':'primary',
                    'missing_capability':'custom_gini','reason':'no registered gini method'}}]}
    files=export_plan(plan,'python','自定义分析',config()['inputs'])
    script=files[0].content.decode()
    ast.parse(script)
    assert 'SandboxClient' in script and 'exec(' not in script
