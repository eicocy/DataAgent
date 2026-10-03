<script>
import { mapActions } from 'pinia'
import { DataAnalysis } from '@element-plus/icons-vue'

import { useAuthStore } from '../stores/auth'

export default {
  name: 'RegisterView',
  components: { DataAnalysis },
  data() {
    return { form: { username: '', password: '', confirmPassword: '' }, submitting: false, errorMessage: '' }
  },
  methods: {
    ...mapActions(useAuthStore, ['register']),
    async submit() {
      this.errorMessage = ''
      if (!/^[A-Za-z0-9_.-]{4,64}$/.test(this.form.username.trim())) {
        this.errorMessage = '用户名需为 4–64 位字母、数字或 . _ -'
        return
      }
      if (this.form.password.length < 8) {
        this.errorMessage = '密码至少需要 8 位'
        return
      }
      if (this.form.password !== this.form.confirmPassword) {
        this.errorMessage = '两次输入的密码不一致'
        return
      }
      this.submitting = true
      try {
        await this.register({ username: this.form.username.trim(), password: this.form.password })
        this.$router.replace({ name: 'dashboard' })
      } catch (error) {
        this.errorMessage = error.message || '注册失败，请稍后重试'
      } finally {
        this.submitting = false
      }
    },
  },
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-story">
      <router-link class="brand auth-brand" to="/login"><span class="brand-mark"><el-icon><DataAnalysis /></el-icon></span><span><strong>DataLens</strong><small>AGENT WORKSPACE</small></span></router-link>
      <div class="story-copy"><p class="eyebrow">让分析更透明</p><h1>从一张表，<br /><em>找到答案。</em></h1><p class="story-text">创建工作区，上传数据，用真实计算支持每一个结论。</p><div class="story-proof"><span class="proof-line"></span><span>问题 → 工具 → 结果 → 结论</span></div></div>
      <div class="story-footer">DATA ANALYSIS, MADE TRACEABLE <span>·</span> 本机演示版</div>
    </section>
    <section class="auth-panel">
      <div class="auth-card">
        <p class="eyebrow">开始使用</p><h2>创建工作区账号</h2><p class="auth-subtitle">你的数据仅对当前账号开放。</p>
        <form novalidate class="auth-form" @submit.prevent="submit">
          <label for="username">用户名</label><el-input id="username" v-model="form.username" autocomplete="username" placeholder="4–64 位字母、数字或 . _ -" size="large" />
          <label for="password">密码</label><el-input id="password" v-model="form.password" autocomplete="new-password" type="password" show-password placeholder="至少 8 位" size="large" />
          <label for="confirm-password">确认密码</label><el-input id="confirm-password" v-model="form.confirmPassword" autocomplete="new-password" type="password" show-password placeholder="再次输入密码" size="large" />
          <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
          <el-button class="auth-submit" type="primary" native-type="submit" size="large" :loading="submitting">创建账号</el-button>
        </form>
        <p class="auth-switch">已有账号？ <router-link to="/login">返回登录</router-link></p>
      </div>
    </section>
  </main>
</template>
