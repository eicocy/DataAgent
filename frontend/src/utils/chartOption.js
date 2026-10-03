function toNumber(value) {
  if (value === null || value === undefined || typeof value === 'boolean' || (typeof value === 'string' && !value.trim())) return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

export function buildChartOption(spec) {
  if (!['bar', 'line', 'pie', 'scatter', 'histogram'].includes(spec?.type) || !Array.isArray(spec.series) || !spec.series.length) return null
  if (spec.type === 'pie') {
    const items = spec.series[0]?.data || []
    if (items.some((item) => toNumber(item.value) < 0)) return null
    return {
      tooltip: { trigger: 'item' },
      legend: { bottom: 0, type: 'scroll' },
      series: [{ type: 'pie', radius: ['38%', '72%'], data: items.map((item) => ({ name: String(item.name ?? ''), value: toNumber(item.value) })).filter((item) => item.value !== null) }],
    }
  }
  const unit = spec.unit || spec.metrics?.[0]?.unit || ''
  if (spec.type === 'scatter') {
    return { tooltip: { trigger: 'item' }, legend: { top: 0 }, grid: { left: 48, right: 22, top: 42, bottom: 50 },
      xAxis: { type: 'value', name: spec.dimension?.label || '' }, yAxis: { type: 'value', name: unit },
      series: spec.series.map((series) => ({ name: series.name || '', type: 'scatter', data: (series.data || []).map((item) => Array.isArray(item.value) ? item.value.map(toNumber) : [toNumber(item.x ?? item.name), toNumber(item.y ?? item.value)]).filter((pair) => pair.length === 2 && pair.every((value) => value !== null)) })) }
  }
  // 以所有系列的分类并集对齐，不能用第一个系列的位置拼接其他产品。
  const categories = [...new Set(spec.series.flatMap((series) => (series.data || []).map((item) => String(item.name ?? ''))))]
  if (['time', 'date', 'datetime'].includes(spec.dimension?.type) || categories.every((name) => /^\d{4}-\d{2}(-\d{2})?$/.test(name))) categories.sort((a, b) => (Date.parse(a) - Date.parse(b)) || a.localeCompare(b))
  else if (spec.dimension?.type === 'value') categories.sort((a, b) => Number(a) - Number(b))
  return {
    tooltip: { trigger: 'axis' },
    legend: { top: 0, type: 'scroll' },
    grid: { left: 48, right: 22, top: 42, bottom: 50 },
    xAxis: { type: 'category', name: spec.dimension?.label || '', data: categories, axisLabel: { hideOverlap: true } },
    yAxis: { type: 'value', scale: true, name: unit },
    series: spec.series.map((series) => ({
      name: String(series.name || ''),
      type: spec.type === 'histogram' ? 'bar' : spec.type,
      smooth: false,
      connectNulls: false,
      data: categories.map((category) => toNumber((series.data || []).find((item) => String(item.name ?? '') === category)?.value)),
    })),
  }
}
