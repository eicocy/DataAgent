function toNumber(value) {
  if (value === null || value === undefined || typeof value === 'boolean' || (typeof value === 'string' && !value.trim())) return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

export function buildChartOption(spec) {
  const type = spec?.chart_type || spec?.type
  if (!['bar', 'line', 'pie', 'donut', 'scatter', 'histogram', 'area', 'box', 'boxplot', 'heatmap', 'waterfall', 'funnel'].includes(type) || !Array.isArray(spec.series) || !spec.series.length) return null
  spec = { ...spec, type, series: spec.series.map(series => ({ ...series, data: (series.points || series.data || []).map(point => ({ ...point, name: point.name ?? point.x ?? '', value: point.value ?? point.y ?? null })) })) }
  if (['pie', 'donut', 'funnel'].includes(type)) {
    const items = spec.series[0]?.data || []
    if (items.some((item) => toNumber(item.value) < 0)) return null
    return {
      tooltip: { trigger: 'item' },
      legend: { bottom: 0, type: 'scroll' },
      series: [{ type: type === 'funnel' ? 'funnel' : 'pie', sort: type === 'funnel' ? 'none' : undefined, radius: type === 'pie' ? '72%' : ['38%', '72%'], data: items.map((item) => ({ name: String(item.name ?? ''), value: toNumber(item.value) })).filter((item) => item.value !== null) }],
    }
  }
  const unit = spec.unit || spec.metrics?.[0]?.unit || ''
  if (type === 'heatmap') {
    const points = spec.series.flatMap((s, i) => s.values ? s.values.map((v, j) => ({ x: j, y: i, value: v })) : s.data.map(p => ({ x: p.x ?? p.name, y: p.y ?? s.name, value: Array.isArray(p.values) ? p.values[0] : p.value })))
    const xs = [...new Set(points.map(p => String(p.x)))], ys = [...new Set(points.map(p => String(p.y)))]
    const values = points.map(p => toNumber(p.value)).filter(v => v !== null)
    return { tooltip: { trigger: 'item' }, grid: { left: 56, right: 28, top: 30, bottom: 64, containLabel: true },
      xAxis: { type: 'category', data: xs }, yAxis: { type: 'category', data: ys },
      visualMap: { min: Math.min(0, ...values), max: Math.max(1, ...values), calculable: true, orient: 'horizontal', bottom: 0 },
      series: [{ type: 'heatmap', data: points.map(p => [xs.indexOf(String(p.x)), ys.indexOf(String(p.y)), toNumber(p.value)]).filter(p => p[2] !== null) }] }
  }
  if (spec.type === 'scatter') {
    return { tooltip: { trigger: 'item' }, legend: { top: 0 }, grid: { left: 48, right: 22, top: 42, bottom: 50 },
      xAxis: { type: 'value', name: spec.dimension?.label || '' }, yAxis: { type: 'value', name: unit },
      series: spec.series.map((series) => ({ name: series.name || '', type: 'scatter', data: (series.data || []).map((item) => Array.isArray(item.value) ? item.value.map(toNumber) : [toNumber(item.x ?? item.name), toNumber(item.y ?? item.value)]).filter((pair) => pair.length === 2 && pair.every((value) => value !== null)) })) }
  }
  // 以所有系列的分类并集对齐，不能用第一个系列的位置拼接其他产品。
  const categories = [...new Set(spec.series.flatMap((series) => (series.data || []).map((item) => String(item.name ?? ''))))]
  if (['time', 'date', 'datetime'].includes(spec.dimension?.type) || categories.every((name) => /^\d{4}-\d{2}(-\d{2})?$/.test(name))) categories.sort((a, b) => (Date.parse(a) - Date.parse(b)) || a.localeCompare(b))
  else if (spec.dimension?.type === 'value') categories.sort((a, b) => Number(a) - Number(b))
  const option = {
    tooltip: { trigger: 'axis' },
    legend: { top: 0, type: 'scroll' },
    grid: { left: 48, right: 22, top: 42, bottom: 50 },
    xAxis: { type: 'category', name: spec.dimension?.label || '', data: categories, axisLabel: { hideOverlap: true } },
    yAxis: { type: 'value', scale: true, name: unit },
    series: spec.series.map((series) => ({
      name: String(series.name || ''),
      type: spec.type === 'histogram' ? 'bar' : spec.type === 'area' ? 'line' : ['box', 'boxplot'].includes(spec.type) ? 'boxplot' : spec.type,
      ...(spec.type === 'area' ? { areaStyle: {} } : {}),
      ...(spec.options?.stacked ? { stack: 'total' } : {}),
      smooth: false,
      connectNulls: false,
      data: categories.map((category) => {
        const point = series.data.find(item => String(item.name) === category)
        if (['box', 'boxplot'].includes(type)) {
          const values = point?.values || point?.value
          return Array.isArray(values) && values.length === 5 && values.every(v => toNumber(v) !== null) ? values.map(toNumber) : null
        }
        return toNumber(point?.value)
      }),
    })),
  }
  if (type === 'waterfall') {
    const items = spec.series[0].data, baselines = [], ends = [], bars = []
    let total = 0
    for (const point of items) {
      const delta = toNumber(point.value)
      baselines.push(delta === null ? null : Math.min(total, total + delta))
      ends.push(delta === null ? total : total + delta)
      bars.push({ value: delta === null ? null : Math.abs(delta), delta })
      if (delta !== null) total += delta
    }
    option.xAxis.data = items.map(p => String(p.name))
    option.yAxis.min = Math.min(0, ...baselines.filter(v => v !== null), ...ends)
    option.yAxis.max = Math.max(0, ...baselines.filter(v => v !== null), ...ends)
    option.series = [{ type: 'bar', silent: true, data: baselines, itemStyle: { opacity: 0 }, tooltip: { show: false } },
      { name: spec.series[0].name || '变化', type: 'custom', data: bars,
        renderItem(params, api) {
          const i = params.dataIndex
          if (bars[i].value === null) return null
          const start = api.coord([i, baselines[i]]), end = api.coord([i, baselines[i] + bars[i].value])
          const width = api.size([1, 0])[0] * 0.6
          return { type: 'rect', shape: { x: start[0] - width / 2, y: Math.min(start[1], end[1]), width, height: Math.abs(end[1] - start[1]) }, style: { fill: bars[i].delta < 0 ? '#d9415d' : '#2f6bff' } }
        } }]
    option.tooltip = { trigger: 'item', formatter: p => `${String(items[p.dataIndex]?.name ?? '')}: ${String(items[p.dataIndex]?.value ?? '')}`, renderMode: 'richText' }
  }
  return option
}
