from copy import deepcopy

import pandas as pd
import pytest

from app.execution.validators import ResultValidationError, validate_result
from test_forecast_fact_units import forecast_result
from test_upgrade_phase3_business import kpi, period


def missing(data, frame=None):
    return [note for note in validate_result(data, frame) if note.code == 'RESULT_MISSING_VALUES']


@pytest.fixture
def finance_results():
    frame={'date':['2024-02-01','2024-03-01'],'amount':['1.1','1.4'],'region':['North','North']}
    return [kpi({'amount':['1','2']}), period(frame), period(frame, name='contribution_analysis', dimension='region')]


def test_valid_typed_finance_optional_explanations_are_not_missing_statistics(finance_results):
    for result in finance_results:
        assert not missing(result.model_dump(mode='json'))


def test_valid_forecast_optional_diagnostics_are_not_missing_statistics(forecast_result):
    data=forecast_result.model_dump(mode='json')
    assert any(candidate['error_code'] is None for candidate in data['candidates'])
    assert not missing(data)


@pytest.mark.parametrize('coverage', [False, True])
def test_undefined_finance_values_still_warn(coverage):
    frame={'date':['2024-03-01'] if coverage else ['2024-02-01','2024-03-01'],
           'amount':['1'] if coverage else ['0','1']}
    data=period(frame).model_dump(mode='json')
    assert data['growth_rate']['value'] is None
    # Present current period remains valid; previous/delta/growth are unavailable.
    assert missing(data)[0].count == (3 if coverage else 1)


def test_zero_target_mape_is_a_missing_statistic():
    from app.analysis.catalog import build_registry
    from app.analysis.context import DatasetContext
    frame=pd.DataFrame({'date':pd.date_range('2024-01-01',periods=24,freq='MS'),'value':[0]*24})
    data=build_registry().calculate('forecast',DatasetContext.from_frame(frame),{'time_column':'date','target_column':'value','horizon':3,'granularity':'month','aggregation':'sum'}).data.model_dump(mode='json')
    assert data['metrics']['mape'] is None
    assert missing(data)[0].count > 0


def test_null_frame_cells_still_warn_despite_valid_typed_result(finance_results):
    assert missing(finance_results[1].model_dump(mode='json'),pd.DataFrame({'cell':[None,None]}))[0].count == 2


def test_failed_forecast_candidate_absent_score_is_diagnostic(forecast_result):
    data=deepcopy(forecast_result.model_dump(mode='json'))
    candidate=next(c for c in data['candidates'] if c['model'] not in {'naive',data['selected_model']})
    candidate.update(status='failed',metrics=None,folds=[],error_code='MODEL_FIT_FAILED')
    from app.analysis.models import ForecastResult
    ForecastResult.model_validate(data)
    assert not missing(data)


def test_nonfinite_nested_diagnostic_still_rejected(forecast_result):
    data=deepcopy(forecast_result.model_dump(mode='json'))
    data['baseline']['validation_error_code']=float('inf')
    with pytest.raises(ResultValidationError,match='RESULT_NON_FINITE'):
        validate_result(data)


@pytest.mark.parametrize('field',['currency','unit','dataset_version'])
def test_nonfinite_metadata_still_rejected_everywhere(forecast_result,field):
    data=deepcopy(forecast_result.model_dump(mode='json'));data[field]=float('inf')
    with pytest.raises(ResultValidationError,match='RESULT_NON_FINITE'):
        validate_result(data)


@pytest.mark.parametrize('data',[
    {'explanation':None}, {'kind':'forecast','error_code':None},
    {'kind':'period_comparison','current':{'value':'1','explanation':None}},
    {'kind':'legacy','metrics':{'mape':None},'explanation':None},
    {'kind':[],'explanation':None},
])
def test_legacy_or_unvalidated_shapes_keep_null_warning(data):
    assert missing(data)[0].count >= 1
