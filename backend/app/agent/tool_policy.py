"""Shared chat tool policy; execution validation remains authoritative."""

CLEANING_TOOLS = frozenset({
    'get_dataset_info', 'preview_data', 'missing_value_analysis', 'duplicate_analysis',
    'constant_column_analysis', 'cardinality_analysis', 'invalid_numeric_analysis',
    'invalid_datetime_analysis', 'infinite_value_analysis', 'outlier_analysis',
})
