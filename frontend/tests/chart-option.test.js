import { describe, expect, it } from 'vitest'

import { buildChartOption } from '../src/utils/chartOption'

describe('ChartSpec adapter', () => {
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
