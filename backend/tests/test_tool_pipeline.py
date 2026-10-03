from datetime import date

import pytest

from app.services.analysis_tools import DatasetTools


def test_full_filtered_result_not_preview_feeds_aggregation():
    tools = DatasetTools.from_frame(1, [{'region': 'East', 'sales': 10}, {'region': 'East', 'sales': 20}, {'region': 'West', 'sales': 100}])
    tools.execute('filter_data', {'conditions': [{'column': 'region', 'operator': 'eq', 'value': 'East'}], 'limit': 1}, call_id='filtered')
    result = tools.execute('aggregate_data', {'metrics': [{'column': 'sales', 'aggregation': 'sum'}]}, source_ref='filtered', call_id='total')
    assert result.data['metric_values']['sales_sum'] == 30
    assert len(tools.frame_results['filtered']) == 2


def test_date_filter_accepts_iso_value():
    tools = DatasetTools.from_frame(1, [{'day': date(2026, 1, 1), 'sales': 10}, {'day': date(2026, 2, 1), 'sales': 20}])
    result = tools.execute('filter_data', {'conditions': [{'column': 'day', 'operator': 'gte', 'value': '2026-02-01'}]}, call_id='filtered')
    assert result.data['matched_count'] == 1


def test_numeric_filter_converts_string_value_and_rejects_invalid_value():
    tools = DatasetTools.from_frame(1, [{'sales': 10}, {'sales': 20}])
    result = tools.execute('filter_data', {'conditions': [{'column': 'sales', 'operator': 'eq', 'value': '20'}]}, call_id='filter')
    assert result.data['matched_count'] == 1
    with pytest.raises(ValueError):
        tools.execute('filter_data', {'conditions': [{'column': 'sales', 'operator': 'eq', 'value': 'invalid'}]}, call_id='invalid')


def test_growth_ranking_excludes_missing_and_zero_baseline():
    tools = DatasetTools.from_frame(1, [
        {'day': '2026-01-01', 'product': 'A', 'sales': 10}, {'day': '2026-06-01', 'product': 'A', 'sales': 30},
        {'day': '2026-01-01', 'product': 'B', 'sales': 20}, {'day': '2026-06-01', 'product': 'B', 'sales': 30},
        {'day': '2026-01-01', 'product': 'C', 'sales': 0}, {'day': '2026-06-01', 'product': 'C', 'sales': 50},
    ])
    result = tools.execute('growth_analysis', {'date_column': 'day', 'group_column': 'product', 'value_column': 'sales'}, call_id='growth')
    assert [row['product'] for row in result.data['rows']] == ['A', 'B']
    assert result.data['rows'][0]['growth_rate'] == 2
    assert result.data['excluded_count'] == 1


def test_chart_rejects_non_numeric_and_preserves_missing():
    tools = DatasetTools.from_frame(1, [{'region': 'A', 'sales': 10}, {'region': 'B', 'sales': None}])
    tools.execute('preview_data', {}, call_id='source')
    result = tools.execute('generate_chart', {'type': 'bar', 'dimension': 'region', 'metrics': [{'field': 'sales'}], 'title': 'Sales'}, source_ref='source', call_id='chart')
    assert result.data['series'][0]['data'][1]['value'] is None
    with pytest.raises(ValueError):
        tools.execute('generate_chart', {'type': 'bar', 'dimension': 'region', 'metrics': [{'field': 'region'}], 'title': 'Sales'}, source_ref='source', call_id='bad')


def test_monthly_chart_keeps_gaps_and_selects_growth_winners():
    tools = DatasetTools.from_frame(1, [
        {'day': '2026-01-01', 'product': 'A', 'sales': 10}, {'day': '2026-06-01', 'product': 'A', 'sales': 30},
        {'day': '2026-01-01', 'product': 'B', 'sales': 20}, {'day': '2026-06-01', 'product': 'B', 'sales': 30},
    ])
    tools.execute('time_group_analysis', {'date_column': 'day', 'group_column': 'product', 'value_column': 'sales'}, call_id='monthly')
    chart = tools.execute('generate_chart', {'type': 'line', 'dimension': 'day', 'group_column': 'product', 'selected_groups': ['A'], 'metrics': [{'field': 'sales_sum'}], 'title': 'Trend'}, source_ref='monthly', call_id='chart')
    assert chart.data['dimension']['type'] == 'time'
    assert len(chart.data['series']) == 1
    assert len(chart.data['series'][0]['data']) == 6
    assert chart.data['series'][0]['data'][1]['value'] is None


def test_metadata_does_not_load_projection():
    tools = DatasetTools.from_frame(1, [{'sales': 10}])
    tools.frame = None
    assert tools.execute('get_dataset_info', {}, call_id='info').data['dataset']['row_count'] == 1


def test_sql_cannot_claim_to_query_an_intermediate_frame():
    tools = DatasetTools.from_frame(1, [{'sales': 10}])
    tools.execute('preview_data', {}, call_id='preview')
    with pytest.raises(ValueError, match='SQL'):
        tools.execute('sql_query', {'query': 'SELECT sales FROM dataset_1'}, source_ref='preview', call_id='sql')
