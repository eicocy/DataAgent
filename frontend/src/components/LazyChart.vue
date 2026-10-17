<script>
import ChartView from './ChartView.vue'
export default {
  name: 'LazyChart', components: { ChartView },
  props: { spec: { type: Object, required: true } },
  emits: ['expand'],
  data() { return { visible: false, observer: null } },
  mounted() {
    if (!window.IntersectionObserver) { this.visible = true; return }
    this.observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) { this.visible = true; this.observer.disconnect() }
    }, { rootMargin: '160px' })
    this.observer.observe(this.$el)
  },
  beforeUnmount() { this.observer?.disconnect() },
  methods: { exportImage() { this.$refs.chart?.exportImage() } },
}
</script>
<template>
  <section class="inline-chart">
    <ChartView v-if="visible" ref="chart" :spec="spec" compact />
    <button v-else type="button" class="chart-placeholder" @click="visible = true">查看{{ spec.title || '图表' }}</button>
    <div class="inline-chart-actions"><button type="button" @click="$emit('expand', spec)">放大图表</button><button type="button" :disabled="!visible" @click="exportImage">下载图片</button></div>
  </section>
</template>
<style scoped>
.inline-chart { min-width: 0; margin: 20px 0; }
.chart-placeholder { width: 100%; height: 320px; border: 1px solid var(--line); border-radius: 10px; background: #fafbfc; color: var(--muted); cursor: pointer; }
.inline-chart-actions { display: flex; gap: 16px; justify-content: flex-end; }
button { border: 0; background: transparent; color: var(--muted); font-size: 12px; cursor: pointer; padding: 6px 0; }
button:hover { color: var(--ink); }
button:focus-visible { outline: 2px solid var(--brand); outline-offset: 3px; }
</style>
