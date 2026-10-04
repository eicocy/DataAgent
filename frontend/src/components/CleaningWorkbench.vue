<script>
import { ElButton } from 'element-plus'
import TransformationPreview from './TransformationPreview.vue'
import transformationFlow from '../utils/transformationFlow'
const operations = { remove_duplicates: '删除重复记录', drop_missing_rows: '删除缺失记录', fill_missing_values: '填补缺失值', outlier_treatment: '处理异常值', normalize_text: '规范文本', convert_dtype: '转换类型', parse_datetime: '解析日期', rename_columns: '重命名字段', replace_values: '替换值' }
export default {
 name: 'CleaningWorkbench', components: { ElButton, TransformationPreview }, mixins: [transformationFlow],
 data() { return { flow: 'transform', steps: [], operations } },
 computed: { payload() { return { dataset_version_id: this.versionId, operations: this.steps.map(step => {
  const parameters = { columns: step.columns }
  if (step.tool === 'remove_duplicates') parameters.keep = step.keep
  if (step.tool === 'drop_missing_rows') parameters.how = step.how
  if (step.tool === 'fill_missing_values' || step.tool === 'outlier_treatment') { parameters.strategy = step.strategy; if (step.strategy === 'constant') parameters.value = step.value; if (step.tool === 'outlier_treatment') parameters.method = step.method }
  if (step.tool === 'normalize_text') parameters.text_operations = step.textOperations
  if (step.tool === 'convert_dtype') parameters.dtype = step.dtype
  if (step.tool === 'parse_datetime' && step.dateFormat) parameters.datetime_format = step.dateFormat
  if (step.tool === 'rename_columns') parameters.names = { [step.columns[0]]: step.value }
  if (step.tool === 'replace_values') parameters.replacements = { [step.from]: step.value }
  return { tool: step.tool, parameters }
 }) } } },
 methods: { addStep() { if (this.steps.length < 8) this.steps.push({ tool: '', columns: [], keep: '', how: '', strategy: '', value: '', method: '', dtype: '', from: '', dateFormat: '', textOperations: [] }) } },
}
</script>
<template><section aria-label="数据清洗"><h3>清洗工作台</h3><p>选择 1–8 项操作，先预览再保存。不会自动填补、删除或处理异常值。</p>
 <fieldset v-for="(step, index) in steps" :key="index" :disabled="saving"><legend>步骤 {{ index + 1 }}</legend>
  <label>清洗操作<select v-model="step.tool" :aria-label="`步骤 ${index + 1} 清洗操作`"><option value="">请选择操作</option><option v-for="(label, tool) in operations" :key="tool" :value="tool">{{ label }}</option></select></label>
  <label>目标字段<select v-model="step.columns" multiple :aria-label="`步骤 ${index + 1} 目标字段`"><option v-for="column in columns" :key="column" :value="column">{{ column }}</option></select></label>
  <label v-if="step.tool === 'remove_duplicates'">重复记录保留<select v-model="step.keep"><option value="">请选择</option><option value="first">保留第一条</option><option value="last">保留最后一条</option><option value="none">全部删除</option></select></label>
  <label v-if="step.tool === 'drop_missing_rows'">删除条件<select v-model="step.how"><option value="">请选择</option><option value="any">任一目标字段缺失</option><option value="all">全部目标字段缺失</option></select></label>
  <label v-if="['fill_missing_values','outlier_treatment'].includes(step.tool)">处理方式<select v-model="step.strategy"><option value="">请选择</option><template v-if="step.tool === 'fill_missing_values'"><option value="constant">指定值</option><option value="mean">平均值（近似数值）</option><option value="median">中位数（近似数值）</option><option value="mode">众数</option><option value="forward">前值</option><option value="backward">后值</option></template><template v-else><option value="clip">限制到边界</option><option value="drop">删除记录</option><option value="null">置为缺失</option></template></select></label>
  <label v-if="step.tool === 'outlier_treatment'">异常识别<select v-model="step.method"><option value="">请选择</option><option value="iqr">四分位距</option><option value="zscore">标准分数</option></select></label>
  <label v-if="step.tool === 'normalize_text'">文本操作<select v-model="step.textOperations" multiple><option value="strip">清除首尾空白</option><option value="collapse_whitespace">合并连续空白</option><option value="lower">小写</option><option value="upper">大写</option><option value="casefold">大小写规范</option></select></label>
  <label v-if="step.tool === 'convert_dtype'">目标类型<select v-model="step.dtype"><option value="">请选择</option><option value="integer">整数</option><option value="decimal">小数</option><option value="string">文本</option><option value="boolean">布尔</option><option value="datetime">日期时间</option></select></label>
  <label v-if="step.tool === 'parse_datetime'">日期格式（可选）<input v-model="step.dateFormat" placeholder="例如 %Y-%m-%d" /></label>
  <label v-if="step.tool === 'replace_values'">原值<input v-model="step.from" /></label>
  <label v-if="step.strategy === 'constant' || ['rename_columns','replace_values'].includes(step.tool)">{{ step.tool === 'rename_columns' ? '新字段名（仅选择一个字段）' : '指定值（文本）' }}<input v-model="step.value" /></label>
  <ElButton @click="steps.splice(index, 1)">移除步骤</ElButton>
 </fieldset>
 <ElButton :disabled="steps.length >= 8 || saving" @click="addStep">添加清洗步骤</ElButton>
 <ElButton :disabled="!steps.length || steps.some(step => !step.tool || !step.columns.length) || saving" :loading="loading" @click="previewChanges">预览清洗</ElButton>
 <p v-if="error" class="inline-error" role="alert">{{ error }}</p><TransformationPreview :preview="preview" />
 <ElButton type="primary" :disabled="!preview || loading" :loading="saving" @click="saveVersion">保存为新版本</ElButton><p v-if="notice" role="status">{{ notice }}</p>
</section></template>
<style scoped>
fieldset { border: 1px solid var(--line); border-radius: var(--radius-sm); margin: 12px 0; display: flex; align-items: start; flex-wrap: wrap; gap: 12px; } label { display: grid; gap: 6px; } select, input { padding: 6px; border: 1px solid var(--line); border-radius: var(--radius-sm); max-width: 100%; } select[multiple] { min-height: 70px; }
</style>
