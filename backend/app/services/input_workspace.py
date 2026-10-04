"""Load only pinned, owned dataset snapshots into independent adapters."""
from types import SimpleNamespace
from sqlalchemy import select
from app.models import Dataset, DatasetColumn
from app.services.datasets import DatasetService
from app.services.analysis_tools import DatasetTools
from app.datasets.schemas import DatasetSchema, DatasetProfile, column_storage_type
from app.agent.graph_executor import InputWorkspace
from app.semantic.detectors import detect_semantics
from app.semantic.mappings import merge_mappings


def load_workspace(db, user_id, configuration, primary_tools, business_bind, projection_bind, readonly_bind, event, lease_check):
    from app.services.analysis import select_projection_bind, VersionUnavailable
    inputs = {}
    semantics = []
    metadata = {}
    total_bytes = 0
    from app.config import get_settings
    for binding in configuration['inputs']:
        lease_check()
        dataset = db.get(Dataset, binding['dataset_id'])
        if not dataset or dataset.user_id != user_id:
            raise VersionUnavailable()
        version = DatasetService(db).get_version(dataset, binding['dataset_version_id'])
        if not version:
            raise VersionUnavailable()
        if dataset.id == primary_tools.dataset.id:
            tools = primary_tools
        else:
            columns = db.scalars(select(DatasetColumn).where(DatasetColumn.dataset_id == dataset.id)).all()
            bind = select_projection_bind(version, business_bind, projection_bind)
            tools = DatasetTools(dataset, columns, bind, readonly_bind)
            tools.frame = DatasetService(db, bind).load_frame(dataset, columns, version.id)
            tools.dataset_version_id = version.id
            tools.projection_table = version.projection_table
            tools.version_schema = DatasetSchema.model_validate(version.schema_json)
            tools.version_profile = DatasetProfile.model_validate(version.profile_json)
            tools.columns = [SimpleNamespace(name=c.name, original_name=c.original_name, data_type=column_storage_type(c),
                nullable=bool(tools.frame[c.name].isna().any()), missing_count=int(tools.frame[c.name].isna().sum()), unique_count=int(tools.frame[c.name].nunique()), sample_values_json=[]) for c in tools.version_schema.columns]
            tools.schema = {c.name: c for c in tools.columns}
        tools.on_event, tools.check_lease = event, lease_check
        # Authorized Session remains on the owner thread: business/Join tools
        # are serial; parallel tools receive only already loaded frames.
        bind=select_projection_bind(version,business_bind,projection_bind)
        tools.exact_frame_loader=lambda dataset=dataset,version_id=version.id,columns=tools.columns,bind=bind: DatasetService(db,bind).load_frame(dataset,columns,version_id,preserve_decimal=True)
        total_bytes += int(tools.frame.memory_usage(deep=True).sum())
        if total_bytes * 3 > get_settings().dataframe_max_bytes:
            raise ValueError('WORKSPACE_MEMORY_BUDGET')
        names = {c['name']: c.get('original_name', c['name']) for c in version.schema_json['columns']}
        candidates = detect_semantics(tools.frame, version.id, names)
        semantics.extend(m.model_dump() for m in merge_mappings(candidates, configuration['semantic_snapshot'], version.id))
        tools.semantic_mappings=[m for m in semantics if m['dataset_version_id']==version.id]
        from app.semantic.business_validation import metadata_evidence
        metadata[binding['alias']] = {'dataset_id': dataset.id, 'dataset_version_id': version.id, 'row_count': len(tools.frame),
            'columns': [{'name': c.name, 'label': c.original_name, 'data_type': c.data_type} for c in tools.columns],
            'business_metadata':metadata_evidence(tools.frame)}
        inputs[binding['alias']] = tools
    workspace = InputWorkspace(inputs)
    workspace.metadata_by_input = metadata
    configuration['semantic_snapshot'] = semantics
    workspace.configuration = configuration
    if configuration.get('artifact_references'):
        from app.models import AnalysisRecord
        from app.services.artifacts import ArtifactStore
        from app.artifacts.manager import ArtifactManager
        prior_plans = []
        for reference in configuration['artifact_references']:
            source = db.get(AnalysisRecord,reference.get('record_id')) if reference.get('record_id') else None
            if source is None: continue
            if source.user_id != user_id or source.session_id != primary_tools.conversation_state.conversation_id:
                raise VersionUnavailable()
            prior_plans.append(source.plan_json or {})
            for step in (source.plan_json or {}).get('steps',[]):
                ref = step.get('result_ref') or ''
                if step.get('status')!='COMPLETED' or not ref.startswith('artifact:') or not ref.split(':',1)[1].isdigit(): continue
                item = ArtifactManager(db).owned(int(ref.split(':',1)[1]),user_id,source.session_id,require_ready=True)
                alias = step.get('input_alias',configuration['inputs'][0]['alias'])
                old_inputs = (source.request_config_json or {}).get('inputs') or [{'alias':'primary','dataset_id':source.dataset_id,'dataset_version_id':source.dataset_version_id}]
                old_binding = next((b for b in old_inputs if b['alias']==alias),None)
                new_alias = next((b['alias'] for b in configuration['inputs'] if old_binding and
                    (b['dataset_id'],b['dataset_version_id'])==(old_binding['dataset_id'],old_binding['dataset_version_id'])),None)
                if not new_alias: continue
                if (source.request_config_json or {}).get('semantic_snapshot',[]) != configuration.get('semantic_snapshot',[]): continue
                workspace.reuse_steps[step['step_id']]={'step':{**step,'input_alias':new_alias},
                    'artifact_id':item.id,'payload':ArtifactStore(db).read(item)}
        configuration['reference_plans'] = prior_plans
    return workspace
