<script>
import { mapActions } from 'pinia'
import { DataAnalysis, Lock, User } from '@element-plus/icons-vue'

import { useAuthStore } from '../stores/auth'

export default {
  name: 'LoginView',
  components: { DataAnalysis, Lock, User },
  data() {
    return { form: { username: '', password: '' }, submitting: false, errorMessage: '' }
  },
  methods: {
    ...mapActions(useAuthStore, ['login']),
    async submit() {
      this.errorMessage = ''
      if (!this.form.username.trim() || !this.form.password) {
        this.errorMessage = '请输入用户名和密码'
        return
      }
      this.submitting = true
      try {
        await this.login(this.form)
        const redirect = typeof this.$route.query.redirect === 'string' ? this.$route.query.redirect : '/'
        this.$router.replace(redirect)
      } catch (error) {
        this.errorMessage = error.message || '登录失败，请稍后重试'
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
      <router-link class="brand auth-brand" to="/login">
        <span class="brand-mark"><el-icon><DataAnalysis /></el-icon></span>
        <span><strong>DataLens</strong><small>AGENT WORKSPACE</small></span>
      </router-link>
      <div class="story-copy">
        <p class="eyebrow">从问题到证据</p>
        <h1>让数据自己<br /><em>说清楚。</em></h1>
        <p class="story-text">用自然语言开始分析。每一步计算都有记录，每一个结论都能回到数据。</p>
        <div class="story-proof"><span class="proof-line"></span><span>问题 → 工具 → 结果 → 结论</span></div>
      </div>
      <div class="story-footer">DATA ANALYSIS, MADE TRACEABLE <span>·</span> 本机演示版</div>
    </section>
    <section class="auth-panel">
      <div class="auth-card">
        <p class="eyebrow">欢迎回来</p>
        <h2>登录工作区</h2>
        <p class="auth-subtitle">继续查看数据集与分析记录。</p>
        <form novalidate class="auth-form" @submit.prevent="submit">
          <label for="username">用户名</label>
          <el-input id="username" v-model="form.username" autocomplete="username" placeholder="请输入用户名" size="large">
            <template #prefix><el-icon><User /></el-icon></template>
          </el-input>
          <label for="password">密码</label>
          <el-input id="password" v-model="form.password" autocomplete="current-password" type="password" show-password placeholder="请输入密码" size="large">
            <template #prefix><el-icon><Lock /></el-icon></template>
          </el-input>
          <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
          <el-button class="auth-submit" type="primary" native-type="submit" size="large" :loading="submitting">登录</el-button>
        </form>
        <p class="auth-switch">还没有账号？ <router-link to="/register">创建账号</router-link></p>
        <p class="auth-security"><span class="security-lock">⌑</span> 登录凭据通过安全连接验证，不会保存在浏览器中。</p>
      </div>
    </section>
  </main>
</template>
