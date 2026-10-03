window.PROTOTYPE_DATA = Object.freeze({
  isPrototypeData: true,
  datasets: [
    { id: 101, name: "2026年销售订单.xlsx", type: "XLSX", rows: 12840, columns: 5, size: "2.8 MB", status: "ready", uploadedAt: "2026-09-20 14:32" },
    { id: 102, name: "华东门店目标.csv", type: "CSV", rows: 3260, columns: 7, size: "780 KB", status: "ready", uploadedAt: "2026-09-19 10:18" },
    { id: 103, name: "客户回访记录.xlsx", type: "XLSX", rows: 842, columns: 9, size: "416 KB", status: "failed", uploadedAt: "2026-09-18 17:42" }
  ],
  columns: [
    { name: "order_date", label: "订单日期", type: "date", missing: 0, unique: 365, example: "2026-09-20" },
    { name: "region", label: "地区", type: "string", missing: 0, unique: 6, example: "华东" },
    { name: "product", label: "产品", type: "string", missing: 12, unique: 38, example: "智能手环" },
    { name: "sales", label: "销售额", type: "decimal", missing: 0, unique: 8892, example: "1280.00" },
    { name: "quantity", label: "数量", type: "integer", missing: 0, unique: 44, example: "3" }
  ],
  history: [
    { id: 901, question: "统计不同地区销售额并生成柱状图", dataset: "2026年销售订单.xlsx", tool: "group_by_analysis", status: "succeeded", duration: "1.84 s", createdAt: "2026-09-20 15:08" },
    { id: 902, question: "最近12个月销售趋势如何？", dataset: "2026年销售订单.xlsx", tool: "aggregate_data", status: "succeeded", duration: "2.13 s", createdAt: "2026-09-20 14:46" },
    { id: 903, question: "筛选销售额超过5000元的订单", dataset: "2026年销售订单.xlsx", tool: "filter_data", status: "failed", duration: "0.62 s", createdAt: "2026-09-20 14:10" }
  ],
  toolCall: {
    tool_call_id: "tc_20260920_001",
    tool_name: "group_by_analysis",
    parameters: { group_column: "region", value_column: "sales", aggregation: "sum" },
    status: "succeeded",
    duration_ms: 482,
    result_summary: "按 region 分为 6 组，返回销售额合计。"
  }
});

