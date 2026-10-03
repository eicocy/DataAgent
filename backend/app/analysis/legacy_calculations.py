"""Compatibility calculations; context loading and orchestration stay in services."""
from __future__ import annotations
import math
import json
import time
from datetime import date,datetime
import pandas as pd
from sqlalchemy import text
from app.analysis.legacy_inputs import *
from app.analysis.serialization import json_value as _json_value, records as _records
from app.analysis.operations import filtered, aggregate_series, sorted_frame
from app.analysis.sql_safety import validate_readonly_query
from app.execution.validators import validate_numeric_series
from app.analysis.errors import ToolInputError
MAX_RESULT_ROWS=500


def _aggregation(series,operation):
    return aggregate_series(series, {'avg':'mean','count_distinct':'nunique'}.get(operation,operation))


class LegacyCalculations:
    def _check_column(self, column: str) -> None:
        if column not in self.schema:
            raise ToolInputError('COLUMN_NOT_FOUND')


    def _filtered(self, frame, conditions, logic="and"):
        return filtered(frame, conditions, logic)


    def get_dataset_info(self, args: DatasetInfoArgs) -> dict[str, Any]:
        return {
            "dataset": {"id": self.dataset.id, "name": self.dataset.original_name, "row_count": len(self.frame) if self.frame is not None else self.dataset.row_count, "column_count": len(self.schema), "file_type": self.dataset.file_type},
            "columns": [
                {"name": c.name, "label": c.original_name, "data_type": c.data_type, "nullable": c.nullable,
                 "missing_count": c.missing_count, "unique_count": c.unique_count,
                 **({"sample_values": c.sample_values_json or []} if args.include_samples else {})}
                for c in self.columns
            ],
            "missing_summary": {c.name: c.missing_count for c in self.columns if c.missing_count},
        }


    def preview_data(self, args: PreviewArgs) -> dict[str, Any]:
        frame = self._frame()
        names = args.columns or list(frame.columns)
        for name in names:
            self._check_column(name)
        chunk = frame.loc[:, names].iloc[args.offset:args.offset + args.limit]
        self._output_frame = frame.loc[:, names].copy()
        return {"columns": names, "rows": _records(chunk), "offset": args.offset, "limit": args.limit, "total_rows": len(frame)}


    def filter_data(self, args: FilterArgs) -> dict[str, Any]:
        frame = self._frame()
        matched = self._filtered(frame, args.conditions, args.logic)
        self._output_frame = matched.copy()
        return {"matched_count": len(matched), "preview_rows": _records(matched.head(args.limit)), "applied_conditions": [condition.model_dump() for condition in args.conditions]}


    def aggregate_data(self, args: AggregateArgs) -> dict[str, Any]:
        frame = self._filtered(self._frame(), args.filters)
        values = {f"{metric.column}_{metric.aggregation}": _json_value(_aggregation(frame[metric.column], metric.aggregation)) for metric in args.metrics if self._check_column(metric.column) is None}
        if args.date_column is None:
            self._output_frame = pd.DataFrame([values])
            return {"metric_values": values, "row_count": len(frame)}
        self._check_column(args.date_column)
        if args.frequency is None:
            raise ValueError("frequency is required when date_column is set")
        dates = pd.to_datetime(frame[args.date_column], errors="coerce")
        rule = {"day": "D", "week": "W-MON", "month": "M", "quarter": "Q", "year": "Y"}[args.frequency]
        time_frame = frame.loc[dates.notna()].copy()
        time_frame["__period"] = dates[dates.notna()].dt.to_period(rule).dt.start_time
        grouped = time_frame.groupby("__period", dropna=False)
        rows = []
        for period, group in grouped:
            row = {args.date_column: pd.Timestamp(period).date().isoformat()}
            row.update({f"{metric.column}_{metric.aggregation}": _json_value(_aggregation(group[metric.column], metric.aggregation)) for metric in args.metrics})
            rows.append(row)
        self._output_frame = pd.DataFrame(rows, columns=[args.date_column, *values.keys()])
        return {"columns": [args.date_column, *values.keys()], "rows": rows[:MAX_RESULT_ROWS], "row_count": len(rows), "frequency": args.frequency}


    def group_by_analysis(self, args: GroupByArgs) -> dict[str, Any]:
        from app.analysis.context import DatasetContext
        from app.analysis.inputs import AggregationInput
        from app.analysis.aggregation_tools import aggregate
        metric_name = f"{args.value_column}_{args.aggregation}"
        context=getattr(self,'_execution_context',None) or DatasetContext.from_frame(self._frame())
        parameters=AggregationInput(dimensions=args.group_columns,metrics=[{'column':args.value_column,'aggregation':{'avg':'mean','count_distinct':'nunique'}.get(args.aggregation,args.aggregation),'alias':metric_name}],sort=[{'column':metric_name,'direction':args.sort}],limit=args.limit,drop_missing=args.drop_missing)
        output=aggregate(context,parameters,True)
        self._output_frame=output.frame
        rows=output.data.rows
        return {'columns':[*args.group_columns,metric_name],'rows':rows,'group_count':output.data.row_count,'value_label':self.schema[args.value_column].original_name,'row_count':len(rows),'truncated':output.data.truncated}


    def sort_data(self, args: SortArgs) -> dict[str, Any]:
        frame = self._filtered(self._frame(), args.filters)
        names = args.columns or list(frame.columns)
        sort_names = [entry.column for entry in args.sort_by]
        for name in set(names + sort_names):
            self._check_column(name)
        ordered = sorted_frame(frame,args.sort_by)
        self._output_frame = ordered.loc[:, names].copy()
        return {"sorted_rows": _records(ordered.loc[:, names].head(args.limit)), "total_after_filter": len(frame)}


    def sql_query(self, args: SqlQueryArgs) -> dict[str, Any]:
        if self.readonly_bind is None:
            raise RuntimeError("read-only SQL connection is not configured")
        sql = validate_readonly_query(args.query, self.dataset.id, set(self.schema), args.max_rows)
        physical=getattr(self,'projection_table',None) or getattr(self.dataset,'projection_table',None) or f'dataset_{self.dataset.id}'
        if physical!=f'dataset_{self.dataset.id}':
            import re,sqlglot
            if not re.fullmatch(rf'dataset_{self.dataset.id}_v_[a-f0-9]{{32}}',physical): raise ValueError('invalid server projection name')
            tree=sqlglot.parse_one(sql,read='mysql')
            table=next(tree.find_all(sqlglot.exp.Table))
            original=table.alias_or_name
            table.set('this',sqlglot.exp.to_identifier(physical,quoted=True))
            if not table.alias: table.set('alias',sqlglot.exp.TableAlias(this=sqlglot.exp.to_identifier(original)))
            sql=tree.sql(dialect='mysql')
        started = time.perf_counter()
        with self.readonly_bind.connect() as connection:
            if connection.dialect.name == "mysql":
                connection.exec_driver_sql("SET SESSION MAX_EXECUTION_TIME = 5000")
            result = connection.execute(text(sql))
            rows = result.mappings().all()
            names = list(result.keys())
        duration_ms = int((time.perf_counter() - started) * 1000)
        self._output_frame = pd.DataFrame([dict(row) for row in rows], columns=names,dtype=object)
        for name in names:
            values=[row[name] for row in rows]
            valid=[value for value in values if value is not None]
            if valid and all(isinstance(value,int) and not isinstance(value,bool) for value in valid):
                self._output_frame[name]=pd.array(values,dtype='Int64')
        if len(json.dumps(_records(self._output_frame), ensure_ascii=False).encode()) > 2 * 1024 * 1024:
            raise ValueError('SQL result exceeds byte budget')
        return {"columns": names, "rows": [{key: _json_value(value) for key, value in row.items()} for row in rows], "row_count": len(rows), "truncated": len(rows) >= args.max_rows, "duration_ms": duration_ms}


    def generate_chart(self, args: ChartArgs) -> dict[str, Any]:
        source = self.call_results.get(args.source_tool_call_id)
        if source is None:
            raise ValueError("source_tool_call_id does not reference a completed tool result")
        full_frame = self.frame_results.get(args.source_tool_call_id)
        if full_frame is not None and args.group_column and args.selected_groups is not None:
            if args.group_column not in full_frame.columns:
                raise ValueError('chart group field is missing')
            full_frame = full_frame.loc[full_frame[args.group_column].isin(args.selected_groups)]
        columns = list(full_frame.columns) if full_frame is not None else source.get("columns") or (list(source["rows"][0]) if source.get("rows") else [])
        rows = _records(full_frame) if full_frame is not None else source.get("rows") or source.get("preview_rows") or source.get("sorted_rows") or []
        if not rows:
            raise ValueError('chart source is empty')
        if args.dimension not in columns or any(metric.field not in columns for metric in args.metrics):
            raise ToolInputError('CHART_COLUMN_NOT_FOUND')
        if args.type == "pie" and (len(args.metrics) != 1 or len(rows) > 20):
            raise ValueError("pie charts require one metric and at most 20 categories")
        dimension_values = pd.Series([row[args.dimension] for row in rows])
        date_like = pd.to_datetime(dimension_values, errors='coerce', format='mixed').notna().all() if not pd.api.types.is_numeric_dtype(dimension_values) else False
        if args.type == "line" and not date_like and not pd.api.types.is_numeric_dtype(dimension_values) and self.schema.get(args.dimension) and self.schema[args.dimension].data_type not in {"date", "datetime", "integer", "decimal"}:
            raise ValueError("line chart dimension must be ordered or date-like")
        for metric in args.metrics:
            for row in rows:
                raw = row[metric.field]
                if raw is None or raw == '':
                    row[metric.field] = None
                    continue
                if isinstance(raw, bool):
                    raise ValueError('chart metrics must be numeric')
                try:
                    number = float(raw)
                except (TypeError, ValueError):
                    raise ValueError('chart metrics must be numeric') from None
                if not math.isfinite(number) or (args.type == 'pie' and number < 0):
                    raise ValueError('invalid chart numeric value')
                row[metric.field] = number
        if args.type in {'line', 'scatter'}:
            rows.sort(key=lambda row: (row[args.dimension] is None, str(row[args.dimension]) if date_like else row[args.dimension]))
        if args.type == 'histogram':
            values = pd.Series([row[args.metrics[0].field] for row in rows]).dropna()
            if values.empty:
                raise ValueError('histogram requires numeric values')
            buckets = pd.cut(values, bins=args.bins).value_counts(sort=False)
            rows = [{args.dimension: str(interval), args.metrics[0].field: int(count)} for interval, count in buckets.items()]
        if len(rows) > 500:
            raise ValueError('chart exceeds 500 point budget')
        series = []
        groups = [None]
        if args.group_column:
            if args.group_column not in columns:
                raise ValueError('chart group field is missing')
            groups = args.selected_groups if args.selected_groups is not None else list(dict.fromkeys(row[args.group_column] for row in rows))
            if len(groups) > 20:
                raise ValueError('chart exceeds series budget')
        for group in groups:
            for metric in args.metrics:
                series_rows = [row for row in rows if group is None or row[args.group_column] == group]
                points = [{"name": _json_value(row[args.dimension]), "value": _json_value(row[metric.field])} for row in series_rows]
                if args.type == 'scatter':
                    points = [{'name': point['name'], 'value': [float(point['name']), point['value']]} for point in points if point['name'] is not None and point['value'] is not None]
                series.append({"name": str(group) if group is not None else metric.label or metric.field, "data": points})
        dimension_type = "category"
        if date_like and args.type != 'histogram':
            dimension_type = 'time'
        if args.dimension in self.schema:
            data_type = self.schema[args.dimension].data_type
            if data_type in {"date", "datetime"}:
                dimension_type = "time"
            elif data_type in {"integer", "decimal"}:
                dimension_type = "value"
        return {
            "version": "1.0", "type": args.type, "title": args.title,
            "dimension": {"field": args.dimension, "label": self.schema.get(args.dimension).original_name if args.dimension in self.schema else args.dimension, "type": dimension_type},
            "metrics": [{"field": item.field, "label": item.label or item.field, "aggregation": item.field.rsplit("_", 1)[-1], "unit": item.unit} for item in args.metrics],
            "series": series, "source_tool_call_id": args.source_tool_call_id, "notes": [],
        }


    def describe_data(self, args: DescribeArgs) -> dict[str, Any]:
        frame = self._frame()
        names = args.columns or list(frame.select_dtypes(include='number').columns)
        for name in names:
            self._check_column(name)
            if not pd.api.types.is_numeric_dtype(frame[name]):
                raise ValueError('description requires numeric fields')
            validate_numeric_series(frame[name])
        result = frame[names].describe().transpose().reset_index(names='field')
        self._output_frame = result
        return {'columns': list(result.columns), 'rows': _records(result), 'row_count': len(result)}


    def _monthly(self, args: TimeGroupArgs) -> tuple[pd.DataFrame, pd.Period, pd.Period, int]:
        frame = self._frame()
        for name in [args.date_column, args.group_column, args.value_column]:
            self._check_column(name)
        dates = pd.to_datetime(frame[args.date_column], errors='coerce')
        if not dates.notna().any():
            raise ValueError('no valid dates')
        last = dates.max().to_period('M')
        first = last - (args.months - 1)
        months = dates.dt.to_period('M')
        selected = frame.loc[months.between(first, last) & frame[args.group_column].notna()].copy()
        selected[args.date_column] = months.loc[selected.index].dt.start_time
        numeric = pd.to_numeric(selected[args.value_column], errors='coerce')
        if (selected[args.value_column].notna() & numeric.isna()).any():
            raise ValueError('value field must be numeric')
        selected[args.value_column] = numeric
        validate_numeric_series(selected[args.value_column])
        monthly = selected.groupby([args.date_column, args.group_column], dropna=False)[args.value_column].agg(lambda values: _aggregation(values, 'sum')).reset_index()
        return monthly, first, last, int((frame[args.date_column].notna() & dates.isna()).sum())


    def time_group_analysis(self, args: TimeGroupArgs) -> dict[str, Any]:
        result, first, last, invalid = self._monthly(args)
        groups = list(dict.fromkeys(result[args.group_column].tolist()))
        from app.config import get_settings
        if len(groups) * args.months * 256 > get_settings().dataframe_max_bytes:
            raise ValueError('monthly grid exceeds memory budget')
        grid = pd.MultiIndex.from_product([pd.period_range(first, last, freq='M').to_timestamp(), groups], names=[args.date_column, args.group_column])
        result = result.set_index([args.date_column, args.group_column]).reindex(grid).reset_index()
        result = result.rename(columns={args.value_column: args.value_column + '_sum'})
        self._output_frame = result
        return {'columns': list(result.columns), 'rows': _records(result.head(200)), 'row_count': len(result), 'window_start': str(first), 'window_end': str(last), 'invalid_date_count': invalid}


    def growth_analysis(self, args: GrowthArgs) -> dict[str, Any]:
        monthly, first, last, invalid = self._monthly(args)
        rows, excluded = [], []
        for group, values in monthly.groupby(args.group_column, sort=False):
            periods = values[args.date_column].dt.to_period('M')
            start = values.loc[periods.eq(first), args.value_column]
            end = values.loc[periods.eq(last), args.value_column]
            if start.empty or end.empty or pd.isna(start.iloc[0]) or pd.isna(end.iloc[0]) or start.iloc[0] <= 0:
                excluded.append(_json_value(group))
                continue
            a, b = float(start.iloc[0]), float(end.iloc[0])
            rows.append({args.group_column: _json_value(group), 'first_month_value': a, 'last_month_value': b, 'absolute_growth': b - a, 'growth_rate': (b - a) / a})
        rows.sort(key=lambda row: (-row['growth_rate'], -row['absolute_growth'], str(row[args.group_column])))
        result = pd.DataFrame(rows[:args.top_n], columns=[args.group_column, 'first_month_value', 'last_month_value', 'absolute_growth', 'growth_rate'])
        self._output_frame = result
        return {'columns': list(result.columns), 'rows': _records(result), 'row_count': len(result), 'selected_groups': result[args.group_column].tolist(), 'excluded_count': len(excluded), 'excluded_groups': excluded, 'invalid_date_count': invalid, 'window_start': str(first), 'window_end': str(last)}
