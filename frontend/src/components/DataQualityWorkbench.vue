<script>
import { datasetApi } from '../api/datasets'
import { percentText } from '../utils/exactDecimal'

export default {
  name: 'DataQualityWorkbench',
  props: { datasetId: Number, versionId: Number, result: Object },
  data() {
    return { quality: null, loading: false, error: '', token: 0 }
  },
  computed: {
    data() { return this.result || this.quality },
    scored() { return this.data?.kind === 'quality_score' },
  },
  watch: {
    versionId: { immediate: true, handler() { this.load() } },
    datasetId() { this.load() },
  },
  beforeUnmount() { this.token++ },
  methods: {
    // 固定版本变化使旧质量请求失效；展示的 result 不触发额外后端查询。
    async load() {
      const token = ++this.token
      this.quality = null
      this.error = ''
      if (this.result || !this.versionId) return
      this.loading = true
      try {
        const value = await datasetApi.quality(this.datasetId, this.versionId)
        if (token === this.token) this.quality = value
      } catch (error) {
        if (token === this.token) this.error = error.message || '质量检查失败'
      } finally {
        if (token === this.token) this.loading = false
      }
    },
    rate(value) { return value == null ? '未提供' : percentText(String(value)) },
    samples(finding) { return finding.row_refs?.slice(0, 100).join('、') || '无样例' },
    checkLabel(check) {
      return ({ missing_value_analysis: '缺失值检查', duplicate_detection: '重复记录检查',
        outlier_detection: '异常值检查', data_type_check: '字段类型检查' })[check] || check
    },
  },
}
</script>

<template>
  <section class="phase3-workbench" aria-label="数据质量">
    <h3>数据质量</h3>
    <p v-if="loading" role="status">正在检查固定版本…</p>
    <p v-if="error" role="alert">{{ error }} <el-button @click="load">重试质量检查</el-button></p>
    <template v-if="data && scored">
      <p>
        规则 {{ data.rule_version }} · {{ data.row_count ?? '未提供' }} 行 ·
        评分 {{ data.status === 'empty' ? '空数据，评分未定义' : data.score ?? '评分未提供' }}
      </p>
      <p>这是公开规则的描述性评分，不是行业标准。</p>
      <p>{{ data.explanation }}</p>
      <div class="table-wrap phase3-table">
        <table class="data-table">
          <thead><tr><th>问题</th><th>字段</th><th>严重程度</th><th>完整数量</th><th>建议</th><th>行号样例（最多100条）</th></tr></thead>
          <tbody>
            <tr v-for="(item, index) in data.findings" :key="index">
              <td>{{ item.issue }}</td><td>{{ item.column || '整表' }}</td>
              <td>{{ item.severity === 'error' ? '错误' : item.severity === 'warning' ? '警告' : '未提供' }}</td>
              <td>{{ item.count }}</td><td>{{ item.suggestion || '未提供' }}</td><td>{{ samples(item) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="!data.findings?.length">未发现当前规则覆盖的问题。</p>
      <p v-if="data.key_candidates?.length">候选唯一键：{{ data.key_candidates.join('、') }}</p>
      <details v-if="data.configured_rules">
        <summary>查看检查口径</summary>
        <p v-for="(rule, column) in data.configured_rules" :key="column">
          {{ column }} · {{ rule.type }} · 下限 {{ rule.minimum ?? '未设定' }} · 上限 {{ rule.maximum ?? '未设定' }} · 日期格式 {{ rule.datetime_format || '自动识别' }}
        </p>
      </details>
    </template>
    <template v-else-if="data?.kind === 'quality'">
      <p>检查：{{ checkLabel(data.check) }}</p>
      <p>此结果按单项检查的原始口径展示数量、比例、状态及阈值。</p>
      <div class="table-wrap phase3-table">
        <table class="data-table">
          <thead><tr><th>字段</th><th>完整数量</th><th>比例</th><th>检查状态</th><th>下界</th><th>上界</th><th>行号样例（最多100条）</th></tr></thead>
          <tbody>
            <tr v-for="(item, index) in data.findings" :key="index">
              <td>{{ item.column || '整表' }}</td><td>{{ item.count }}</td><td>{{ rate(item.rate) }}</td>
              <td>{{ item.status ?? '未提供' }}</td><td>{{ item.lower ?? '未提供' }}</td><td>{{ item.upper ?? '未提供' }}</td><td>{{ samples(item) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="!data.findings.length">本次单项检查没有返回检查项。</p>
    </template>
  </section>
</template>
