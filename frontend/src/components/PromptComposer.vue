<script>
export default {
  name: 'PromptComposer',
  props: {
    modelValue: { type: String, default: '' }, busy: Boolean, uploading: Boolean,
    catalog: { type: Object, default: () => ({ categories: [], items: [] }) },
    capabilities: { type: Object, default: () => ({ file_formats: ['csv', 'tsv', 'json', 'xlsx', 'xls', 'parquet'] }) },
  },
  emits: ['update:modelValue', 'submit', 'upload', 'option-change', 'templates'],
  data() { return { category: '', templateId: '', dragging: false, composing: false } },
  computed: {
    accept() { return (this.capabilities.file_formats || []).map(ext => `.${ext}`).join(',') },
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
        this.$emit('option-change', { category: this.category, template_id: profile.id })
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
      <button type="button" class="composer-file" :disabled="busy" @click="$refs.fileInput.click()">＋ 文件</button>
      <label class="composer-choice">分析方向<select v-model="category" :disabled="busy" aria-label="分析方向" @change="templateId = ''; $emit('option-change', { category })"><option value="">自动</option><option v-for="item in catalog.categories" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
      <label class="composer-choice">分析模板<select v-model="templateId" :disabled="busy" aria-label="分析模板" @change="chooseTemplate"><option value="">选择示例</option><option v-for="item in templates" :key="item.id" :value="item.id" :disabled="item.availability === 'planned'">{{ item.name }}{{ item.availability === 'planned' ? ' · 规划中' : item.availability === 'limited' ? ' · 通用能力' : '' }}</option></select></label>
      <label class="composer-choice">分析深度<select aria-label="分析深度" disabled title="当前执行标准分析，深度预算在后续阶段开放"><option>标准</option></select></label>
      <label class="composer-choice">报告类型<select aria-label="报告类型" disabled title="分析完成后可在工件面板生成报告"><option>手动生成</option></select></label>
      <label class="composer-choice model-choice">模型<select aria-label="模型" disabled><option>{{ capabilities.models?.[0]?.id || '服务端配置' }}</option></select></label>
      <button type="submit" class="composer-send" :disabled="busy || uploading || !modelValue.trim()" :aria-busy="busy">{{ busy ? '处理中' : '发送问题' }} <span aria-hidden="true">↑</span></button>
    </div>
    <p v-if="selectedTemplate?.availability === 'limited'" class="composer-note">{{ selectedTemplate.constraints?.[1] }}</p>
    <p class="composer-note">Enter 发送 · Shift+Enter 换行 · 模板填入可修改示例；当前分析使用选中的一个数据集。</p>
  </form>
</template>

<style scoped>
.prompt-composer { width: 100%; background: var(--surface); border: 1px solid var(--line); border-radius: 16px; padding: 16px; box-shadow: var(--shadow-card); transition: border-color .15s; }
.prompt-composer:focus-within, .prompt-composer.is-dragging { border-color: var(--brand); }
textarea { width: 100%; height: 112px; min-height: 96px; max-height: 280px; resize: none; border: 0; background: transparent; outline: none; color: var(--ink); font: inherit; line-height: 1.7; }
textarea:disabled { opacity: .65; }
.prompt-toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.prompt-toolbar button, select { cursor: pointer; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); color: var(--ink); min-height: 32px; }
.prompt-toolbar button { padding: 6px 12px; }
.prompt-toolbar button:hover:not(:disabled) { background: var(--canvas); }
.composer-choice { display: grid; gap: 3px; font-size: 10px; color: var(--muted); }
select { max-width: 150px; font-size: 12px; padding: 3px 5px; }
select:disabled, button:disabled { cursor: default; opacity: .55; }
.prompt-toolbar .composer-send { margin-left: auto; background: var(--ink); color: var(--surface); min-width: 96px; }
.prompt-toolbar .composer-send:hover:not(:disabled) { background: var(--brand); }
.composer-note { color: var(--muted); font-size: 11px; margin: 10px 0 0; line-height: 1.6; }
@media (max-width: 600px) { .model-choice { display: none; } .prompt-composer { padding: 12px; } select { max-width: 120px; } }
</style>
