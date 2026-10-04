"""Internal fallback after the registered tool planner cannot cover a capability."""
from dataclasses import dataclass
import hashlib
import json
import re
from pydantic import BaseModel, ConfigDict, Field
from app.sandbox.client import SandboxClient
from app.sandbox.settings import get_sandbox_settings
from app.sandbox.validator import validate_code, SandboxError
from app.sandbox.results import validate_output


class UnknownToolCapability(ValueError):
    def __init__(self, names):
        self.names = sorted(set(names))
        super().__init__('REGISTERED_TOOLS_INSUFFICIENT')


class CodeProposal(BaseModel):
    model_config = ConfigDict(extra='forbid')
    missing_capability: str = Field(min_length=1,max_length=64)
    reason: str = Field(min_length=1,max_length=500)
    input_alias: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,31}$')
    code: str = Field(min_length=1,max_length=32768)


@dataclass(frozen=True)
class Authorization:
    code_hash: str
    input_alias: str
    inputs_json: str
    step_id: str = 'sandbox'


def propose_plan(question,provider,config,metadata,task_id,intent,unmet):
    from app.analysis.catalog import build_registry
    from app.agent.schemas import AnalysisPlanV3, AnalysisStep
    names = {tool.metadata.name for tool in build_registry(include_legacy=True).list_tools()}
    if intent not in {'DATA_ANALYSIS','FOLLOW_UP_ANALYSIS'} or not unmet.names or any(name in names or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}',name) for name in unmet.names):
        raise SandboxError('SANDBOX_FALLBACK_DENIED')
    settings=get_sandbox_settings()
    if not settings.enabled: raise SandboxError('SANDBOX_DISABLED')
    SandboxClient(settings).health()
    # No sample rows, filenames, database locations or credentials are sent.
    proposal=CodeProposal.model_validate(provider.generate_structured('sandbox_planner',
        {'question':question[:2000],'unsupported_capabilities':unmet.names,'registered_tools':sorted(names),
         'inputs':config['inputs'],'datasets':{alias:{'columns':value.get('columns',[]),'row_count':value.get('row_count')} for alias,value in metadata.items()}},CodeProposal))
    if proposal.missing_capability not in unmet.names or proposal.input_alias not in {i['alias'] for i in config['inputs']}:
        raise SandboxError('SANDBOX_PROPOSAL_MISMATCH')
    validate_code(proposal.code)
    seal=Authorization(hashlib.sha256(proposal.code.encode()).hexdigest(),proposal.input_alias,
        json.dumps(config['inputs'],sort_keys=True))
    step=AnalysisStep(step_id=seal.step_id,tool_name='python_sandbox',name='受限自定义分析',
        input_alias=proposal.input_alias,arguments=proposal.model_dump())
    primary=config['inputs'][0]
    plan=AnalysisPlanV3(task_id=task_id,goal=question[:500],intent=intent,
        dataset_id=primary['dataset_id'],dataset_version_id=primary['dataset_version_id'],inputs=config['inputs'],
        steps=[step],expected_outputs=[seal.step_id],profiles=config['profiles'],
        semantic_snapshot=config['semantic_snapshot'],semantic_version=config['semantic_version'],depth=config['depth'],
        budget=provider.budget.snapshot(),status='READY',warnings=['自定义代码分析，需核对方法与适用前提。'])
    return plan,seal


def execute_sandbox(workspace,arguments,call_id):
    from app.tools.schemas import ToolResult
    from app.analysis.serialization import records
    from app.execution.validators import ResultWarning
    from app.analysis.engine import AnalysisEngine, ExecutionContext
    from app.analysis.registry import FunctionTool, ToolMetadata, ToolOutput, ToolRegistry
    from app.analysis.models import ToolCategory, TableResult, ToolExecutionRequest
    from app.analysis.context import DatasetContext
    seal=getattr(workspace,'sandbox_authorization',None)
    proposal=CodeProposal.model_validate(arguments)
    if not isinstance(seal,Authorization) or call_id!=seal.step_id or proposal.input_alias!=seal.input_alias or hashlib.sha256(proposal.code.encode()).hexdigest()!=seal.code_hash or json.dumps(workspace.configuration['inputs'],sort_keys=True)!=seal.inputs_json:
        raise SandboxError('SANDBOX_PROPOSAL_MISMATCH')
    binding=next(i for i in workspace.configuration['inputs'] if i['alias']==seal.input_alias)
    adapter=workspace.inputs[seal.input_alias]
    if adapter.dataset.id != binding['dataset_id'] or adapter.dataset_version_id != binding['dataset_version_id']:
        raise SandboxError('SANDBOX_INPUT_VERSION_MISMATCH')
    # The owned loader preserves stored Decimal values. Never load an upload
    # directory or permit the model to select a path/connection.
    frame=adapter.frame_for('kpi_analysis')
    dtypes={c.name:c.data_type for c in adapter.columns if c.data_type in {'integer','decimal','float','boolean','string','datetime','date'}}
    snapshot=dict(binding,columns=list(frame.columns),rows=records(frame),dtypes=dtypes)
    images=[]
    if getattr(workspace,'on_event',None): workspace.on_event('stage',{'stage':'tool','timeout_seconds':60})
    def calculate(context,parameters):
        output=SandboxClient().run(dict(code=parameters.code,owner=workspace.sandbox_owner,inputs=[snapshot]),
            check_lease=getattr(workspace,'sandbox_lease_check',getattr(workspace,'check_lease',None)),deadline=workspace.deadline)
        table, output_frame, pngs=validate_output(output['result'],output['images'])
        images.extend(pngs)
        return ToolOutput(table,output_frame,[ResultWarning(code='CUSTOM_CODE_METHOD',message='结果来自受限自定义代码，请核对分析方法与适用前提。')])
    # Private per-execution registry: never added to the public tool catalog.
    registry=ToolRegistry()
    registry.register(FunctionTool(ToolMetadata(name='python_sandbox',description='Internal container analysis',
        category=ToolCategory.DATA,capabilities=('custom_code',),timeout_seconds=60,chat_enabled=False,
        exposes_rows=True,provides_frame=True),CodeProposal,TableResult,calculate))
    captured=[]
    context=DatasetContext.from_frame(frame,binding['dataset_id'],binding['dataset_version_id'])
    output=AnalysisEngine(registry).execute(ToolExecutionRequest(tool_name='python_sandbox',dataset_id=binding['dataset_id'],
        dataset_version=binding['dataset_version_id'],parameters=arguments,request_id=call_id),
        ExecutionContext(getattr(adapter.dataset,'user_id',0),context,deadline=workspace.deadline,
            lease_check=getattr(workspace,'sandbox_lease_check',None),capture_frame=captured.append))
    workspace.frame_results[call_id]=captured[0]
    adapter.check_frame_budget(captured[0])
    data=output.data.model_dump(mode='json'); data['columns']=[c['name'] for c in data['columns']]
    workspace.call_results[call_id]=data
    if images and getattr(workspace,'on_event',None):
        workspace.on_event('sandbox_images',{'step_id':call_id,'images':images,'dataset_id':binding['dataset_id'],'dataset_version_id':binding['dataset_version_id']})
    return ToolResult(data=data,summary='受限自定义分析完成',metadata={'result_kind':'table','exposes_rows':True},warnings=output.warnings,execution_time_ms=output.execution_time_ms)
