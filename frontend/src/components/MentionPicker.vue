<script>
export default {
  name: 'MentionPicker',
  props: { items: { type: Array, default: () => [] }, modelValue: { type: Array, default: () => [] }, busy: Boolean },
  emits: ['update:modelValue'],
  computed: {
    available() { return this.items.filter(item => item.status === 'READY' && ['table', 'chart', 'dataset', 'report', 'excel', 'word', 'pdf'].includes(item.type || item.artifact_type?.toLowerCase())) },
  },
  methods: {
    toggle(item) { if (this.busy) return; const id = item.id || item.artifact_id; this.$emit('update:modelValue', this.modelValue.includes(id) ? this.modelValue.filter(value => value !== id) : [...this.modelValue, id].slice(0, 10)) },
  },
}
</script>
<template>
  <details v-if="available.length" class="mention-picker"><summary>@ 引用已有成果 <span v-if="modelValue.length">· 已选 {{ modelValue.length }}</span></summary><div class="mention-options"><button v-for="item in available" :key="item.id || item.artifact_id" type="button" :disabled="busy" :aria-pressed="modelValue.includes(item.id || item.artifact_id)" @click="toggle(item)">{{ item.name || item.title }}{{ modelValue.includes(item.id || item.artifact_id) ? ' · 已引用' : '' }}</button></div><p>引用使用完整来源与固定版本。切换数据版本后，需要重新核对引用。</p></details>
</template>
<style scoped>
.mention-picker { margin: 8px 0; font-size: 12px; color: var(--muted); }
summary { cursor: pointer; padding: 6px 0; }
.mention-options { display: flex; gap: 6px; flex-wrap: wrap; max-height: 160px; overflow: auto; }
button { cursor: pointer; color: var(--ink); background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius-sm); padding: 7px 10px; text-align: left; overflow-wrap: anywhere; }
button:hover, button[aria-pressed="true"] { border-color: var(--brand); background: var(--canvas); }
button:focus-visible, summary:focus-visible { outline: 2px solid var(--brand); outline-offset: 2px; }
button:disabled { cursor: default; opacity: .55; }
</style>
