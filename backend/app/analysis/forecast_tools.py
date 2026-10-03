"""Bounded, univariate forecasts with chronological out-of-sample evaluation.

No imputation, shuffled splits, hyperparameter search, or silent truncation.
At most 1000 regular periods, five candidates, three folds and one final fit
per eligible candidate. ARIMA uses a fixed (1,1,0) order / 50 iterations.
"""
import warnings
from numbers import Number

import numpy as np
import pandas as pd

from app.analysis.errors import ToolInputError, ToolExecutionError
from app.analysis.models import (
    ForecastCandidate, ForecastFold, ForecastFoldScore, ForecastMetrics,
    ForecastPoint, ForecastResult, ForecastUncertainty,
)
from app.analysis.registry import ToolOutput


PERIODS = {'day': ('D', 'D'), 'week': ('W-SUN', 'W-MON'),
           'month': ('M', 'MS'), 'quarter': ('Q-DEC', 'QS'), 'year': ('Y-DEC', 'YS')}
MODELS = ('naive', 'moving_average', 'linear_trend', 'exponential_smoothing', 'arima')


def _history(context, args):
    context.columns([args.time_column, args.target_column])
    context.check_size(context.frame)
    dates = context.frame[args.time_column]
    if (dates.isna().any() or pd.api.types.is_numeric_dtype(dates.dtype)
            or any(isinstance(value, (Number, bool, np.bool_)) for value in dates)):
        raise ToolInputError('FORECAST_INVALID_DATE')
    try:
        dates = pd.to_datetime(dates, errors='raise', format='mixed')
        if dates.isna().any():
            raise ToolInputError('FORECAST_INVALID_DATE')
        if dates.dt.tz is not None:
            raise ValueError('timezone must be normalized explicitly')
        periods = dates.dt.to_period(PERIODS[args.granularity][0])
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise ToolInputError('FORECAST_INVALID_DATE') from None
    target = context.frame[args.target_column]
    if target.isna().any():
        raise ToolInputError('FORECAST_MISSING_TARGET')
    if (pd.api.types.is_bool_dtype(target.dtype) or pd.api.types.is_complex_dtype(target.dtype)
            or pd.api.types.is_datetime64_any_dtype(target.dtype) or pd.api.types.is_timedelta64_dtype(target.dtype)
            or any(isinstance(v, (bool, np.bool_, complex, pd.Timestamp, pd.Timedelta)) for v in target)):
        raise ToolInputError('FORECAST_INVALID_TARGET')
    try:
        values = pd.to_numeric(target, errors='raise').astype(float)
    except (ValueError, TypeError, OverflowError):
        raise ToolInputError('FORECAST_INVALID_TARGET') from None
    if not np.isfinite(values).all():
        raise ToolInputError('FORECAST_NON_FINITE_TARGET')
    history = pd.DataFrame({'period': periods.to_numpy(), 'value': values.to_numpy()}).groupby('period', sort=True)['value'].agg(args.aggregation)
    if not np.isfinite(history).all():
        raise ToolInputError('FORECAST_NON_FINITE_AGGREGATE')
    if len(history) < 12:
        raise ToolInputError('FORECAST_INSUFFICIENT_OBSERVATIONS', details={'observations': len(history), 'minimum': 12})
    if len(history) > 1000:
        raise ToolInputError('FORECAST_HISTORY_BUDGET_EXCEEDED', details={'observations': len(history), 'maximum': 1000})
    if (np.diff(history.index.asi8) != 1).any():
        raise ToolInputError('FORECAST_IRREGULAR_PERIODS', suggestion='按声明的周期补齐并核实数据后重新预测，工具不会自动补零')
    if len(history) - 3 * args.horizon < 3:
        raise ToolInputError('FORECAST_INSUFFICIENT_VALIDATION_HISTORY', details={'observations': len(history), 'required': 3 + 3 * args.horizon})
    return history


def _predict(model, train, horizon):
    if model == 'naive':
        predicted = np.repeat(train[-1], horizon)
    elif model == 'moving_average':
        predicted = np.repeat(np.mean(train[-3:]), horizon)
    elif model == 'linear_trend':
        slope, intercept = np.polyfit(np.arange(len(train), dtype=float), train, 1)
        predicted = intercept + slope * np.arange(len(train), len(train) + horizon)
    elif model == 'exponential_smoothing':
        # Constant series need no numerical optimization; exact SES fixed point.
        if np.ptp(train) == 0:
            predicted = np.repeat(train[-1], horizon)
        else:
            from statsmodels.tsa.holtwinters import SimpleExpSmoothing
            fitted = SimpleExpSmoothing(train, initialization_method='estimated').fit(optimized=True, minimize_kwargs={'options': {'maxiter': 100}})
            if not fitted.mle_retvals.success:
                raise ToolExecutionError('FORECAST_MODEL_NOT_CONVERGED')
            predicted = fitted.forecast(horizon)
    else:
        from statsmodels.tsa.arima.model import ARIMA
        fitted = ARIMA(train, order=(1, 1, 0), enforce_stationarity=True, enforce_invertibility=True).fit(method_kwargs={'maxiter': 50})
        if not fitted.mle_retvals.get('converged', False):
            raise ToolExecutionError('FORECAST_MODEL_NOT_CONVERGED')
        predicted = fitted.forecast(horizon)
    predicted = np.asarray(predicted, dtype=float)
    if predicted.shape != (horizon,) or not np.isfinite(predicted).all():
        raise ToolExecutionError('FORECAST_NON_FINITE_PREDICTION')
    return predicted


def _metrics(actual, predicted):
    residual = actual - predicted
    nonzero = actual != 0
    scale = float(np.max(np.abs(residual)))
    rmse = 0.0 if scale == 0 else scale * float(np.sqrt(np.mean((residual / scale) ** 2)))
    return ForecastMetrics(mae=float(np.mean(np.abs(residual))), rmse=rmse,
        mape=float(np.mean(np.abs(residual[nonzero] / actual[nonzero])) * 100) if nonzero.any() else None,
        mape_coverage=float(np.mean(nonzero)),
        mape_explanation='MAPE uses nonzero held-out actuals only; zero targets are excluded. Null means no nonzero held-out actuals. Coverage is the included fraction.')


def forecast(context, args):
    history = _history(context, args)
    values = history.to_numpy(dtype=float)
    times = history.index.to_timestamp()
    horizon = args.horizon
    folds = []
    for fold_id in range(3):
        end = len(values) - (3 - fold_id) * horizon
        folds.append(ForecastFold(fold_id=fold_id, train_start=times[0].isoformat(), train_end=times[end-1].isoformat(),
            test_start=times[end].isoformat(), test_end=times[end+horizon-1].isoformat(), train_size=end, test_size=horizon))
    candidates, residuals, final_predictions = [], {}, {}
    for model in MODELS:
        candidate = ForecastCandidate(model=model, status='skipped', error_code='FORECAST_MODEL_INELIGIBLE')
        if model == 'arima' and (folds[0].train_size < 12 or np.ptp(values[:folds[0].train_size]) == 0):
            candidates.append(candidate)
            continue
        stage = 'validation'
        try:
            predictions, actuals, scores = [], [], []
            # Numerical/convergence warnings invalidate a candidate, never suppress them silently.
            with warnings.catch_warnings():
                warnings.simplefilter('error')
                for fold in folds:
                    end = fold.train_size
                    predicted = _predict(model, values[:end].copy(), horizon)
                    actual = values[end:end+horizon]
                    scores.append(ForecastFoldScore(fold_id=fold.fold_id, predictions=predicted.tolist(), metrics=_metrics(actual, predicted)))
                    predictions.extend(predicted)
                    actuals.extend(actual)
                actuals, predictions = np.asarray(actuals), np.asarray(predictions)
                metrics = _metrics(actuals, predictions)
                stage = 'final_fit'
                final_predictions[model] = _predict(model, values.copy(), horizon)
            residuals[model] = actuals - predictions
            candidate = ForecastCandidate(model=model, status='succeeded', metrics=metrics, folds=scores)
        except (Exception,) as exc:
            code = exc.code if isinstance(exc, ToolExecutionError) else 'FORECAST_MODEL_NUMERICAL_WARNING' if isinstance(exc, Warning) else 'FORECAST_MODEL_FIT_FAILED'
            candidate = ForecastCandidate(model=model, status='failed', error_code=code,
                validation_error_code=code if stage == 'validation' else None,
                final_fit_error_code=code if stage == 'final_fit' else None,
                folds=scores, metrics=metrics if stage == 'final_fit' else None)
        candidates.append(candidate)
    if candidates[0].status != 'succeeded':
        raise ToolExecutionError('FORECAST_BASELINE_FAILED', details={'reason': candidates[0].error_code})
    # Round only comparison keys to avoid numerical noise changing exact-zero ties.
    selected = min((c for c in candidates if c.status == 'succeeded'), key=lambda c: (round(c.metrics.mae, 10), round(c.metrics.rmse, 10), MODELS.index(c.model)))
    with warnings.catch_warnings():
        warnings.simplefilter('error', RuntimeWarning)
        width = float(np.quantile(np.abs(residuals[selected.model]), .9))
        future = pd.period_range(history.index[-1] + 1, periods=horizon, freq=history.index.freq).to_timestamp()
        points = [ForecastPoint(time=t.isoformat(), value=float(v), lower=float(v-width), upper=float(v+width)) for t, v in zip(future, final_predictions[selected.model])]
    return ToolOutput(ForecastResult(dataset_id=context.dataset_id, dataset_version=context.dataset_version, source_ref=context.source_ref,
        time_column=args.time_column, target_column=args.target_column, aggregation=args.aggregation, granularity=args.granularity,
        frequency=PERIODS[args.granularity][1], history_start=times[0].isoformat(), history_end=times[-1].isoformat(),
        observation_count=len(values), input_row_count=len(context.frame), horizon=horizon, selected_model=selected.model, metrics=selected.metrics,
        folds=folds, baseline=candidates[0], candidates=candidates, points=points,
        uncertainty=ForecastUncertainty(residual_quantile=.9, residual_count=len(residuals[selected.model]),
            limitations='Symmetric empirical bounds from the selected model held-out absolute residual 90th percentile. Not calibrated confidence or prediction intervals; model selection reuses these folds. Small samples, horizon effects and regime changes can reduce coverage; zero errors can yield zero width.'),
        limitations=['Univariate, nonseasonal forecasts; no external variables or causal claims.',
            'Calendar periods start on day/Monday/month/quarter/year boundaries; duplicates aggregate by the declared rule; no missing-period imputation.',
            'Three expanding chronological folds use the requested forecast horizon. MAE selects the model; RMSE breaks ties; near-equal numerical ties retain the simpler candidate.',
            'Maximum 1000 periods, 24-step horizon, five candidates; fixed ARIMA(1,1,0), at most 50 optimizer iterations; SES at most 100.']))
