<script>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart, ScatterChart, BoxplotChart, HeatmapChart, FunnelChart, CustomChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent, VisualMapComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { buildChartOption } from '../utils/chartOption'
import { chartsApi } from '../api/charts'

echarts.use([BarChart, LineChart, PieChart, ScatterChart, BoxplotChart, HeatmapChart, FunnelChart, CustomChart, GridComponent, LegendComponent, TooltipComponent, VisualMapComponent, CanvasRenderer])

export default {
  name: 'ChartView',
  props: { spec: { type: Object, required: true } },
  data() { return { highResLoading: false, highResError: '', renderedFiles: [], renderController: null } },
  watch: { spec: { deep: true, handler() { this.renderController?.abort(); this.renderController = null; this.highResLoading = false; this.highResError = ''; this.renderedFiles = [] } } },
  beforeUnmount() { this.renderController?.abort(); this.renderController = null },
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
  methods: {
    async generateHighResolution() {
      const artifactId = this.spec.artifact_id
      if (!artifactId || this.highResLoading) return
      this.highResLoading = true
      this.highResError = ''
      const controller = new AbortController()
      this.renderController = controller
      try {
        const response = await chartsApi.render(artifactId, {}, { signal: controller.signal })
        if (this.renderController !== controller || controller.signal.aborted) return
        this.renderedFiles = response || []
      } catch (error) { if (this.renderController === controller && !controller.signal.aborted) this.highResError = error.message || '高清图表生成失败' }
      finally { if (this.renderController === controller) this.highResLoading = false }
    },
  },
}
</script>

<template><section class="chart-result"><div ref="element" class="chart-canvas" role="img" :aria-label="spec.title || '分析图表'"></div><div class="chart-actions"><el-button size="small" plain @click="exportImage">快速导出</el-button><el-button v-if="spec.artifact_id" size="small" type="primary" plain :loading="highResLoading" @click="generateHighResolution">生成高清图表（300 DPI）</el-button></div><p v-if="highResError" class="inline-error" role="alert">{{ highResError }}</p><div v-if="renderedFiles.length" class="chart-downloads" role="status"><a v-for="file in renderedFiles" :key="file.artifact_id" :href="file.download_url" :download="file.file_name">下载 {{ file.file_name }}</a></div><p v-if="spec.source_ref || spec.source_tool_call_id" class="caption">结果来源：{{ spec.source_ref || spec.source_tool_call_id }}</p></section></template>
<style scoped>
.chart-actions, .chart-downloads { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.chart-downloads a { color: var(--brand, #245fe8); font-size: 13px; }
</style>
