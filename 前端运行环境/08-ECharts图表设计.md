# ECharts 图表设计

## ChartSpec

```text
type: bar | line | pie
title: string
dimension: { field, label, type }
metrics: [{ field, label, aggregation, unit }]
series: [{ name, data: [{ name, value }] }]
source_tool_call_id: string
```

`chartAdapter.toEChartsOption(spec)` 只映射白名单属性，不接受 formatter 函数字符串、HTML、事件脚本或任意 ECharts option。数值格式由本地 formatter 生成。

所有图表提供标题、单位、图例、空/错误状态和同源数据表；颜色使用 DESIGN.md 固定序列。容器通过 ResizeObserver 调整尺寸，并在页面卸载时 dispose。

