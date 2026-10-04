<script>
import { ElButton, ElIcon } from 'element-plus'
import { Plus, Top } from '@element-plus/icons-vue'

export default {
  name: 'PromptComposer',
  components: { ElButton, ElIcon, Plus, Top },
  props: {
    modelValue: { type: String, default: '' }, busy: Boolean, uploading: Boolean,
    catalog: { type: Object, default: () => ({ categories: [], items: [] }) },
    capabilities: { type: Object, default: () => ({ file_formats: ['csv', 'tsv', 'json', 'xlsx', 'xls', 'parquet'] }) },
    options: { type: Object, default: () => ({}) },
  },
  emits: ['update:modelValue', 'submit', 'upload', 'option-change', 'templates'],
  data() { return { category: '', templateId: '', depth: 'STANDARD', modelId: '', dragging: false, composing: false } },
  watch: {
    options: { immediate: true, deep: true, handler(value) { this.category = value.category || ''; this.templateId = value.profile_ids?.[0] || ''; this.depth = value.depth || 'STANDARD'; this.modelId = value.model_id || '' } },
  },
  computed: {
    accept() { return [...(this.capabilities.file_formats || []), ...(this.capabilities.document_formats || [])].map(ext => `.${ext}`).join(',') },
    templates() { return (this.catalog.items || []).filter(item => !this.category || item.category === this.category) },
    selectedTemplate() { return this.templates.find(item => item.id === this.templateId) },
  },
  methods: {
    submit() { if (!this.busy && !this.uploading && this.modelValue.trim() && !this.composing) this.$emit('submit') },
    handleEnter(event) {
      // 中文输入法候选确认不是发送；Shift+Enter 保留换行。
      if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && !this.composing) { event.preventDefault(); this.submit() }
    },
    input(event) {
      this.$emit('update:modelValue', event.target.value)
      event.target.style.height = 'auto'
      event.target.style.height = `${Math.min(280, Math.max(96, event.target.scrollHeight))}px`
    },
    files(event) {
      const files = event.target.files || event.dataTransfer?.files
      if (!this.busy && files?.length) this.$emit('upload', Array.from(files))
      if (event.target.type === 'file') event.target.value = ''
      this.dragging = false
    },
    chooseTemplate() {
      const profile = this.selectedTemplate
      if (profile && profile.availability !== 'planned') {
        this.$emit('update:modelValue', profile.example_questions[0] || '')
        this.$emit('option-change', { category: this.category, profile_ids: this.capabilities.profile_execution ? [profile.id] : [] })
        this.$nextTick(() => this.$refs.question.focus())
      }
    },
  },
}
</script>

<template>
  <form novalidate class="prompt-composer" :class="{ 'is-dragging': dragging }" @submit.prevent="submit" @dragover.prevent="dragging = !busy" @dragleave.prevent="dragging = false" @drop.prevent="files">
    <slot />
    <label class="sr-only" for="analysis-question">分析问题</label>
    <textarea id="analysis-question" ref="question" class="resize-none" :value="modelValue" :disabled="busy" maxlength="2000" rows="3" placeholder="描述你的业务问题，或拖入数据文件…" @input="input" @keydown="handleEnter" @compositionstart="composing = true" @compositionend="composing = false"></textarea>
    <div class="prompt-toolbar">
      <input ref="fileInput" class="sr-only" type="file" multiple :accept="accept" aria-label="选择数据文件" :disabled="busy" @change="files" />
      <el-button native-type="button" class="composer-file" :disabled="busy" @click="$refs.fileInput.click()"><el-icon><Plus /></el-icon><span>文件</span></el-button>
      <label class="composer-choice">分析方向<select v-model="category" :disabled="busy" aria-label="分析方向" @change="templateId = ''; $emit('option-change', { category, profile_ids: [] })"><option value="">自动</option><option v-for="item in catalog.categories" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
      <label class="composer-choice">分析模板<select v-model="templateId" :disabled="busy" aria-label="分析模板" @change="templateId ? chooseTemplate() : $emit('option-change', { profile_ids: [] })"><option value="">自动选择</option><option v-for="item in templates" :key="item.id" :value="item.id" :disabled="item.availability === 'planned'">{{ item.name }}{{ item.availability === 'planned' ? ' · 规划中' : item.availability === 'limited' ? ' · 通用能力' : '' }}</option></select></label>
      <label class="composer-choice">分析深度<select v-model="depth" aria-label="分析深度" :disabled="busy || !capabilities.depth_selection" @change="$emit('option-change', { depth })"><option v-for="value in capabilities.depths || ['STANDARD']" :key="value" :value="value">{{ { FAST: '快速', STANDARD: '标准', DEEP: '深度' }[value] }}</option></select></label>
      <label class="composer-choice">报告类型<select aria-label="报告类型" disabled title="分析完成后可在工件面板生成报告"><option>手动生成</option></select></label>
      <label class="composer-choice model-choice">模型<select v-model="modelId" aria-label="模型" :disabled="busy || !capabilities.model_selection" @change="$emit('option-change', { model_id: modelId || null })"><option value="">{{ capabilities.models?.[0]?.id || '服务端配置' }}</option><option v-for="model in capabilities.models || []" :key="model.id" :value="model.id" :disabled="!model.configured">{{ model.id }}</option></select></label>
      <el-button native-type="submit" type="primary" class="composer-send" :disabled="busy || uploading || !modelValue.trim()" :loading="busy" :aria-busy="busy"><span>{{ busy ? '处理中' : '发送问题' }}</span><el-icon v-if="!busy"><Top /></el-icon></el-button>
    </div>
    <p v-if="selectedTemplate?.availability === 'limited'" class="composer-note">{{ selectedTemplate.constraints?.[1] }}</p>
    <p class="composer-note">Enter 发送 · Shift+Enter 换行 · {{ capabilities.profile_execution ? '模板决定关注点，系统根据数据生成分析计划。' : '模板填入可修改示例；当前分析使用选中的一个数据集。' }}</p>
  </form>
</template>

<style scoped>
.prompt-composer { width: 100%; background: var(--surface); border: 1px solid var(--line); border-radius: 16px; padding: 16px; box-shadow: var(--shadow-card); transition: border-color .15s; }
.prompt-composer:focus-within, .prompt-composer.is-dragging { border-color: var(--brand); }
textarea { width: 100%; height: 112px; min-height: 96px; max-height: 280px; resize: none; border: 0; background: transparent; outline: none; color: var(--ink); font: inherit; line-height: 1.7; }
textarea:disabled { opacity: .65; }
.prompt-toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: flex-end; }
.prompt-toolbar .el-button { height: 36px; margin-left: 0; padding: 0 14px; border-radius: var(--radius-sm); font-size: 12px; }
.prompt-toolbar .el-button :deep(.el-icon) { font-size: 14px; }
.composer-file :deep(.el-icon) { margin-right: 6px; }
.composer-send :deep(.el-icon) { margin-left: 6px; }
select { cursor: pointer; border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--surface); color: var(--ink); height: 36px; }
.composer-choice { display: grid; gap: 3px; font-size: 10px; color: var(--muted); }
select { max-width: 150px; font-size: 12px; padding: 3px 5px; }
select:disabled { cursor: default; opacity: .55; }
.prompt-toolbar .composer-send { margin-left: auto; min-width: 110px; }
.composer-note { color: var(--muted); font-size: 11px; margin: 10px 0 0; line-height: 1.6; }
@media (max-width: 600px) { .model-choice { display: none; } .prompt-composer { padding: 12px; } select { max-width: 120px; } }
</style>
