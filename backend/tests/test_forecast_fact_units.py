from decimal import Decimal
import pandas as pd
import pytest
from app.analysis.catalog import build_registry
from app.analysis.context import DatasetContext
from app.execution.evidence import ReportContent,render_report


@pytest.fixture(scope='module')
def forecast_result():
    frame=pd.DataFrame({'date':pd.date_range('2024-01-01',periods=24,freq='MS'),'value':[10+i+(i%3) for i in range(24)]})
    return build_registry().calculate('forecast',DatasetContext.from_frame(frame),{'time_column':'date','target_column':'value','horizon':3,'granularity':'month','aggregation':'sum'}).data


def display(result,path,decimals=2):
    content=ReportContent(template='MAPE {value}',facts=[{'key':'value','step_id':'f','path':path,'format':'percent','decimals':decimals}],evidence_refs=['f'])
    return render_report(content,{'f':result})


@pytest.mark.parametrize('path',[
    ['metrics','mape'],['baseline','metrics','mape'],['candidates',0,'metrics','mape'],
    ['baseline','folds',0,'metrics','mape'],['candidates',0,'folds',0,'metrics','mape'],
])
def test_forecast_mape_percent_points_do_not_scale_twice(forecast_result,path):
    data=forecast_result.model_dump(mode='json')
    node=data
    for key in path[:-1]:node=node[key]
    node[path[-1]]=3.594354477737491
    assert display(data,path)=='MAPE 3.59%'


def test_actual_typed_forecast_result_renders_authoritative_unit(forecast_result):
    expected=format(Decimal(str(forecast_result.metrics.mape)).quantize(Decimal('.01')),'f')
    assert display(forecast_result,['metrics','mape'])==f'MAPE {expected}%'


@pytest.mark.parametrize('path',[
    ['metrics','mape_coverage'],['baseline','metrics','mape_coverage'],
    ['candidates',0,'folds',0,'metrics','mape_coverage'],['uncertainty','residual_quantile'],
])
def test_forecast_fraction_paths_still_scale(forecast_result,path):
    data=forecast_result.model_dump(mode='json');node=data
    for key in path[:-1]:node=node[key]
    node[path[-1]]=.9
    assert display(data,path)=='MAPE 90.00%'


@pytest.mark.parametrize('data,path',[
    ({'kind':'table','metrics':{'mape':3.594354477737491}},['metrics','mape']),
    ({'metrics':{'mape':3.594354477737491}},['metrics','mape']),
    ({'kind':'forecast','untrusted':{'mape':3.594354477737491}},['untrusted','mape']),
    ({'kind':'forecast','rows':[{'mape':3.594354477737491}]},['rows',0,'mape']),
])
def test_unit_route_requires_forecast_kind_and_exact_typed_path(data,path):
    assert display(data,path)=='MAPE 359.44%'


@pytest.mark.parametrize('data,path',[
    ({'kind':'period_comparison','growth_rate':{'value':'-0.125'}},['growth_rate','value']),
    ({'kind':'contribution','groups':[{'contribution_share':'0.125'}]},['groups',0,'contribution_share']),
])
def test_business_fraction_percentage_contract_unchanged(data,path):
    assert display(data,path)==('MAPE -12.50%' if data['kind']=='period_comparison' else 'MAPE 12.50%')


@pytest.mark.parametrize('bad',['NaN','Infinity','1e1000000','9'*1001,'not numeric'])
def test_percent_point_route_does_not_relax_decimal_guards(bad):
    with pytest.raises(ValueError):display({'kind':'forecast','metrics':{'mape':bad}},['metrics','mape'])
