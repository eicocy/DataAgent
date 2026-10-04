"""Every canonical available tool has real normal/boundary executions."""
import pandas as pd
import pytest
from app.analysis.catalog import build_registry
from app.analysis.context import DatasetContext
from app.analysis.models import Permission
from app.analysis.errors import ToolError

PARAMETERS={
    'join_data':{'right_alias':'r','left_on':['id'],'right_on':['key'],'how':'left','relationship':'many_to_one'},
    'publish_join':{'right_dataset_id':2,'right_version_id':2,'left_on':['id'],'right_on':['key'],'how':'left','relationship':'many_to_one'},
    'data_quality_score':{'field_rules':{'x':{'type':'numeric'}}},
    'cleaning_plan':{'operations':[{'tool':'rename_columns','parameters':{'columns':['x'],'names':{'x':'measurement'}}}]},
    'kpi_analysis':{'metrics':{'revenue':'x'},'currency':'USD','unit':'dollar'},
    'period_comparison':{'date_column':'time','value_column':'x','granularity':'month','start':'2024-03-01','end':'2024-04-01','comparison':'mom','currency':'USD','unit':'dollar'},
    'contribution_analysis':{'date_column':'time','value_column':'x','granularity':'month','start':'2024-03-01','end':'2024-04-01','comparison':'mom','currency':'USD','unit':'dollar','dimension':'label'},
    'forecast':{'time_column':'time','target_column':'x','horizon':1,'granularity':'month','aggregation':'sum'},
    'dataset_overview':{},'column_summary':{'columns':['x']},
    'select_columns':{'columns':['x']},'filter_rows':{'filters':[{'column':'x','operator':'gt','value':0}]},
    'sort_rows':{'sort':[{'column':'x'}]},'sample_rows':{'limit':2},
    'unique_values':{'columns':['label']},'value_counts':{'columns':['label']},
    'aggregate':{'metrics':[{'column':'x','aggregation':'sum'}]},
    'multi_aggregate':{'metrics':[{'column':'x','aggregation':'mean'},{'column':'x','aggregation':'median'}]},
    'groupby_aggregate':{'dimensions':['label'],'metrics':[{'column':'x','aggregation':'sum'}]},
    'pivot_table':{'index':['label'],'column':'time','value':'x'},'crosstab':{'index':['label'],'column':'time'},
    'rank':{'column':'x'},'top_n':{'column':'x'},'bottom_n':{'column':'x'},
    'percentage_share':{'column':'x'},'weighted_average':{'column':'x','weight_column':'weight'},
    **{name:{'column':'x','order_by':[{'column':'time'}]} for name in ['cumulative_sum','percentage_change','growth_rate','rolling_statistics']},
    **{name:{'columns':['x','y']} for name in ['descriptive_statistics','percentile','quantile','variance','standard_deviation','skewness','kurtosis','covariance','correlation']},
    **{name:{'columns':['x']} for name in ['missing_value_analysis','duplicate_analysis','constant_column_analysis','cardinality_analysis','invalid_numeric_analysis','infinite_value_analysis','outlier_analysis']},
    'invalid_datetime_analysis':{'columns':['day']},
    'fill_missing_values':{'columns':['x'],'value':0},'drop_missing_rows':{'columns':['x']},'remove_duplicates':{'columns':['label']},
    'convert_dtype':{'columns':['x'],'dtype':'string'},'parse_datetime':{'columns':['day'],'datetime_format':'%Y-%m-%d'},
    'replace_values':{'columns':['label'],'replacements':{'A':'C'}},'normalize_text':{'columns':['label']},
    'rename_columns':{'columns':['x'],'names':{'x':'measurement'}},'outlier_treatment':{'columns':['x'],'strategy':'clip'},
    'chart_spec':{'chart_type':'line','x':'time','y':['x']},'chart_recommendations':{},'eda':{},
}


@pytest.mark.parametrize('name',sorted(PARAMETERS))
def test_each_available_tool_has_real_typed_output_and_preserves_input(name):
    registry=build_registry()
    frame=pd.DataFrame({'label':['A','A','B','B'],'x':[1.,2.,3.,4.],'y':[2.,4.,6.,8.],'time':[1,2,3,4],'weight':[1.,1.,2.,2.],'day':['2026-01-01']*4})
    if name=='forecast':
        frame=pd.DataFrame({'time':pd.date_range('2020-01-01',periods=12,freq='MS'),'x':range(1,13)})
    if name in {'kpi_analysis','period_comparison','contribution_analysis'}:
        frame=pd.DataFrame({'time':['2024-02-01','2024-03-01'],'x':['0.1','0.2'],'label':['A','B']})
    original=frame.copy(deep=True)
    related={}
    if name in {'join_data','publish_join'}:
        frame=pd.DataFrame({'id':[1,2,3],'left_value':['a','b','c']});original=frame.copy(deep=True)
        related={'r' if name=='join_data' else 'right':DatasetContext.from_frame(pd.DataFrame({'key':[1,2],'right_value':['x','y']}),dataset_id=2,dataset_version=2)}
    output=registry.calculate(name,DatasetContext.from_frame(frame,related_inputs=related),PARAMETERS[name],frozenset({Permission.READ_DATA,Permission.TRANSFORM_DATA}))
    output.data.model_dump_json()
    pd.testing.assert_frame_equal(frame,original)


def test_catalog_has_no_unverified_available_tools():
    assert {tool.metadata.name for tool in build_registry().list_tools()}==set(PARAMETERS)


@pytest.mark.parametrize('name',sorted(PARAMETERS))
def test_unknown_input_and_missing_columns_are_rejected(name):
    registry=build_registry()
    with pytest.raises(ToolError): registry.validate_input(name,dict(PARAMETERS[name],unexpected_permission=True))
    params=PARAMETERS[name]
    if not params or name=='sample_rows': return
    context=DatasetContext.from_frame(pd.DataFrame({'unrelated':[1.,2.]}))
    with pytest.raises(ToolError): registry.calculate(name,context,params,frozenset({Permission.READ_DATA,Permission.TRANSFORM_DATA}))


@pytest.mark.parametrize('name',sorted(PARAMETERS))
def test_each_available_tool_empty_and_missing_input_has_structured_outcome(name):
    registry=build_registry()
    for frame in [pd.DataFrame({'label':pd.Series(dtype='string'),'x':pd.Series(dtype='float64'),'y':pd.Series(dtype='float64'),'time':pd.Series(dtype='int64'),'weight':pd.Series(dtype='float64'),'day':pd.Series(dtype='string')}),
                  pd.DataFrame({'label':[None]*3,'x':[float('nan')]*3,'y':[float('nan')]*3,'time':[1,2,3],'weight':[float('nan')]*3,'day':[None]*3})]:
        try:
            output=registry.calculate(name,DatasetContext.from_frame(frame),PARAMETERS[name],frozenset({Permission.READ_DATA,Permission.TRANSFORM_DATA}))
            output.data.model_dump_json()
        except ToolError as error:
            assert set(error.structured())=={'code','message','details','recoverable','suggestion'}


@pytest.mark.parametrize('name',sorted(PARAMETERS))
def test_each_available_tool_rejects_wrong_types_and_missing_required_parameters(name):
    registry=build_registry()
    with pytest.raises(ToolError):registry.validate_input(name,dict(PARAMETERS[name],columns=123))
    for field,spec in registry.get(name).input_schema.model_fields.items():
        if spec.is_required():
            parameters={key:value for key,value in PARAMETERS[name].items() if key!=field}
            with pytest.raises(ToolError):registry.validate_input(name,parameters)
