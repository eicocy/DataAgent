<script>
import { ElButton, ElIcon } from 'element-plus'
import { Plus, Top } from '@element-plus/icons-vue'
import ComposerSettingsPopover from './ComposerSettingsPopover.vue'

export default {
  name: 'PromptComposer',
  components: { ComposerSettingsPopover, ElButton, ElIcon, Plus, Top },
  props: {
    modelValue: { type: String, default: '' }, busy: Boolean, uploading: Boolean,
    interruptible: Boolean, interruptDisabled: Boolean, interrupting: Boolean,
    catalog: { type: Object, default: () => ({ categories: [], items: [] }) },
    capabilities: { type: Object, default: () => ({ file_formats: ['csv', 'tsv', 'json', 'xlsx', 'xls', 'parquet'] }) },
    options: { type: Object, default: () => ({}) },
  },
  emits: ['update:modelValue', 'submit', 'interrupt', 'upload', 'option-change', 'templates'],
  data() { return { dragging: false, composing: false } },
  watch: {
    modelValue() { this.$nextTick(this.resizeInput) },
  },
  computed: {
    accept() { return [...(this.capabilities.file_formats || []), ...(this.capabilities.document_formats || [])].map(ext => `.${ext}`).join(',') },
    summary() {
      const profile = (this.catalog.items || []).find(item => item.id === this.options.profile_ids?.[0])
      return `${profile?.name || '自动'} · ${{ FAST: '快速', STANDARD: '标准', DEEP: '深度' }[this.options.depth || 'STANDARD'] || '标准'}`
    },
  },
  mounted() { this.resizeInput() },
  methods: {
    submit() { if (!this.busy && !this.uploading && this.modelValue.trim() && !this.composing) this.$emit('submit') },
    // 中断只发出操作事件，任务终止与确认交由工作台处理。
    interrupt() { if (this.busy && this.interruptible && !this.interruptDisabled && !this.interrupting) this.$emit('interrupt') },
    handleEnter(event) {
      // 中文输入法候选确认不是发送；Shift+Enter 保留换行。
      if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && !this.composing) { event.preventDefault(); this.submit() }
    },
    input(event) {
      this.$emit('update:modelValue', event.target.value)
      this.resizeInput()
    },
    resizeInput() {
      const input = this.$refs.question
      if (!input) return
      input.style.height = 'auto'
      input.style.height = `${Math.min(240, Math.max(88, input.scrollHeight))}px`
    },
    files(event) {
      const files = event.target.files || event.dataTransfer?.files
      if (!this.busy && files?.length) this.$emit('upload', Array.from(files))
      if (event.target.type === 'file') event.target.value = ''
      this.dragging = false
    },
    chooseTemplate(profile, category) {
      if (profile && profile.availability !== 'planned') {
        this.$emit('update:modelValue', profile.example_questions[0] || '')
        this.$emit('option-change', { category, profile_ids: this.capabilities.profile_execution ? [profile.id] : [] })
      }
    },
  },
}
</script>

<template>
  <form novalidate class="prompt-composer" :class="{ 'is-dragging': dragging }" @submit.prevent="submit" @dragover.prevent="dragging = !busy" @dragleave.prevent="dragging = false" @drop.prevent="files">
    <div v-if="$slots.attachments || $slots.default" class="composer-attachments"><slot name="attachments"><slot /></slot></div>
    <label class="sr-only" for="analysis-question">分析问题</label>
    <textarea id="analysis-question" ref="question" class="resize-none" :value="modelValue" :disabled="busy" maxlength="2000" rows="3" placeholder="输入问题…" @input="input" @keydown="handleEnter" @compositionstart="composing = true" @compositionend="composing = false"></textarea>
    <div class="prompt-toolbar">
      <input ref="fileInput" class="sr-only" type="file" multiple :accept="accept" aria-label="选择数据文件" :disabled="busy" @change="files" />
      <slot name="add" :upload="() => $refs.fileInput.click()"><el-button native-type="button" class="composer-file" :disabled="busy" aria-label="添加附件" title="添加附件" @click="$refs.fileInput.click()"><el-icon><Plus /></el-icon></el-button></slot>
      <ComposerSettingsPopover :catalog="catalog" :capabilities="capabilities" :options="options" :busy="busy" @option-change="$emit('option-change', $event)" @template-select="chooseTemplate" />
      <span class="composer-summary" :title="summary" aria-label="当前分析配置">{{ summary }}</span>
      <el-button v-if="busy && interruptible" native-type="button" class="composer-send composer-interrupt run-stop-button" :disabled="interruptDisabled || interrupting" :aria-label="interrupting ? '正在中断分析' : '中断分析'" :title="interrupting ? '正在中断，等待服务端确认' : '中断分析'" :aria-busy="interrupting" @click="interrupt"><span v-if="interrupting" class="run-stop-spinner" aria-hidden="true"></span><span class="run-stop-glyph" aria-hidden="true"></span><span class="sr-only">{{ interrupting ? '正在中断…' : '中断' }}</span></el-button>
      <el-button v-else native-type="submit" type="primary" class="composer-send" :disabled="busy || uploading || !modelValue.trim()" :loading="busy" :aria-busy="busy" :aria-label="busy ? '处理中' : '发送问题'" :title="busy ? '处理中' : '发送问题'"><span class="sr-only">{{ busy ? '处理中' : '发送问题' }}</span><el-icon v-if="!busy"><Top /></el-icon></el-button>
    </div>
  </form>
  <p class="composer-keyboard-hint">Enter 发送 · Shift+Enter 换行</p>
</template>

<style scoped>
.prompt-composer { width: 100%; background: var(--surface); border: 1px solid var(--line); border-radius: 16px; padding: 16px; box-shadow: var(--shadow-card); transition: border-color .15s; }
.prompt-composer:focus-within, .prompt-composer.is-dragging { border-color: var(--brand); }
textarea { display: block; width: 100%; height: 88px; min-height: 88px; max-height: 240px; padding: 0; resize: none; border: 0; background: transparent; outline: none; color: var(--ink); font: inherit; font-size: 14px; line-height: 1.7; }
textarea:disabled { opacity: .65; }
.prompt-toolbar { display: flex; gap: 4px; align-items: center; min-width: 0; min-height: 44px; margin-top: 12px; }
.prompt-toolbar .composer-file { width: 40px; height: 40px; flex-shrink: 0; margin: 0; padding: 0; border-color: transparent; border-radius: 9px; color: var(--muted); background: transparent; }
.prompt-toolbar .composer-file:hover { color: var(--ink); background: var(--canvas); }
.prompt-toolbar .el-button :deep(.el-icon) { font-size: 14px; }
.composer-file :deep(.el-icon) { font-size: 20px; }
.composer-send :deep(.el-icon) { margin: 0; font-size: 20px; }
.prompt-toolbar .composer-send { width: 44px; height: 44px; min-width: 44px; flex-shrink: 0; margin: 0 0 0 8px; padding: 0; border-radius: 50%; }
.composer-summary { flex: 1; min-width: 0; padding-left: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); font-size: 12px; }
.composer-attachments { margin-bottom: 12px; } .composer-attachments:empty { display: none; }
.composer-keyboard-hint { margin: 6px 16px 0; color: var(--muted); font-size: 11px; line-height: 1.6; text-align: right; }
@media (max-width: 600px) { .composer-keyboard-hint { display: none; } }
</style>
