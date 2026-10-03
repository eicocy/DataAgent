<script>
import { mapState, mapActions } from 'pinia'
import { DataAnalysis, Files, ChatLineRound, Clock, UserFilled } from '@element-plus/icons-vue'

import { useAuthStore } from '../stores/auth'

export default {
  name: 'AppShell',
  components: { DataAnalysis, Files, ChatLineRound, Clock, UserFilled },
  computed: {
    ...mapState(useAuthStore, ['user']),
  },
  methods: {
    ...mapActions(useAuthStore, ['logout']),
    async signOut() {
      await this.logout()
      this.$router.replace({ name: 'login' })
    },
  },
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar" aria-label="主导航">
      <router-link class="brand" :to="{ name: 'dashboard' }">
        <span class="brand-mark"><el-icon><DataAnalysis /></el-icon></span>
        <span><strong>DataLens</strong><small>AGENT WORKSPACE</small></span>
      </router-link>
      <p class="nav-caption">工作空间</p>
      <nav class="nav-list">
        <router-link class="nav-item" :to="{ name: 'dashboard' }" exact-active-class="is-active">
          <el-icon><DataAnalysis /></el-icon><span>Dashboard</span>
        </router-link>
        <router-link class="nav-item" to="/datasets"><el-icon><Files /></el-icon><span>数据集</span></router-link>
        <router-link class="nav-item" to="/analysis"><el-icon><ChatLineRound /></el-icon><span>智能分析</span></router-link>
        <router-link class="nav-item" to="/sessions"><el-icon><Clock /></el-icon><span>分析会话</span></router-link>
        <router-link class="nav-item" to="/history"><el-icon><Clock /></el-icon><span>分析历史</span></router-link>
      </nav>
      <div class="sidebar-bottom">
        <div class="evidence-note"><span class="evidence-dot"></span><span>每个结论都有数据依据</span></div>
        <button class="profile-button" type="button" @click="signOut">
          <span class="avatar"><el-icon><UserFilled /></el-icon></span>
          <span class="profile-copy"><strong>{{ user?.username || '用户' }}</strong><small>退出登录</small></span>
          <span aria-hidden="true">↗</span>
        </button>
      </div>
    </aside>
    <div class="workspace">
      <header class="topbar">
        <span class="breadcrumb">Data workspace <span>/</span> {{ $route.meta.title }}</span>
        <div class="topbar-status"><span class="status-pulse"></span>本地工作区</div>
      </header>
      <main class="page-content"><slot /></main>
    </div>
  </div>
</template>
