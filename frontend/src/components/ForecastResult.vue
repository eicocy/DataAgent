<script>
import ChartView from './ChartView.vue'
export default {
 name: 'ForecastResult', components: { ChartView }, props: { result: { type: Object, required: true } },
 computed: { chart() { return { chart_type: 'line', title: '预测与经验误差范围', unit: this.result.unit || '', source_ref: this.result.source_ref, series: [['预测', 'value'], ['经验下界', 'lower'], ['经验上界', 'upper']].map(([name, key]) => ({ name, points: (this.result.points || []).map(point => ({ x: point.time, y: point[key] })) })) } } },
 methods: { metric(value) { return value ?? '未定义' }, model(value) { return ({ naive: '上一期基准', moving_average: '移动平均', linear_trend: '线性趋势', exponential_smoothing: '指数平滑', arima: 'ARIMA' })[value] || value }, status(value) { return ({ succeeded: '成功', skipped: '跳过', failed: '失败' })[value] || value } },
}
</script>
<template><section class="phase3-workbench" aria-label="预测结果"><h3>预测结果</h3>
 <p>历史 {{ result.history_start }} 至 {{ result.history_end }} · {{ result.observation_count }} 期 · 汇总 {{ result.aggregation }} · 粒度 {{ result.granularity }}</p>
 <p>选用 {{ model(result.selected_model) }} · 预测 {{ result.horizon }} 期 · {{ result.currency || '币种未确认' }} {{ result.unit || '单位未确认' }}</p>
 <div class="table-wrap phase3-table"><table class="data-table"><thead><tr><th>比较</th><th>MAE</th><th>RMSE</th><th>MAPE</th><th>非零目标覆盖率</th><th>解释</th></tr></thead><tbody><tr v-for="(entry, index) in [result.baseline, { metrics: result.metrics }]" :key="index"><th>{{ index ? '所选模型' : '上一期基准' }}</th><td>{{ metric(entry?.metrics?.mae) }}</td><td>{{ metric(entry?.metrics?.rmse) }}</td><td>{{ metric(entry?.metrics?.mape) }}</td><td>{{ entry?.metrics?.mape_coverage ?? '未提供' }}</td><td>{{ entry?.metrics?.mape_explanation }}</td></tr></tbody></table></div>
 <p class="summary-warning">经验误差范围，未经校准。它不保证未来真实值落入范围。</p><p>{{ result.uncertainty?.limitations }} · 残差样本 {{ result.uncertainty?.residual_count ?? '未提供' }}</p>
 <ChartView v-if="result.points?.length" :spec="chart" />
 <div class="table-wrap phase3-table"><table class="data-table"><thead><tr><th>时间</th><th>预测值</th><th>经验下界</th><th>经验上界</th></tr></thead><tbody><tr v-for="point in result.points" :key="point.time"><td>{{ point.time }}</td><td>{{ point.value }}</td><td>{{ point.lower }}</td><td>{{ point.upper }}</td></tr></tbody></table></div>
 <details><summary>查看回测历史和候选模型</summary><p v-for="fold in result.folds" :key="fold.fold_id">回测 {{ fold.fold_id + 1 }}：训练 {{ fold.train_start }} 至 {{ fold.train_end }}（{{ fold.train_size }} 期）；测试 {{ fold.test_start }} 至 {{ fold.test_end }}（{{ fold.test_size }} 期）</p><div v-for="candidate in result.candidates" :key="candidate.model"><h4>{{ model(candidate.model) }} · {{ status(candidate.status) }}</h4><p v-if="candidate.error_code">{{ candidate.error_code }}</p><p v-for="fold in candidate.folds" :key="fold.fold_id">回测 {{ fold.fold_id + 1 }}：MAE {{ fold.metrics.mae }} · RMSE {{ fold.metrics.rmse }} · MAPE {{ metric(fold.metrics.mape) }} · {{ fold.metrics.mape_explanation }}</p></div></details>
 <p v-for="note in result.limitations" :key="note" class="summary-warning">{{ note }}</p>
</section></template>
