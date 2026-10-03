from dataclasses import replace
from decimal import Decimal
import pandas as pd
import pytest
from app.analysis.catalog import build_registry
from app.analysis.context import DatasetContext
from app.analysis.errors import ToolError


def ctx(frame):
    return replace(DatasetContext.from_frame(pd.DataFrame({'x':[1]}), dataset_id=7, dataset_version=3), frame=pd.DataFrame(frame))


def run(name, frame, **params):
    return build_registry().execute(name, ctx(frame), params).data


def kpi(frame, **params):
    return run('kpi_analysis', frame, metrics={'revenue':'amount'}, currency='USD', unit='dollar', **params)


def period(frame, name='period_comparison', **params):
    args=dict(date_column='date', value_column='amount', granularity='month', start='2024-03-01', end='2024-04-01', comparison='mom', currency='USD', unit='dollar')
    args.update(params)
    return run(name, frame, **args)


def test_exact_decimal_sum_and_unique_ids():
    data=kpi({'amount':[Decimal('0.1'),Decimal('0.2')], 'order':['x','x'], 'customer':['a','b']}, order_id_column='order', customer_id_column='customer')
    assert data.metrics['revenue'].value=='0.3'
    assert data.metrics['orders_count'].value=='1'
    assert data.metrics['customers_count'].value=='2'
    assert data.dataset_id==7 and data.dataset_version==3


def test_large_text_decimal_preserved_records_not_orders():
    data=kpi({'amount':['9007199254740993.01','0.02']})
    assert data.metrics['revenue'].value=='9007199254740993.03'
    assert data.metrics['records_count'].value=='2' and 'orders_count' not in data.metrics


def test_derived_margins_variance_gmv_separate():
    data=run('kpi_analysis', {'r':['10'],'c':['4'],'e':['2'],'g':['15'],'b':['9'],'a':['10']}, metrics={'revenue':'r','cost':'c','operating_expense':'e','gmv':'g','budget':'b','actual':'a'}, currency='USD', unit='dollar')
    assert {k:v.value for k,v in data.metrics.items() if k in ['gross_profit','operating_profit','gross_margin','operating_margin','variance','gmv']}=={'gross_profit':'6','operating_profit':'4','gross_margin':'0.6','operating_margin':'0.4','variance':'1','gmv':'15'}


def test_zero_denominator_is_null_with_reason():
    data=run('kpi_analysis', {'r':['0'],'c':['3']}, metrics={'revenue':'r','cost':'c'},currency='USD',unit='dollar')
    assert data.metrics['gross_margin'].value is None and data.metrics['gross_margin'].status=='zero_denominator' and data.metrics['gross_margin'].explanation


@pytest.mark.parametrize('params', [{}, {'currency':'USD'}, {'unit':'dollar'}])
def test_missing_money_metadata_rejected(params):
    with pytest.raises(ToolError): run('kpi_analysis', {'amount':['1']}, metrics={'revenue':'amount'}, **params)


@pytest.mark.parametrize('column,values', [('currency',['USD','EUR']),('unit',['dollar','cent'])])
def test_mixed_metadata_rejected_even_with_explicit_override(column,values):
    with pytest.raises(ToolError): run('kpi_analysis', {'amount':['1','2'],column:values},metrics={'revenue':'amount'},currency='USD',unit='dollar',**{column+'_column':column})


@pytest.mark.parametrize('bad', [None, 'NaN', 'Infinity', True, 'oops', complex(1,2)])
def test_invalid_money_rejected(bad):
    with pytest.raises(ToolError): kpi({'amount':['1',bad]})


def test_float_precision_limitation():
    assert any('float' in s for s in kpi({'amount':[0.1,0.2]}).limitations)


def test_mom_ranges_and_real_delta():
    data=period({'date':['2024-02-01','2024-03-01'],'amount':['1.1','1.4']})
    assert data.current.value=='1.4' and data.previous.value=='1.1' and data.delta.value=='0.3'
    assert data.previous_range.start=='2024-02-01' and data.previous_range.end=='2024-03-01'


def test_yoy_leap_calendar_range():
    data=period({'date':['2023-02-01','2024-02-29'],'amount':['2','3']}, start='2024-02-01',end='2024-03-01',comparison='yoy')
    assert data.previous_range.start=='2023-02-01' and data.previous_range.end=='2023-03-01'


def test_custom_same_length_calendar_windows():
    data=period({'date':['2022-01-01','2024-03-01'],'amount':['2','3']}, comparison='custom', previous_start='2022-01-01',previous_end='2022-02-01')
    assert data.delta.value=='1'


@pytest.mark.parametrize('kwargs', [dict(end='2024-03-20'),dict(comparison='custom',previous_start='2022-01-01',previous_end='2022-03-01')])
def test_partial_or_unequal_calendar_windows_rejected(kwargs):
    with pytest.raises(ToolError): period({'date':['2024-03-01'],'amount':['1']},**kwargs)


def test_missing_previous_is_unavailable_not_zero():
    data=period({'date':['2024-03-01'],'amount':['2']})
    assert data.previous.value is None and data.delta.value is None and data.status=='insufficient_coverage'


def test_missing_interior_month_is_insufficient():
    data=period({'date':['2023-12-01','2024-02-01','2024-03-01'],'amount':['1','2','3']},start='2024-02-01',end='2024-04-01',comparison='custom',previous_start='2023-12-01',previous_end='2024-02-01')
    assert data.status=='insufficient_coverage'


@pytest.mark.parametrize('bad', ['NaT','',0,True])
def test_invalid_dates_rejected(bad):
    with pytest.raises(ToolError): period({'date':['2024-02-01','2024-03-01',bad],'amount':['1','2','3']})


def test_entry_exit_outer_groups_reconcile_exactly():
    data=period({'date':['2024-02-01','2024-02-02','2024-03-01','2024-03-02'], 'amount':['0.1','0.2','0.4','0.5'],'group':['exit','stay','stay','entry']},name='contribution_analysis',dimension='group')
    rows={r.dimension:r for r in data.groups}
    assert rows['entry'].previous=='0' and rows['exit'].current=='0'
    assert sum(Decimal(r.delta) for r in rows.values())==Decimal(data.delta.value)==Decimal('0.6')
    assert any('causal' in s for s in data.limitations)


def test_zero_delta_contribution_share_null():
    data=period({'date':['2024-02-01','2024-03-01'],'amount':['2','2'],'group':['a','b']},name='contribution_analysis',dimension='group')
    assert all(g.contribution_share is None for g in data.groups)


def test_filter_applies_to_same_precision_core():
    data=kpi({'amount':['0.1','0.2'],'group':['a','b']},filters=[{'column':'group','operator':'eq','value':'a'}])
    assert data.metrics['revenue'].value=='0.1'


def test_metadata_columns_infer_unit_and_currency():
    data=run('kpi_analysis', {'amount':['1','2'],'ccy':['USD','USD'],'u':['dollar','dollar']},metrics={'revenue':'amount'},currency_column='ccy',unit_column='u')
    assert data.currency=='USD' and data.unit=='dollar'


@pytest.mark.parametrize('bad', [None,'NaN','Infinity',True,'oops',complex(1,2)])
def test_bad_numeric_has_precise_error_code(bad):
    with pytest.raises(ToolError) as error: kpi({'amount':['1',bad]})
    assert error.value.code=='BUSINESS_NUMERIC_INVALID'


@pytest.mark.parametrize('bad', ['NaT','',0,True])
def test_bad_date_has_precise_error_code(bad):
    with pytest.raises(ToolError) as error: period({'date':['2024-02-01','2024-03-01',bad],'amount':['1','2','3']})
    assert error.value.code=='BUSINESS_DATE_INVALID'


def test_high_precision_addition_exceeds_default_decimal_context():
    data=kpi({'amount':['123456789012345678901234567890.12345678','0.00000001']})
    assert data.metrics['revenue'].value=='123456789012345678901234567890.12345679'


def test_decimal_precision_budget_is_explicit():
    with pytest.raises(ToolError) as error: kpi({'amount':['1e1001']})
    assert error.value.code=='DECIMAL_PRECISION_BUDGET_EXCEEDED'


@pytest.mark.parametrize('granularity,start,end,previous', [('day','2024-03-01','2024-03-02','2024-02-29'),('quarter','2024-04-01','2024-07-01','2024-01-01'),('year','2024-01-01','2025-01-01','2023-01-01')])
def test_other_granularities_have_real_calendar_previous(granularity,start,end,previous):
    data=period({'date':[previous,start],'amount':['1','3']},granularity=granularity,start=start,end=end)
    assert data.previous_range.start==previous and data.delta.value=='2'


def test_day_leap_yoy_length_mismatch_not_silently_compared():
    with pytest.raises(ToolError) as error: period({'date':['2024-02-01'],'amount':['1']},granularity='day',start='2024-02-01',end='2024-03-01',comparison='yoy')
    assert error.value.code=='BUSINESS_PERIOD_LENGTH_MISMATCH'


def test_zero_previous_growth_rate_undefined():
    data=period({'date':['2024-02-01','2024-03-01'],'amount':['0','2']})
    assert data.growth_rate.status=='zero_denominator' and data.delta.value=='2'


def test_filter_result_preserves_frame_and_all_groups():
    frame={'date':['2024-02-01','2024-03-01'],'amount':['1','2'],'group':[None,None]}
    original=ctx(frame)
    before=original.frame.copy(deep=True)
    data=build_registry().execute('contribution_analysis',original,dict(date_column='date',value_column='amount',granularity='month',start='2024-03-01',end='2024-04-01',comparison='mom',currency='USD',unit='dollar',dimension='group')).data
    assert data.groups[0].dimension is None and data.groups[0].delta=='1'
    pd.testing.assert_frame_equal(original.frame,before)


def test_invalid_metric_expression_is_rejected():
    with pytest.raises(ToolError) as error: run('kpi_analysis',{'amount':['1']},metrics={'eval':'amount'},currency='USD',unit='dollar')
    assert error.value.code=='TOOL_INPUT_INVALID'


def test_calendar_boundaries_reject_time_of_day():
    with pytest.raises(ToolError) as error: period({'date':['2024-02-01','2024-03-01'],'amount':['1','2']},start='2024-03-01T12:00:00',end='2024-04-01T12:00:00')
    assert error.value.code=='BUSINESS_PERIOD_ALIGNMENT_REQUIRED'


def test_output_group_strings_reject_nonfinite_decimal():
    from app.analysis.models import ContributionGroup
    with pytest.raises(ValueError): ContributionGroup(dimension='a',current='NaN',previous='0',delta='1',contribution_share=None)


def test_explicit_metadata_cannot_override_column_metadata():
    with pytest.raises(ToolError) as error: run('kpi_analysis',{'amount':['1'],'ccy':['EUR']},metrics={'revenue':'amount'},currency='USD',unit='dollar',currency_column='ccy')
    assert error.value.code=='BUSINESS_METADATA_CONFLICT'


def test_operating_profit_formula_does_not_claim_net_profit():
    data=run('kpi_analysis',{'r':['10'],'c':['4'],'e':['2']},metrics={'revenue':'r','cost':'c','operating_expense':'e'},currency='USD',unit='dollar')
    assert data.metrics['operating_profit'].value=='4'
    assert data.metrics['operating_margin'].value=='0.4'
    assert 'net_profit' not in data.metrics and 'net_margin' not in data.metrics


def test_pure_count_kpi_needs_no_currency_or_money_columns():
    data=run('kpi_analysis',{'order':['a','a','b'],'customer':['x','x','y'],'product':['p','q','p']},order_id_column='order',customer_id_column='customer',product_id_column='product')
    assert {k:v.value for k,v in data.metrics.items()}=={'records_count':'3','orders_count':'2','customers_count':'2','products_count':'2'}
    assert data.currency is None and data.unit is None


def test_records_only_kpi_with_empty_metrics():
    data=run('kpi_analysis',{'arbitrary':['x','y']},metrics={})
    assert data.metrics['records_count'].value=='2'


@pytest.mark.parametrize('name',['period_comparison','contribution_analysis'])
def test_quantity_periods_need_unit_but_no_currency(name):
    args=dict(date_column='date',value_column='amount',granularity='month',start='2024-03-01',end='2024-04-01',comparison='mom',value_kind='quantity',unit='items')
    if name=='contribution_analysis': args['dimension']='group'
    data=run(name,{'date':['2024-02-01','2024-03-01'],'amount':['2','5'],'group':['a','b']},**args)
    assert data.delta.value=='3' and data.currency is None and data.unit=='items' and data.value_kind=='quantity'


def test_quantity_period_still_requires_confirmed_unit():
    with pytest.raises(ToolError) as error:
        run('period_comparison',{'date':['2024-02-01','2024-03-01'],'amount':['2','5']},date_column='date',value_column='amount',granularity='month',start='2024-03-01',end='2024-04-01',comparison='mom',value_kind='quantity')
    assert error.value.code=='BUSINESS_METADATA_REQUIRED'


def test_multiple_business_concepts_may_reference_same_column():
    data=run('kpi_analysis',{'amount':['0.1','0.2'],'budget':['0.2','0.2']},metrics={'revenue':'amount','actual':'amount','budget':'budget'},currency='USD',unit='dollar')
    assert data.metrics['revenue'].value==data.metrics['actual'].value=='0.3'
    assert data.metrics['variance'].value=='-0.1'
