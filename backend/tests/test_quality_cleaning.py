import pandas as pd
import pytest
from app.analysis.context import DatasetContext
from app.analysis.catalog import build_registry
from app.analysis.models import Permission
from app.analysis.errors import ToolError


def test_quality_nonfinite_and_outlier_preview():
    registry=build_registry()
    context=DatasetContext.from_frame(pd.DataFrame({'x':[1.,1.,1.,100.,float('inf')]}))
    assert registry.execute('infinite_value_analysis',context,{'columns':['x']}).data.findings[0].count==1
    finite=DatasetContext.from_frame(pd.DataFrame({'x':[1.,1.,1.,1.,100.]}))
    finding=registry.execute('outlier_analysis',finite,{'columns':['x'],'method':'iqr','limit':1}).data.findings[0]
    assert finding.count==1
    assert finding.row_refs==[4]


@pytest.mark.parametrize('tool,parameters',[
    ('fill_missing_values',{'columns':['x'],'value':0}),
    ('drop_missing_rows',{'columns':['x']}),
    ('remove_duplicates',{'columns':['x']}),
    ('convert_dtype',{'columns':['x'],'dtype':'string'}),
    ('parse_datetime',{'columns':['label'],'datetime_format':'%Y-%m-%d','errors':'coerce'}),
    ('replace_values',{'columns':['label'],'replacements':{'A':'B'}}),
    ('normalize_text',{'columns':['label'],'text_operations':['strip','upper']}),
    ('rename_columns',{'columns':['x'],'names':{'x':'renamed'}}),
    ('outlier_treatment',{'columns':['x'],'strategy':'clip'}),
])
def test_all_cleaning_tools_are_explicit_and_do_not_mutate(tool,parameters):
    registry=build_registry()
    frame=pd.DataFrame({'x':[1.,None,1.,100.],'label':[' A ','A','2026-01-01','bad']})
    original=frame.copy(deep=True)
    context=DatasetContext.from_frame(frame,dataset_version=1)
    with pytest.raises(ToolError): registry.calculate(tool,context,parameters)
    output=registry.calculate(tool,context,parameters,frozenset({Permission.READ_DATA,Permission.TRANSFORM_DATA}))
    assert output.data.source_version==1
    assert output.frame is not None
    pd.testing.assert_frame_equal(frame,original)
