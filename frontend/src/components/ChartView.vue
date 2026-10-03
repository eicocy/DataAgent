<script>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart, ScatterChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { buildChartOption } from '../utils/chartOption'

echarts.use([BarChart, LineChart, PieChart, ScatterChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

export default {
  name: 'ChartView',
  props: { spec: { type: Object, required: true } },
  setup(props) {
    const element = ref(null)
    let chart = null
    let resizeObserver = null
    const render = () => {
      if (!chart || !element.value) return
      const option = buildChartOption(props.spec)
      if (option) chart.setOption(option, true)
      else chart.clear()
    }
    onMounted(() => {
      if (!element.value) return
      chart = echarts.init(element.value)
      resizeObserver = new ResizeObserver(() => chart?.resize())
      resizeObserver.observe(element.value)
      render()
    })
    watch(() => props.spec, render, { deep: true })
    onBeforeUnmount(() => {
      resizeObserver?.disconnect()
      chart?.dispose()
      chart = null
    })
    const exportImage = () => {
      if (!chart) return
      const link = document.createElement('a')
      link.download = `${String(props.spec.title || '分析图表').replace(/[\\/:*?"<>|]/g, '_')}.png`
      link.href = chart.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#ffffff' })
      link.click()
    }
    return { element, exportImage }
  },
}
</script>

<template><section><div ref="element" class="chart-canvas" role="img" :aria-label="spec.title || '分析图表'"></div><el-button size="small" plain @click="exportImage">导出 PNG</el-button><p v-if="spec.source_ref || spec.source_tool_call_id" class="caption">结果来源：{{ spec.source_ref || spec.source_tool_call_id }}</p></section></template>
