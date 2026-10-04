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
    return workspace
