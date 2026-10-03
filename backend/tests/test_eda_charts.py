import pandas as pd
import pytest
from app.analysis.catalog import build_registry
from app.analysis.context import DatasetContext


def test_eda_composes_registered_tools(monkeypatch):
    registry=build_registry()
    called=[]
    original=registry.calculate
    def tracked(name,*args,**kwargs):
        called.append(name)
        return original(name,*args,**kwargs)
    monkeypatch.setattr(registry,'calculate',tracked)
    context=DatasetContext.from_frame(pd.DataFrame({'category':['A','B','A'],'amount':[1.,2.,3.],'other':[2.,4.,6.]}))
    result=registry.execute('eda',context,{})
    assert result.data.kind=='eda'
    assert {'dataset_overview','missing_value_analysis','descriptive_statistics','correlation','chart_recommendations'}<=set(called)
    assert all(section.status!='failed' for section in result.data.sections)


@pytest.mark.parametrize('chart_type',['line','bar','scatter','histogram','boxplot','heatmap','pie','donut'])
def test_all_internal_chart_types_are_typed_and_not_chat_exposed(chart_type):
    registry=build_registry()
    context=DatasetContext.from_frame(pd.DataFrame({'position':[1,2,3],'amount':[1.,2.,3.],'other':[3.,4.,5.]}))
    result=registry.execute('chart_spec',context,{'chart_type':chart_type,'x':'position','y':['amount','other'] if chart_type=='heatmap' else ['amount']})
    assert result.data.version=='2.0'
    assert result.data.series
    assert 'chart_spec' not in [item['name'] for item in registry.get_llm_tool_manifest()]
