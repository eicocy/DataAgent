# Tool 体系设计

## 通用协议

所有 Tool 使用 Pydantic 输入，输出 `{success, data, summary, metadata, error}`。通用输入隐式包含经 Service 注入的 `DatasetHandle`，LLM 不能传文件路径或 owner_id。错误分为 validation、permission、data_quality、execution、timeout。

## 1. get_dataset_info

- 场景：回答行列数、字段和数据质量。
- 参数：`include_samples: bool=false`。
- 输出：dataset 元信息、columns、missing_summary。
- 示例：`{"include_samples":true}`。

## 2. preview_data

- 场景：查看有限行数据。
- 参数：`offset: int>=0`、`limit: int=1..100`、`columns: list[str]?`。
- 输出：columns、rows、offset、limit、total_rows。
- 示例：`{"offset":0,"limit":10,"columns":["region","sales"]}`。

## 3. filter_data

- 场景：按条件筛选记录。
- 参数：`conditions: [{column, operator, value}]`、`logic: and|or`、`limit<=500`。
- operator 白名单：eq/ne/gt/gte/lt/lte/in/contains/between/is_null。
- 输出：matched_count、preview_rows、applied_conditions。
- 示例：`{"conditions":[{"column":"sales","operator":"gt","value":5000}],"logic":"and","limit":100}`。

## 4. aggregate_data

- 场景：整体或时间维度指标。
- 参数：`metrics: [{column, aggregation}]`、`date_column?`、`frequency?: day|week|month|quarter|year`、`filters?`。
- aggregation：sum/avg/min/max/count/count_distinct。
- 输出：metric_values 或 time_series。
- 示例：`{"metrics":[{"column":"sales","aggregation":"sum"}],"date_column":"order_date","frequency":"month"}`。

## 5. group_by_analysis

- 场景：按类别比较指标。
- 参数：`group_columns: list[str]`（长度 1–2）、`value_column`、`aggregation`、`sort`、`limit<=100`、`drop_missing=true`。
- 输出：rows、group_count、value_label。
- 示例：`{"group_columns":["region"],"value_column":"sales","aggregation":"sum","sort":"desc","limit":20}`。

## 6. sort_data

- 场景：查找最高/最低记录。
- 参数：`sort_by: [{column,direction}]`、`columns?`、`limit<=100`、`filters?`。
- 输出：sorted_rows、total_after_filter。
- 示例：`{"sort_by":[{"column":"sales","direction":"desc"}],"limit":10}`。

## 7. sql_query

- 场景：只读复杂查询，且 Pandas Tool 无法自然表达。
- 参数：`query: string`、`max_rows: int<=500`。
- 输出：columns、rows、row_count、truncated、duration_ms。
- 示例：`{"query":"SELECT region, SUM(sales) AS total_sales FROM dataset_101 GROUP BY region LIMIT 100","max_rows":100}`。
- 安全：必须经过 SQL AST、表字段白名单、LIMIT、超时和只读连接；模型不能指定连接。
- 首期实现：SQLGlot 只接受单条 SELECT，仅允许引用当前数据集投影表和画像字段；查询使用独立只读连接，结果最多 500 行，MySQL 查询超时 5 秒。

## 8. generate_chart

- 场景：把前一个 Tool Result 转为可视化协议。
- 参数：`source_tool_call_id`、`type: bar|line|pie`、`dimension`、`metrics`、`title`。
- 输出：受控 ChartSpec，不含脚本、HTML 或 formatter 函数。
- 示例：`{"source_tool_call_id":"tc_001","type":"bar","dimension":"region","metrics":["sales_sum"],"title":"各地区销售额"}`。

## 注册与版本

Tool Registry 以规范名注册，并保存 schema_version。接口记录实际 Tool 版本，便于历史解释。新增 Tool 需同时更新 Prompt 描述、Schema、权限、文档和回归场景。
