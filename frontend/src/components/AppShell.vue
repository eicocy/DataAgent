<script>
import { mapState, mapActions } from 'pinia'
import { DataAnalysis, Files, ChatLineRound, Clock, UserFilled, Plus, Star, EditPen, Delete, Menu } from '@element-plus/icons-vue'

import { useAuthStore } from '../stores/auth'
import { analysisApi } from '../api/analysis'

export default {
  name: 'AppShell',
  components: { DataAnalysis, Files, ChatLineRound, Clock, UserFilled, Plus, Star, EditPen, Delete, Menu },
  data() {
    return { recentSessions: [], recentLoading: false, mobileSidebarOpen: false,
      editingSessionId: null, editingTitle: '', renameSaving: false,
      deleteSessionId: null, deleteDialogOpen: false, deletingSession: false,
      sidebarError: '' }
  },
  computed: {
    ...mapState(useAuthStore, ['user']),
  },
  watch: {
    '$route.params.sessionId'() { this.loadRecentSessions() },
  },
  created() { this.loadRecentSessions() },
  methods: {
    ...mapActions(useAuthStore, ['logout']),
    async loadRecentSessions() {
      this.recentLoading = true
      try {
        const result = await analysisApi.sessions({ page: 1, page_size: 20 })
        this.recentSessions = result.items || []
        this.sidebarError = ''
      } catch (error) {
        if (error.code !== 'ERR_CANCELED') this.sidebarError = error.message || '会话列表加载失败'
      } finally { this.recentLoading = false }
    },
    newConversation() {
      this.mobileSidebarOpen = false
      this.$router.push({ name: 'analysis' })
    },
    openConversation(session) {
      this.mobileSidebarOpen = false
      this.$router.push({ name: 'analysis', params: { sessionId: session.id } })
    },
    startRename(session) {
      this.editingSessionId = session.id
      this.editingTitle = session.title || ''
    },
    async saveRename(session) {
      if (this.renameSaving || this.editingSessionId !== session.id) return
      const title = this.editingTitle.trim()
      if (!title) { this.editingSessionId = null; return }
      this.renameSaving = true
      try {
        const changed = await analysisApi.updateSession(session.id, { title })
        Object.assign(session, changed)
        this.editingSessionId = null
      } catch (error) { this.sidebarError = error.message || '会话重命名失败' }
      finally { this.renameSaving = false }
    },
    async togglePinned(session) {
      try {
        const changed = await analysisApi.updateSession(session.id, { is_pinned: !session.is_pinned })
        Object.assign(session, changed)
        this.recentSessions.sort((left, right) => Number(right.is_pinned) - Number(left.is_pinned))
      } catch (error) { this.sidebarError = error.message || '置顶状态更新失败' }
    },
    async confirmDeleteSession() {
      if (!this.deleteDialogOpen || !this.deleteSessionId || this.deletingSession) return
      this.deletingSession = true
      try {
        await analysisApi.removeSession(this.deleteSessionId)
        const deletedId = this.deleteSessionId
        this.deleteSessionId = null
        this.deleteDialogOpen = false
        if (Number(this.$route.params.sessionId) === deletedId) this.$router.replace({ name: 'analysis' })
        await this.loadRecentSessions()
      } catch (error) { this.sidebarError = error.message || '会话删除失败' }
      finally { this.deletingSession = false }
    },
    async signOut() {
      await this.logout()
      this.$router.replace({ name: 'login' })
    },
  },
}
</script>

<template>
  <div class="app-shell">
    <div v-if="mobileSidebarOpen" class="sidebar-backdrop" @click="mobileSidebarOpen = false"></div>
    <aside class="sidebar" :class="{ 'is-open': mobileSidebarOpen }" aria-label="主导航">
      <router-link class="brand" :to="{ name: 'dashboard' }">
        <span class="brand-mark"><el-icon><DataAnalysis /></el-icon></span>
        <span><strong>DataLens</strong><small>AGENT WORKSPACE</small></span>
      </router-link>
      <p class="nav-caption">工作空间</p>
      <nav class="nav-list">
        <router-link class="nav-item" :to="{ name: 'dashboard' }" exact-active-class="is-active" @click="mobileSidebarOpen = false">
          <el-icon><DataAnalysis /></el-icon><span>Dashboard</span>
        </router-link>
        <router-link class="nav-item" to="/datasets" @click="mobileSidebarOpen = false"><el-icon><Files /></el-icon><span>数据集</span></router-link>
        <router-link class="nav-item" to="/analysis" @click="mobileSidebarOpen = false"><el-icon><ChatLineRound /></el-icon><span>智能分析</span></router-link>
        <router-link class="nav-item" to="/sessions" @click="mobileSidebarOpen = false"><el-icon><Clock /></el-icon><span>分析会话</span></router-link>
        <router-link class="nav-item" to="/files" @click="mobileSidebarOpen = false"><el-icon><Files /></el-icon><span>文件与工件</span></router-link>
        <router-link class="nav-item" to="/history" @click="mobileSidebarOpen = false"><el-icon><Clock /></el-icon><span>分析历史</span></router-link>
      </nav>
      <section class="sidebar-conversations" aria-label="最近会话">
        <div class="sidebar-section-heading"><span>最近会话</span><button type="button" aria-label="新建分析" @click="newConversation"><el-icon><Plus /></el-icon></button></div>
        <p v-if="sidebarError" class="sidebar-error" role="alert">{{ sidebarError }}</p>
        <p v-else-if="recentLoading && !recentSessions.length" class="sidebar-empty">正在加载…</p>
        <p v-else-if="!recentSessions.length" class="sidebar-empty">还没有会话</p>
        <div v-for="session in recentSessions" :key="session.id" class="sidebar-conversation" :class="{ 'is-active': Number($route.params.sessionId) === session.id }">
          <button v-if="editingSessionId !== session.id" type="button" class="sidebar-conversation-title" @click="openConversation(session)"><el-icon v-if="session.is_pinned"><Star /></el-icon><span>{{ session.title || '新分析' }}</span></button>
          <el-input v-else v-model="editingTitle" size="small" maxlength="200" autofocus :disabled="renameSaving" @keydown.enter.prevent="saveRename(session)" @blur="saveRename(session)" />
          <div class="sidebar-conversation-actions"><button type="button" :aria-label="session.is_pinned ? '取消置顶' : '置顶会话'" @click="togglePinned(session)"><el-icon><Star /></el-icon></button><button type="button" aria-label="重命名会话" @click="startRename(session)"><el-icon><EditPen /></el-icon></button><button type="button" aria-label="删除会话" @click="deleteSessionId = session.id; deleteDialogOpen = true"><el-icon><Delete /></el-icon></button></div>
        </div>
      </section>
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
        <button type="button" class="mobile-menu-button" aria-label="打开导航" @click="mobileSidebarOpen = !mobileSidebarOpen"><el-icon><Menu /></el-icon></button>
        <span class="breadcrumb">Data workspace <span>/</span> {{ $route.meta.title }}</span>
        <div class="topbar-status"><span class="status-pulse"></span>本地工作区</div>
      </header>
      <main class="page-content"><slot /></main>
    </div>
    <el-dialog v-model="deleteDialogOpen" title="删除会话" width="min(420px, 92vw)" :close-on-click-modal="false" @closed="deleteSessionId = null">
      <p class="dialog-copy">删除后，该会话的消息、报告和分析证据将一并移除；数据集文件会保留。</p>
      <template #footer><el-button @click="deleteDialogOpen = false">取消</el-button><el-button type="danger" :loading="deletingSession" @click="confirmDeleteSession">确认删除</el-button></template>
    </el-dialog>
  </div>
</template>
