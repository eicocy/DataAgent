<script>
import AppShell from '../components/AppShell.vue'

export default { name: 'PlaceholderView', components: { AppShell } }
</script>

<template>
  <AppShell>
    <section class="page-heading"><div><p class="eyebrow">开发中</p><h1>{{ $route.meta.title }}</h1><p class="page-intro">此页面将在后续阶段接入真实工作流。</p></div></section>
    <section class="panel placeholder-panel"><span class="evidence-dot"></span><h2>先从数据集开始</h2><p>上传一个 CSV 或 Excel 文件，解析完成后即可继续。</p><el-button type="primary" @click="$router.push('/datasets')">查看数据集</el-button></section>
  </AppShell>
</template>
