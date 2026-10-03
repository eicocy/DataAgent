<script>
import { useAuthStore } from './stores/auth'
export default {
  name: 'AppRoot',
  created() {
    // API 会话过期时跳回登录页，并保留当前路由供重新登录后返回。
    this.authExpiredHandler = () => {
      const wasAuthenticated = useAuthStore().authStatus === 'authenticated'
      useAuthStore().expireSession()
      if (wasAuthenticated && !this.$route.meta?.public) this.$router.replace({ name: 'login', query: { redirect: this.$route.fullPath } })
    }
    window.addEventListener('datalens:auth-expired', this.authExpiredHandler)
  },
  beforeUnmount() {
    window.removeEventListener('datalens:auth-expired', this.authExpiredHandler)
  },
}
</script>

<template><router-view /></template>
