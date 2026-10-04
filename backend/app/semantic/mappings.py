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


def parse_corrections(question, columns, version_id,existing_mappings=None):
    """Only explicit known-column statements; inferred business prose never overwrites mappings."""
    import re
    concepts = {'销售额': 'revenue', '销售金额': 'revenue', '销量': 'quantity', '销售数量': 'quantity',
        '利润': 'profit', '成本': 'cost', '运营费用':'operating_expense', '费用':'operating_expense', '预算':'budget', '实际金额':'actual',
        '订单号':'order','客户':'customer', '地区': 'region', '时间': 'time', '日期': 'time', '产品': 'product'}
    result = []
    previous={m['column']:m for m in existing_mappings or [] if m.get('dataset_version_id')==version_id}
    for column in columns:
        pattern = rf'(?<![\w]){re.escape(column)}(?:字段)?\s*(?:不是[^，,。；;]+[，,]\s*)?是\s*({"|".join(concepts)})'
        match = re.search(pattern, question)
        declaration=re.search(rf'(?<![\w]){re.escape(column)}(?:字段)?\s*(?=(?:币种|currency|单位|unit))',question,re.I)
        if match or (declaration and column in previous):
            old=previous.get(column,{})
            concept = concepts[match[1]] if match else old['concept']
            metric = concept in {'revenue', 'quantity', 'profit', 'cost','operating_expense','budget','actual'}
            # Only explicit labels bind money. A unit never implies a currency.
            tail=question[match.end() if match else declaration.end():]
            # Another known-column declaration ends this field's metadata scope.
            stop=re.search(rf'(?:[。；;]|(?:{"|".join(re.escape(name) for name in columns)})(?:字段)?\s*(?:是|单位|币种))',tail)
            if stop: tail=tail[:stop.start()]
            currency=re.search(r'(?:币种|currency)\s*(?:是|为|改为)?\s*[:：]?\s*([A-Za-z]{3})(?![A-Za-z])',tail,re.I)
            unit=re.search(r'(?:单位|unit)\s*(?:是|为|改为)?\s*[:：]?\s*([^，,。；;\s]+)',tail,re.I)
            result.append(SemanticMapping(column=column, concept=concept, role='metric' if metric else 'dimension',
                dataset_version_id=version_id, source='user', confidence=1, aggregation='sum' if metric else 'none',
                currency=currency[1].upper() if currency else old.get('currency'), unit=unit[1] if unit else old.get('unit'), reason='用户在问题中明确修正字段含义或单位'))
    return result
