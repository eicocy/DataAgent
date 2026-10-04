"""Normalize public options and pin every authorized input before queuing."""
from fastapi import HTTPException
from app.config import get_settings
from app.models import Dataset, DatasetVersion
from app.services.datasets import DatasetService
from app.profiles.service import ProfileService
from app.agent.context import ConversationContext


def public_config(request):
    return {name: getattr(request, name, None) for name in ('depth', 'category', 'model_id')} | {
        'profile_ids': list(getattr(request, 'profile_ids', [])),
        'inputs': [x.model_dump() for x in getattr(request, 'inputs', [])]}


def configured_model():
    settings = get_settings()
    return settings.deepseek_model if settings.llm_provider == 'deepseek' else settings.openai_model


def snapshot_config(db, user_id, session, request, primary, version):
    public = public_config(request)
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
        dataset = db.get(Dataset, binding['dataset_id'])
        if not dataset or dataset.user_id != user_id:
            raise HTTPException(403, detail={'code': 'DATASET_FORBIDDEN', 'message': '数据输入不存在或未授权'})
        if dataset.status != 'ready':
            raise HTTPException(409, detail={'code': 'DATASET_NOT_READY', 'message': '数据集尚未就绪'})
        fixed = DatasetService(db).get_version(dataset, binding.get('dataset_version_id'))
        if not fixed:
            raise HTTPException(409, detail={'code': 'DATASET_VERSION_UNAVAILABLE', 'message': '输入版本不可用'})
        pinned.append(dict(binding, dataset_version_id=fixed.id))
    if pinned and (not primary or (pinned[0]['dataset_id'], pinned[0]['dataset_version_id']) != (primary.id, version.id if version else None)):
        raise HTTPException(422, detail={'code': 'PRIMARY_INPUT_MISMATCH', 'message': '首个输入必须是当前数据集的固定版本'})
    if public['category'] and public['category'] not in {c['id'] for c in profiles.catalog()['categories']}:
        raise HTTPException(422, detail={'code': 'CATEGORY_INVALID', 'message': '分析方向不存在'})
    context = ConversationContext.model_validate(session.context_json or {'conversation_id': session.id, 'user_id': user_id})
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
        session.context_json = context.model_dump(mode='json')
    return {'version': '3.0', 'public': public, 'depth': public['depth'] or 'STANDARD', 'inputs': pinned,
        'profiles': [p.model_dump() for p in selected], 'catalog': profiles.catalog()['items'],
        'semantic_snapshot': [m for m in context.semantic_mappings if m.get('dataset_version_id') in versions],
        'semantic_version': context.semantic_version, 'model_id': public['model_id'] or configured_model()}
