"""Conservative suggestions from names, types and cardinality; never invent units."""
import re
import pandas as pd
from app.semantic.mappings import SemanticMapping

METRICS = {
    'revenue': ('sales_amount', 'sale_amt', 'revenue', '销售金额', '销售额', '营业额'),
    'gmv': ('gmv', '成交总额'),
    'quantity': ('quantity', 'qty', 'units', '销量', '销售数量'),
    'profit': ('profit', 'net_profit', '利润', '净利润'),
    'cost': ('cost', '成本'),
    'conversion': ('conversion', '转化率'),
}
DIMENSIONS = {'region': ('region', '地区', '区域', 'city', '城市'), 'product': ('product', 'sku', '商品', '产品'),
    'customer': ('customer', 'user_id', '客户', '用户'), 'channel': ('channel', '渠道'),
    'department': ('department', '部门'), 'supplier': ('supplier', '供应商'), 'store': ('store', '门店'), 'order': ('order_id', '订单号')}


def detect_semantics(frame, version_id, original_names=None):
    original_names = original_names or {}
    result = []
    for column in frame.columns:
        series = frame[column]
        name = str(original_names.get(column, column)).lower().strip()
        normalized = re.sub(r'[\s-]+', '_', name)
        numeric = pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series)
        concept, role, confidence, aggregation = None, 'dimension', .75, 'none'
        identifier = normalized.endswith('_id') or normalized.endswith('编号') or normalized.endswith('编码')
        if numeric and not identifier:
            concept = next((key for key, aliases in METRICS.items() if normalized in aliases), None)
            if concept:
                role, confidence, aggregation = 'metric', .9, 'mean' if concept == 'conversion' else 'sum'
            elif normalized in {'sales', '销售'}:
                concept, role, confidence = 'ambiguous_sales', 'metric', .5
        if not concept:
            concept = next((key for key, aliases in DIMENSIONS.items() if any(alias in normalized for alias in aliases)), None)
        if pd.api.types.is_datetime64_any_dtype(series) or normalized in {'date', 'day', 'month', 'time', '日期', '时间', '月份'}:
            concept, role, confidence = 'time', 'dimension', .9
        if not concept and (not numeric or identifier):
            concept = 'identifier' if identifier or series.nunique(dropna=True) == len(series) else 'category'
        if concept:
            result.append(SemanticMapping(column=str(column), concept=concept, role=role, dataset_version_id=version_id,
                confidence=confidence, aggregation=aggregation, reason=f'字段名称、类型 {series.dtype}、唯一值 {series.nunique(dropna=True)}；未确认币种和单位'))
    return result
