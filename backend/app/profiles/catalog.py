"""One catalog for templates and capability disclosure, backed by real tools."""
import json
from functools import lru_cache
from pathlib import Path

from app.analysis.catalog import build_registry
from app.profiles.schemas import AnalysisProfile, ProfileCategory


@lru_cache
def _catalog():
    raw = json.loads(Path(__file__).with_name('catalog.json').read_text(encoding='utf-8'))
    categories = [ProfileCategory.model_validate(item) for item in raw['categories']]
    profiles = [AnalysisProfile.model_validate(item) for item in raw['items']]
    if len({p.id for p in profiles}) != len(profiles):
        raise ValueError('Duplicate profile ID')
    if any(p.category not in {c.id for c in categories} for p in profiles):
        raise ValueError('Unknown profile category')
    return categories, profiles


def profile_catalog(category: str | None = None) -> dict:
    categories, profiles = _catalog()
    registry = build_registry(include_legacy=True)
    chat_tools = {t['name'] for t in registry.get_llm_tool_manifest()}
    output = []
    for profile in profiles:
        if category and profile.category != category:
            continue
        item = profile.model_dump()
        if profile.availability != 'planned' and not set(profile.required_capabilities) <= chat_tools:
            item['availability'] = 'planned'
        output.append(item)
    return {'categories': [c.model_dump() for c in categories], 'items': output,
            'profile_execution': False}
