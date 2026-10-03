import pandas as pd
import pytest


def test_registry_generic_groupby_and_immutable_context():
    from app.analysis.context import DatasetContext
    from app.analysis.catalog import build_registry
    registry = build_registry()
    for dimension, metric in [('地区', '销售额'), ('department', 'revenue')]:
        frame = pd.DataFrame({dimension: ['A', 'A'], metric: [10, 20]})
        original = frame.copy(deep=True)
        result = registry.execute('groupby_aggregate', DatasetContext.from_frame(frame), {'dimensions': [dimension], 'metrics': [{'column': metric, 'aggregation': 'sum'}]})
        assert result.data.rows[0][metric + '_sum'] == 30
        pd.testing.assert_frame_equal(frame, original)
    assert registry.exists('correlation')
    assert all(not entry['modifies_dataset'] for entry in registry.get_llm_tool_manifest())


def test_registry_rejects_duplicate_unknown_and_invalid_input():
    from app.analysis.catalog import build_registry
    from app.analysis.errors import ToolError
    registry = build_registry()
    with pytest.raises(ToolError):
        registry.register(registry.get('aggregate'))
    with pytest.raises(ToolError):
        registry.get('missing')
    with pytest.raises(ToolError):
        registry.validate_input('aggregate', {'metrics': [], 'arbitrary': True})


@pytest.mark.parametrize('operation', ['sum','mean','median','count','nunique','min','max','std','var','first','last'])
def test_all_aggregations_and_missing(operation):
    from app.analysis.catalog import build_registry
    from app.analysis.context import DatasetContext
    context=DatasetContext.from_frame(pd.DataFrame({'metric':pd.Series([10,None,20],dtype='Int64')}))
    result=build_registry().execute('aggregate',context,{'metrics':[{'column':'metric','aggregation':operation}]})
    assert result.data.rows[0]['metric_'+operation] is not None


def test_filters_sort_pivot_and_integer_window_safety():
    from app.analysis.catalog import build_registry
    from app.analysis.context import DatasetContext
    from app.analysis.errors import ToolError
    registry=build_registry()
    context=DatasetContext.from_frame(pd.DataFrame({'g':['A','A','B'],'time':[1,2,3],'x':[10,20,5]}))
    result=registry.execute('filter_rows',context,{'filters':[{'column':'g','operator':'not_in','value':['B']}],'columns':['x']})
    assert [r['x'] for r in result.data.rows]==[10,20]
    result=registry.execute('pivot_table',context,{'index':['g'],'column':'time','value':'x'})
    assert result.data.row_count==2
    huge=DatasetContext.from_frame(pd.DataFrame({'time':[1,2],'x':[2**63-1,1]}))
    with pytest.raises(ToolError):
        registry.execute('cumulative_sum',huge,{'column':'x','order_by':[{'column':'time'}]})
    with pytest.raises(ToolError):
        registry.execute('rolling_statistics',huge,{'column':'x','order_by':[{'column':'time'}],'window':2,'aggregation':'sum'})


def test_ratios_sequences_and_pairwise_correlations():
    from app.analysis.catalog import build_registry
    from app.analysis.context import DatasetContext
    registry=build_registry()
    context=DatasetContext.from_frame(pd.DataFrame({'time':[1,2,3,4],'x':[0.,10.,None,30.],'y':[0.,20.,9.,60.],'weight':[0.,0.,0.,0.]}))
    result=registry.execute('weighted_average',context,{'column':'x','weight_column':'weight'})
    assert result.data.values[0].status=='zero_denominator'
    result=registry.execute('percentage_change',context,{'column':'x','order_by':[{'column':'time'}]})
    assert result.data.rows[1]['x_percentage_change'] is None
    assert result.data.rows[3]['x_percentage_change'] is None
    for method in ['pearson','spearman']:
        result=registry.execute('correlation',context,{'columns':['x','y'],'method':method})
        pair=next(p for p in result.data.pairs if p.x=='x' and p.y=='y')
        assert pair.sample_size==3
        assert pair.coefficient==pytest.approx(1)


def test_constant_and_insufficient_statistical_values():
    from app.analysis.catalog import build_registry
    from app.analysis.context import DatasetContext
    registry=build_registry()
    context=DatasetContext.from_frame(pd.DataFrame({'x':[1.],'y':[2.]}))
    assert registry.execute('variance',context,{'columns':['x']}).data.values[0].value is None
    assert registry.execute('standard_deviation',context,{'columns':['x']}).data.values[0].value is None
    context=DatasetContext.from_frame(pd.DataFrame({'x':[1.,1.,1.],'y':[2.,3.,4.]}))
    assert registry.execute('correlation',context,{'columns':['x','y']}).data.pairs[1].status=='constant'
