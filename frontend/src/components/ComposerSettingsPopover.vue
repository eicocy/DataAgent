<script>
import { ElButton, ElIcon, ElPopover } from 'element-plus'
import { Operation, Close } from '@element-plus/icons-vue'

// 设置即时回传给工作台；展开状态不影响已选择的分析配置。
export default {
  name: 'ComposerSettingsPopover',
  components: { ElButton, ElIcon, ElPopover, Operation, Close },
  props: {
    catalog: { type: Object, default: () => ({ categories: [], items: [] }) },
    capabilities: { type: Object, default: () => ({}) },
    options: { type: Object, default: () => ({}) },
    busy: Boolean,
  },
  emits: ['option-change', 'template-select'],
  data() { return { open: false, category: '', templateId: '', depth: 'STANDARD', reportTemplate: '', modelId: '', returnFocus: false } },
  computed: {
    templates() { return (this.catalog.items || []).filter(item => !this.category || item.category === this.category) },
    selectedTemplate() { return this.templates.find(item => item.id === this.templateId) },
  },
  watch: {
    options: { immediate: true, deep: true, handler(value) {
      this.category = value.category || ''; this.templateId = value.profile_ids?.[0] || ''
      this.depth = value.depth || 'STANDARD'; this.reportTemplate = value.report_template || ''; this.modelId = value.model_id || ''
    } },
    busy(value) { if (value) { this.returnFocus = false; this.open = false } },
    open(value) {
      // 捕获 Escape，原生 select 展开/聚焦时也能可靠关闭面板。
      if (value) document.addEventListener('keydown', this.handleEscape, true)
      else document.removeEventListener('keydown', this.handleEscape, true)
    },
  },
  beforeUnmount() { document.removeEventListener('keydown', this.handleEscape, true) },
  methods: {
    change(patch) { if (!this.busy) this.$emit('option-change', patch) },
    changeCategory() { this.templateId = ''; this.change({ category: this.category, profile_ids: [] }) },
    chooseTemplate() {
      if (this.busy) return
      if (!this.templateId) { this.change({ profile_ids: [] }); return }
      const profile = this.selectedTemplate
      if (profile && profile.availability !== 'planned') this.$emit('template-select', profile, this.category)
    },
    close() { this.returnFocus = true; this.open = false },
    handleEscape(event) { if (this.open && event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); this.close() } },
    focusFirst() {
      const panel = this.$refs.panel
      if (!this.busy && this.open && !panel?.contains(document.activeElement)) panel?.querySelector('select:not(:disabled)')?.focus({ preventScroll: true })
    },
    restoreFocus() {
      // 键盘关闭回到触发按钮；点击其他输入时保留用户刚选择的焦点。
      if (!this.busy && (this.returnFocus || document.activeElement === document.body)) this.$refs.trigger?.$el?.focus({ preventScroll: true })
      this.returnFocus = false
    },
  },
}
</script>

<template>
  <el-popover v-model:visible="open" role="dialog" trigger="click" placement="top-start" :width="'min(360px, calc(100vw - 32px))'" :disabled="busy" :show-arrow="false" :teleported="true" :hide-after="0" :popper-options="{ strategy: 'fixed', modifiers: [{ name: 'preventOverflow', options: { rootBoundary: 'viewport', padding: 16, altAxis: true } }, { name: 'flip', options: { padding: 16, fallbackPlacements: ['top-start', 'bottom-start'] } }] }" :popper-style="{ padding: '0', borderRadius: '14px' }" popper-class="composer-settings-popper" @after-enter="focusFirst" @after-leave="restoreFocus">
    <template #reference>
      <el-button ref="trigger" native-type="button" class="composer-settings-trigger" :disabled="busy" aria-label="分析设置" aria-haspopup="dialog" :aria-expanded="open" title="分析设置"><el-icon><Operation /></el-icon><span>分析设置</span></el-button>
    </template>
    <section ref="panel" class="composer-settings-panel" role="dialog" aria-label="分析设置" @keydown.esc.stop.prevent="close">
      <header><div><h3>分析设置</h3><p>选择后立即生效</p></div><button type="button" class="settings-close" aria-label="关闭分析设置" @click="close"><el-icon><Close /></el-icon></button></header>
      <div class="settings-fields">
        <label>分析方向<select v-model="category" :disabled="busy" aria-label="分析方向" @change="changeCategory"><option value="">自动</option><option v-for="item in catalog.categories" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
        <label>分析模板<select v-model="templateId" :disabled="busy" aria-label="分析模板" @change="chooseTemplate"><option value="">自动选择</option><option v-for="item in templates" :key="item.id" :value="item.id" :disabled="item.availability === 'planned'">{{ item.name }}{{ item.availability === 'planned' ? ' · 规划中' : item.availability === 'limited' ? ' · 通用能力' : '' }}</option></select></label>
        <label>分析深度<select v-model="depth" aria-label="分析深度" :disabled="busy || !capabilities.depth_selection" @change="change({ depth })"><option v-for="value in capabilities.depths || ['STANDARD']" :key="value" :value="value">{{ { FAST: '快速', STANDARD: '标准', DEEP: '深度' }[value] }}</option></select></label>
        <label>报告类型<select v-model="reportTemplate" aria-label="报告类型" :disabled="busy || !capabilities.automatic_reports" @change="change({ report_template: reportTemplate || null, output_formats: reportTemplate ? ['xlsx', 'docx', 'pdf', 'python'] : [] })"><option value="">手动生成</option><option v-for="item in capabilities.report_templates || []" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
        <label>模型<select v-model="modelId" aria-label="模型" :disabled="busy || !capabilities.model_selection" @change="change({ model_id: modelId || null })"><option value="">{{ capabilities.models?.[0]?.id || '服务端配置' }}</option><option v-for="model in capabilities.models || []" :key="model.id" :value="model.id" :disabled="!model.configured">{{ model.id }}</option></select></label>
      </div>
      <footer><p>{{ capabilities.profile_execution ? '模板决定关注点，系统根据数据生成分析计划。' : '模板填入可修改示例；当前分析使用选中的一个数据集。' }}</p><p v-if="selectedTemplate?.availability === 'limited'">{{ selectedTemplate.constraints?.[1] }}</p><p v-if="reportTemplate">分析后自动生成 Excel、Word、PDF 和 Python 文件；缺少来源或格式失败会保留部分结果。</p></footer>
    </section>
  </el-popover>
</template>

<style scoped>
.composer-settings-trigger { height: 40px; padding: 0 10px; margin: 0; border-color: transparent; background: transparent; color: var(--ink); border-radius: 9px; font-size: 13px; }
.composer-settings-trigger :deep(.el-icon) { font-size: 17px; margin-right: 6px; }
.composer-settings-trigger:hover, .composer-settings-trigger[aria-expanded="true"] { background: var(--canvas); border-color: var(--line); }
.composer-settings-panel { max-height: min(480px, calc(100dvh - 48px)); overflow-y: auto; overscroll-behavior: contain; color: var(--ink); padding: 18px; }
header { position: sticky; top: 0; z-index: 1; display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 18px; background: var(--surface); }
h3 { margin: 0; font-size: 15px; font-weight: 600; } header p { margin: 5px 0 0; font-size: 12px; color: var(--muted); }
.settings-close { width: 32px; height: 32px; display: grid; place-items: center; flex-shrink: 0; border: 0; border-radius: 8px; background: transparent; color: var(--muted); cursor: pointer; }
.settings-close:hover { background: var(--canvas); color: var(--ink); }
.settings-fields { display: grid; gap: 14px; }
label { display: grid; gap: 7px; font-size: 13px; font-weight: 500; }
select { width: 100%; min-width: 0; height: 38px; padding: 0 10px; color: var(--ink); border: 1px solid var(--line); border-radius: 8px; background: var(--surface); font: inherit; font-weight: 400; cursor: pointer; }
select:disabled { cursor: default; color: var(--muted); background: var(--canvas); }
select:focus-visible { outline: 2px solid rgb(47 107 255 / 35%); outline-offset: 2px; border-color: var(--brand); }
footer { margin-top: 18px; padding-top: 12px; border-top: 1px solid var(--line); } footer p { margin: 0 0 6px; color: var(--muted); font-size: 12px; line-height: 1.6; }
</style>

<style>
@media (prefers-reduced-motion: reduce) {
  .composer-settings-popper { transition: none !important; animation: none !important; }
}
</style>
