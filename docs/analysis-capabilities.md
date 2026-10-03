# Analysis capabilities

Generated from `app.analysis.catalog.build_registry`; all canonical registrations are exercised by `test_tool_catalog_contracts.py`.

Available means implemented and covered by automated execution tests. It does not claim real MySQL or live model verification.

| Tool | Category | Input | Output | Chat | Version | Status |
|---|---|---|---|---|---|---|
| `dataset_overview` | data | `DataInput` | `OverviewResult` | read-only | 3.0 | Available |
| `column_summary` | data | `DataInput` | `TableResult` | read-only | 3.0 | Available |
| `select_columns` | data | `DataInput` | `TableResult` | read-only | 3.0 | Available |
| `filter_rows` | data | `DataInput` | `TableResult` | read-only | 3.0 | Available |
| `sort_rows` | data | `DataInput` | `TableResult` | read-only | 3.0 | Available |
| `sample_rows` | data | `DataInput` | `TableResult` | read-only | 3.0 | Available |
| `unique_values` | data | `DataInput` | `TableResult` | read-only | 3.0 | Available |
| `value_counts` | data | `DataInput` | `TableResult` | read-only | 3.0 | Available |
| `aggregate` | aggregation | `AggregationInput` | `AggregationResult` | read-only | 3.0 | Available |
| `multi_aggregate` | aggregation | `AggregationInput` | `AggregationResult` | read-only | 3.0 | Available |
| `groupby_aggregate` | aggregation | `AggregationInput` | `AggregationResult` | read-only | 3.0 | Available |
| `pivot_table` | aggregation | `PivotInput` | `AggregationResult` | read-only | 3.0 | Available |
| `crosstab` | aggregation | `PivotInput` | `AggregationResult` | read-only | 3.0 | Available |
| `rank` | aggregation | `RankInput` | `TableResult` | read-only | 3.0 | Available |
| `top_n` | aggregation | `RankInput` | `TableResult` | read-only | 3.0 | Available |
| `bottom_n` | aggregation | `RankInput` | `TableResult` | read-only | 3.0 | Available |
| `percentage_share` | aggregation | `RatioInput` | `AggregationResult` | read-only | 3.0 | Available |
| `weighted_average` | aggregation | `RatioInput` | `StatisticsResult` | read-only | 3.0 | Available |
| `cumulative_sum` | time_series | `SequenceInput` | `AggregationResult` | read-only | 3.0 | Available |
| `percentage_change` | time_series | `SequenceInput` | `AggregationResult` | read-only | 3.0 | Available |
| `growth_rate` | time_series | `SequenceInput` | `AggregationResult` | read-only | 3.0 | Available |
| `rolling_statistics` | time_series | `SequenceInput` | `AggregationResult` | read-only | 3.0 | Available |
| `descriptive_statistics` | statistics | `StatisticsInput` | `StatisticsResult` | read-only | 3.0 | Available |
| `percentile` | statistics | `StatisticsInput` | `StatisticsResult` | read-only | 3.0 | Available |
| `quantile` | statistics | `StatisticsInput` | `StatisticsResult` | read-only | 3.0 | Available |
| `variance` | statistics | `StatisticsInput` | `StatisticsResult` | read-only | 3.0 | Available |
| `standard_deviation` | statistics | `StatisticsInput` | `StatisticsResult` | read-only | 3.0 | Available |
| `skewness` | statistics | `StatisticsInput` | `StatisticsResult` | read-only | 3.0 | Available |
| `kurtosis` | statistics | `StatisticsInput` | `StatisticsResult` | read-only | 3.0 | Available |
| `correlation` | statistics | `StatisticsInput` | `CorrelationResult` | read-only | 3.0 | Available |
| `covariance` | statistics | `StatisticsInput` | `StatisticsResult` | read-only | 3.0 | Available |
| `missing_value_analysis` | data | `QualityInput` | `DataQualityResult` | read-only | 3.0 | Available |
| `duplicate_analysis` | data | `QualityInput` | `DataQualityResult` | read-only | 3.0 | Available |
| `constant_column_analysis` | data | `QualityInput` | `DataQualityResult` | read-only | 3.0 | Available |
| `cardinality_analysis` | data | `QualityInput` | `DataQualityResult` | read-only | 3.0 | Available |
| `invalid_numeric_analysis` | data | `QualityInput` | `DataQualityResult` | read-only | 3.0 | Available |
| `invalid_datetime_analysis` | data | `QualityInput` | `DataQualityResult` | read-only | 3.0 | Available |
| `infinite_value_analysis` | data | `QualityInput` | `DataQualityResult` | read-only | 3.0 | Available |
| `outlier_analysis` | eda | `QualityInput` | `DataQualityResult` | read-only | 3.0 | Available |
| `fill_missing_values` | cleaning | `CleaningInput` | `CleaningResult` | internal only | 3.0 | Available |
| `drop_missing_rows` | cleaning | `CleaningInput` | `CleaningResult` | internal only | 3.0 | Available |
| `remove_duplicates` | cleaning | `CleaningInput` | `CleaningResult` | internal only | 3.0 | Available |
| `convert_dtype` | cleaning | `CleaningInput` | `CleaningResult` | internal only | 3.0 | Available |
| `parse_datetime` | cleaning | `CleaningInput` | `CleaningResult` | internal only | 3.0 | Available |
| `replace_values` | cleaning | `CleaningInput` | `CleaningResult` | internal only | 3.0 | Available |
| `normalize_text` | cleaning | `CleaningInput` | `CleaningResult` | internal only | 3.0 | Available |
| `rename_columns` | cleaning | `CleaningInput` | `CleaningResult` | internal only | 3.0 | Available |
| `outlier_treatment` | cleaning | `CleaningInput` | `CleaningResult` | internal only | 3.0 | Available |
| `chart_spec` | visualization | `ChartInput` | `ChartResult` | internal only | 3.0 | Available |
| `chart_recommendations` | visualization | `DataInput` | `RecommendationResult` | read-only | 3.0 | Available |
| `eda` | eda | `DataInput` | `EDAResult` | read-only | 3.0 | Available |

## Compatibility adapters

Old names and parameters retain their established response fields; SQL additionally requires READ_DATABASE and a configured read-only connection.

| Adapter | Input | Output | Version |
|---|---|---|---|
| `get_dataset_info` | `DatasetInfoArgs` | `LegacyResult` | 3.0 |
| `preview_data` | `PreviewArgs` | `LegacyResult` | 3.0 |
| `filter_data` | `FilterArgs` | `LegacyResult` | 3.0 |
| `aggregate_data` | `AggregateArgs` | `LegacyResult` | 3.0 |
| `group_by_analysis` | `GroupByArgs` | `LegacyResult` | 3.0 |
| `sort_data` | `SortArgs` | `LegacyResult` | 3.0 |
| `sql_query` | `SqlQueryArgs` | `LegacyResult` | 3.0 |
| `generate_chart` | `ChartArgs` | `LegacyChartResult` | 3.0 |
| `describe_data` | `DescribeArgs` | `LegacyResult` | 3.0 |
| `time_group_analysis` | `TimeGroupArgs` | `LegacyResult` | 3.0 |
| `growth_analysis` | `GrowthArgs` | `LegacyResult` | 3.0 |

## Deferred

Phase 2.5: Kendall, normality tests, t tests, chi-square and ANOVA are not registered or advertised as Available.

Phase 3: more advanced planning, persistent multi-turn state, streaming and task lifecycle extensions require a separately approved scope.

Future: dynamic Python, sandbox execution, report export, a cache platform, machine learning and new infrastructure are not implemented.
