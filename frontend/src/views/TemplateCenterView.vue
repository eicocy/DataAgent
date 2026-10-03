<script>
import AppShell from '../components/AppShell.vue'
import { workspaceApi } from '../api/workspace'

export default {
  name: 'TemplateCenterView', components: { AppShell },
  data() { return { catalog: { categories: [], items: [] }, category: 'general', query: '', loading: true, error: '', controller: null } },
  computed: {
    profiles() { return this.catalog.items.filter(item => (!this.category || item.category === this.category) && `${item.name} ${item.description} ${item.example_questions.join(' ')}`.toLowerCase().includes(this.query.trim().toLowerCase())) },
  },
  created() { this.load() },
  beforeUnmount() { this.controller?.abort(); this.controller = null },
  methods: {
    async load() {
      this.controller?.abort()
      const controller = new AbortController()
      this.controller = controller
      this.loading = true
      this.error = ''
      try { const catalog = await workspaceApi.profiles({}, { signal: controller.signal }); if (this.controller === controller && !controller.signal.aborted) this.catalog = catalog }
      catch (error) { if (this.controller === controller && !controller.signal.aborted) this.error = error.message || '模板目录加载失败' }
      finally { if (this.controller === controller) this.loading = false }
    },
    choose(profile) {
      if (profile.availability === 'planned') return
      this.$router.push({ name: 'workspace', query: { question: profile.example_questions[0] } })
    },
    status(profile) { return ({ available: '可用', limited: '通用能力', planned: '规划中' })[profile.availability] },
  },
}
</script>

<template>
  <AppShell>
    <header class="page-heading"><div><p class="eyebrow">从业务问题开始</p><h1>分析模板</h1><p class="page-intro">选择一个示例，修改成你的问题。计划会根据实际数据生成。</p></div></header>
    <div class="template-controls"><label for="template-search">搜索模板</label><input id="template-search" ref="search" v-model="query" type="search" placeholder="搜索名称或用途" /><button v-if="query" type="button" aria-label="清除模板搜索" @click="query = ''; $refs.search.focus()">清除</button></div>
    <nav class="template-categories" aria-label="分析方向"><button v-for="item in catalog.categories" :key="item.id" type="button" :aria-pressed="category === item.id" @click="category = item.id">{{ item.name }}</button></nav>
    <p v-if="loading" role="status">正在加载分析模板…</p>
    <p v-else-if="error" class="inline-error" role="alert">{{ error }} <button type="button" @click="load">重试</button></p>
    <p v-else-if="!profiles.length" role="status">没有匹配模板，请更换分析方向或清除搜索。</p>
    <section v-else class="template-grid" aria-label="模板列表"><article v-for="profile in profiles" :key="profile.id" class="panel template-card">
      <div class="template-title"><h2>{{ profile.name }}</h2><span :class="`availability-${profile.availability}`">{{ status(profile) }}</span></div>
      <p>{{ profile.description }}</p>
      <dl><dt>示例问题</dt><dd>{{ profile.example_questions[0] }}</dd><dt>推荐数据</dt><dd>{{ profile.recommended_data.join('；') }}</dd><dt>生成内容</dt><dd>{{ profile.output_artifacts.length ? profile.output_artifacts.join(' · ') : '能力开放后提供' }}</dd></dl>
      <p v-if="profile.availability === 'limited'" class="template-limit">{{ profile.constraints[1] }}</p>
      <button type="button" class="template-use" :disabled="profile.availability === 'planned'" @click="choose(profile)">{{ profile.availability === 'planned' ? '规划中' : '使用这个问题 ↗' }}</button>
    </article></section>
  </AppShell>
</template>

<style scoped>
.template-controls { display: flex; gap: 10px; align-items: center; margin: 20px 0; font-size: 13px; }
input { padding: 10px 12px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); width: min(320px, 60vw); }
button { cursor: pointer; border: 1px solid var(--line); border-radius: 8px; padding: 8px 12px; color: var(--ink); background: var(--surface); }
button:hover:not(:disabled) { background: var(--canvas); }
button:disabled { cursor: default; opacity: .55; }
.template-categories { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 24px; }
.template-categories button { font-size: 12px; }
.template-categories button[aria-pressed=true] { background: var(--ink); color: var(--surface); }
.template-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(300px, 100%), 1fr)); gap: 16px; }
.template-card { padding: 22px; display: flex; flex-direction: column; }
.template-title { display: flex; gap: 12px; align-items: center; justify-content: space-between; }
.template-title h2 { font-size: 16px; }
.template-title span { font-size: 11px; white-space: nowrap; color: var(--muted); }
.availability-available { color: var(--evidence) !important; }
.template-card p, dd { font-size: 12px; line-height: 1.8; color: var(--muted); }
dt { font-size: 11px; color: var(--ink); margin-top: 12px; }
dd { margin: 4px 0 0; }
.template-use { margin-top: auto; align-self: start; }
.template-limit { padding: 8px; background: var(--canvas); border-radius: 8px; }
</style>
