from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class SemanticMapping(BaseModel):
    model_config = ConfigDict(extra='forbid')
    column: str = Field(min_length=1, max_length=200)
    concept: str = Field(min_length=1, max_length=100)
    role: Literal['metric', 'dimension']
    dataset_version_id: int = Field(gt=0)
    unit: str | None = Field(default=None, max_length=30)
    currency: str | None = Field(default=None, max_length=10)
    aggregation: Literal['sum', 'mean', 'count', 'nunique', 'none'] = 'none'
    confidence: float = Field(default=.5, ge=0, le=1)
    reason: str = Field(default='', max_length=500)
    source: Literal['candidate', 'confirmed', 'user'] = 'candidate'


def merge_mappings(candidates, overrides, version_id):
    priority = {'candidate': 0, 'confirmed': 1, 'user': 2}
    merged = {}
    for value in [*candidates, *overrides]:
        item = SemanticMapping.model_validate(value) if isinstance(value, dict) else value
        if item.dataset_version_id != version_id:
            continue
        old = merged.get(item.column)
        if old is None or priority[item.source] >= priority[old.source]:
            merged[item.column] = item
    return list(merged.values())


def parse_corrections(question, columns, version_id):
    """Only explicit known-column statements; inferred business prose never overwrites mappings."""
    import re
    concepts = {'销售额': 'revenue', '销售金额': 'revenue', '销量': 'quantity', '销售数量': 'quantity',
        '利润': 'profit', '成本': 'cost', '地区': 'region', '时间': 'time', '日期': 'time', '产品': 'product'}
    result = []
    for column in columns:
        pattern = rf'(?<![\w]){re.escape(column)}(?:字段)?\s*(?:不是[^，,。；;]+[，,]\s*)?是\s*({"|".join(concepts)})'
        match = re.search(pattern, question)
        if match:
            concept = concepts[match[1]]
            metric = concept in {'revenue', 'quantity', 'profit', 'cost'}
            result.append(SemanticMapping(column=column, concept=concept, role='metric' if metric else 'dimension',
                dataset_version_id=version_id, source='user', confidence=1, aggregation='sum' if metric else 'none', reason='用户在问题中明确修正字段含义'))
    return result
