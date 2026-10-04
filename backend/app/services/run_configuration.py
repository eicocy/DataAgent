"""Normalize public options and pin every authorized input before queuing."""
from fastapi import HTTPException
from sqlalchemy import select
from app.config import get_settings
from app.models import Dataset, DatasetVersion
from app.services.datasets import DatasetService
from app.profiles.service import ProfileService
from app.agent.context import ConversationContext


def public_config(request):
    result = {name: getattr(request, name, None) for name in ('depth', 'category', 'model_id')} | {
        'profile_ids': list(getattr(request, 'profile_ids', [])),
        'inputs': [x.model_dump() for x in getattr(request, 'inputs', [])]}
    # Legacy requests retain their original canonical shape.
    if getattr(request, 'artifact_refs', []): result['artifact_refs'] = list(dict.fromkeys(request.artifact_refs))
    if getattr(request, 'report_template', None): result['report_template'] = request.report_template
    if getattr(request, 'output_formats', []): result['output_formats'] = list(dict.fromkeys(request.output_formats))
    return result


def configured_model():
    settings = get_settings()
    return settings.deepseek_model if settings.llm_provider == 'deepseek' else settings.openai_model


def snapshot_config(db, user_id, session, request, primary, version):
    public = public_config(request)
    from app.artifacts.references import resolve_references
    try:
        references = resolve_references(db, user_id, session.id, public.get('artifact_refs', []))
    except LookupError as error:
        raise HTTPException(422, detail={'code': str(error), 'message': '引用不可用，请核对会话、来源和固定版本'}) from None
    from app.reports.exporters import exporter_registry
    if set(public.get('output_formats', [])) - set(exporter_registry().formats) - {'python', 'sql'}:
        raise HTTPException(422, detail={'code': 'REPORT_FORMAT_UNSUPPORTED', 'message': '报告格式不支持'})
    if public.get('output_formats') and not public.get('report_template'):
        raise HTTPException(422, detail={'code': 'REPORT_TEMPLATE_REQUIRED', 'message': '请选择报告类型'})
    delivery = None
    if public.get('report_template'):
        delivery = {'template':public['report_template'], 'formats':public.get('output_formats') or ['xlsx','docx','pdf','python']}
    if not any(public.values()):
        return None
    if public['model_id'] and public['model_id'] != configured_model():
        raise HTTPException(422, detail={'code': 'MODEL_NOT_ALLOWED', 'message': '只能选择服务端配置的模型'})
    profiles = ProfileService(db)
    try:
        profiles.seed()
        selected = profiles.selected(public['profile_ids'])
    except ValueError as exc:
        raise HTTPException(422, detail={'code': str(exc), 'message': '模板不存在、不可用或超过三个'}) from None
    bindings = public['inputs'] or ([{'alias': 'primary', 'dataset_id': primary.id, 'dataset_version_id': version.id}] if primary and version else [])
    if len({x['alias'] for x in bindings}) != len(bindings) or len({x['dataset_id'] for x in bindings}) != len(bindings):
        raise HTTPException(422, detail={'code': 'DUPLICATE_INPUT', 'message': '数据输入别名与数据集不能重复'})
    pinned = []
    for binding in bindings:
        dataset = db.scalar(select(Dataset).where(Dataset.id == binding['dataset_id']).with_for_update().execution_options(populate_existing=True))
        if not dataset or dataset.user_id != user_id:
            raise HTTPException(403, detail={'code': 'DATASET_FORBIDDEN', 'message': '数据输入不存在或未授权'})
        if dataset.status != 'ready':
            raise HTTPException(409, detail={'code': 'DATASET_NOT_READY', 'message': '数据集尚未就绪'})
        identifier = binding.get('dataset_version_id') or dataset.current_version_id
        current = db.scalar(select(DatasetVersion).where(DatasetVersion.id == identifier).with_for_update().execution_options(populate_existing=True)) if identifier else None
        if current is None:
            raise HTTPException(409, detail={'code': 'DATASET_VERSION_UNAVAILABLE', 'message': '输入版本不可用'})
        fixed = DatasetService(db).get_version(dataset, identifier)
        if not fixed:
            raise HTTPException(409, detail={'code': 'DATASET_VERSION_UNAVAILABLE', 'message': '输入版本不可用'})
        pinned.append(dict(binding, dataset_version_id=fixed.id))
    if pinned and (not primary or (pinned[0]['dataset_id'], pinned[0]['dataset_version_id']) != (primary.id, version.id if version else None)):
        raise HTTPException(422, detail={'code': 'PRIMARY_INPUT_MISMATCH', 'message': '首个输入必须是当前数据集的固定版本'})
    authorized_versions = {(x['dataset_id'], x['dataset_version_id']) for x in pinned}
    if any((binding['dataset_id'], binding['dataset_version_id']) not in authorized_versions for ref in references for binding in ref['dataset_versions']):
        raise HTTPException(409, detail={'code': 'ARTIFACT_INPUT_VERSION_MISMATCH', 'message': '请选择引用成果使用的数据集和固定版本'})
    if public['category'] and public['category'] not in {c['id'] for c in profiles.catalog()['categories']}:
        raise HTTPException(422, detail={'code': 'CATEGORY_INVALID', 'message': '分析方向不存在'})
    context = ConversationContext.from_session(session)
    versions = {item['dataset_version_id'] for item in pinned}
    from app.semantic.mappings import parse_corrections
    corrections = []
    for binding in pinned:
        fixed = db.get(DatasetVersion, binding['dataset_version_id'])
        corrections.extend(m.model_dump() for m in parse_corrections(request.question, [c['name'] for c in fixed.schema_json['columns']], fixed.id,context.semantic_mappings))
    if corrections:
        changed = {(m['dataset_version_id'], m['column']) for m in corrections}
        context.semantic_mappings = [m for m in context.semantic_mappings if (m['dataset_version_id'], m['column']) not in changed] + corrections
        context.semantic_version += 1
    # Submission is a write seam: persist trusted identity even when this
    # question contains no semantic corrections and keeps the same dataset.
    session.context_json = {**(session.context_json or {}), **context.model_dump(mode='json')}
    return {'version': '3.0', 'public': public, 'depth': public['depth'] or 'STANDARD', 'inputs': pinned, 'artifact_references': references, 'delivery':delivery,
        'profiles': [p.model_dump() for p in selected], 'catalog': profiles.catalog()['items'],
        'semantic_snapshot': [m for m in context.semantic_mappings if m.get('dataset_version_id') in versions],
        'semantic_version': context.semantic_version, 'model_id': public['model_id'] or configured_model()}
