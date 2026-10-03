import { describe, expect, it } from 'vitest'

import { buildChartOption } from '../src/utils/chartOption'

describe('ChartSpec adapter', () => {
  it('accepts canonical points and renders area, box, heatmap and funnel', () => {
    const points = [{ x: 'Jan', y: 12 }, { x: 'Feb', y: null }]
    expect(buildChartOption({ chart_type: 'area', series: [{ name: 'Sales', points }] }).series[0].areaStyle).toEqual({})
    expect(buildChartOption({ chart_type: 'box', series: [{ points: [{ x: 'A', values: [1, 2, 3, 4, 5] }] }] }).series[0].data).toEqual([[1, 2, 3, 4, 5]])
    expect(buildChartOption({ type: 'heatmap', series: [{ data: [{ x: 'A', y: 'B', value: 0.8 }] }] }).series[0].data).toEqual([[0, 0, 0.8]])
    expect(buildChartOption({ type: 'funnel', series: [{ data: [{ name: 'Visit', value: 50 }] }] }).series[0].type).toBe('funnel')
  })
  it('represents positive and negative waterfall changes on their true baselines', () => {
    const option = buildChartOption({ type: 'waterfall', series: [{ data: [{ name: 'Start', value: 100 }, { name: 'Loss', value: -30 }, { name: 'Gain', value: 20 }] }] })
    expect(option.series[0].data).toEqual([0, 70, 70])
    expect(option.series[1].data.map(item => item.value)).toEqual([100, 30, 20])
  })
  it('preserves undefined correlation cells rather than substituting row indices', () => {
    const option = buildChartOption({ chart_type: 'heatmap', series: [
      { name: 'A', points: [{ x: 0, y: 0, values: [null] }, { x: 1, y: 0, values: [0] }] },
      { name: 'B', points: [{ x: 0, y: 1, values: [null] }, { x: 1, y: 1, values: [null] }] },
    ] })
    expect(option.series[0].data).toEqual([[1, 0, 0]])
  })
  it('converts the server bar result into numeric series with category labels', () => {
    const option = buildChartOption({
      type: 'bar',
      dimension: { label: '地区' },
      series: [{ name: '销售额合计', data: [{ name: '华东', value: '3280.00' }, { name: '华南', value: 'not-number' }] }],
    })

    expect(option.xAxis.data).toEqual(['华东', '华南'])
    expect(option.series[0].data).toEqual([3280, null])
    expect(option.series[0].type).toBe('bar')
  })

  it('renders one safe pie series and rejects unsupported chart types', () => {
    const option = buildChartOption({ type: 'pie', series: [{ data: [{ name: 'East', value: 12 }, { name: 'West', value: 3 }] }] })

    expect(option.series[0].data).toEqual([{ name: 'East', value: 12 }, { name: 'West', value: 3 }])
    expect(buildChartOption({ type: 'unknown', series: [] })).toBeNull()
  })

  it('preserves missing values and aligns sorted time categories across all series', () => {
    const option = buildChartOption({ type: 'line', dimension: { type: 'date' }, unit: '元', series: [
      { name: 'A', data: [{ name: '2026-02', value: null }, { name: '2026-01', value: 5 }] },
      { name: 'B', data: [{ name: '2026-03', value: '' }, { name: '2026-02', value: 8 }] },
    ] })
    expect(option.xAxis.data).toEqual(['2026-01', '2026-02', '2026-03'])
    expect(option.series[0].data).toEqual([5, null, null])
    expect(option.series[1].data).toEqual([null, 8, null])
    expect(option.yAxis.name).toBe('元')
  })
  it('supports numeric scatter coordinates and rejects negative pie values', () => {
    expect(buildChartOption({ type: 'scatter', series: [{ data: [{ x: 2, y: 3 }, { x: '', y: 4 }] }] }).series[0].data).toEqual([[2, 3]])
    expect(buildChartOption({ type: 'scatter', series: [{ data: [{ name: 2, value: [2, 3] }] }] }).series[0].data).toEqual([[2, 3]])
    expect(buildChartOption({ type: 'pie', series: [{ data: [{ name: 'a', value: -1 }] }] })).toBeNull()
    expect(buildChartOption({ type: 'histogram', series: [{ data: [{ name: '0–10', value: 3 }] }] }).series[0].type).toBe('bar')
  })
})
