import { createApp } from 'vue'
import { createPinia } from 'pinia'
import {
  ElButton,
  ElDialog,
  ElIcon,
  ElInput,
  ElLoading,
  ElPagination,
  ElProgress,
  ElOption,
  ElSelect,
  ElTable,
  ElTableColumn,
  ElTag,
} from 'element-plus'
import 'element-plus/dist/index.css'

import App from './App.vue'
import router from './router'
import './styles/tokens.css'
import './styles/app.css'

const app = createApp(App)
app.use(createPinia()).use(router)
for (const component of [ElButton, ElDialog, ElIcon, ElInput, ElOption, ElPagination, ElProgress, ElSelect, ElTable, ElTableColumn, ElTag]) {
  app.component(component.name, component)
}
app.directive('loading', ElLoading.directive)
app.mount('#app')
