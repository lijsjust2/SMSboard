import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import App from './App.vue'
import api, { getToken } from './api'

import SetupView from './views/SetupView.vue'
import LoginView from './views/LoginView.vue'
import DashboardView from './views/DashboardView.vue'
import MessagesView from './views/MessagesView.vue'
import DevicesView from './views/DevicesView.vue'
import DeviceView from './views/DeviceView.vue'
import SettingsView from './views/SettingsView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/setup', component: SetupView },
    { path: '/login', component: LoginView },
    { path: '/admin', redirect: '/login' },
    { path: '/', component: DashboardView, meta: { auth: true } },
    { path: '/messages', component: MessagesView, meta: { auth: true } },
    { path: '/calls', component: MessagesView, meta: { auth: true, callMode: true } },
    { path: '/devices', component: DevicesView, meta: { auth: true } },
    { path: '/device', component: DeviceView, meta: { auth: true } },
    { path: '/settings', component: SettingsView, meta: { auth: true } },
  ],
})

router.beforeEach(async (to) => {
  try {
    const { need_setup } = await api.get('/api/setup/status')
    if (need_setup && to.path !== '/setup') return '/setup'
    if (!need_setup && to.path === '/setup') return '/login'
  } catch {
    /* 服务未就绪时放行，页面内会提示 */
  }
  if (to.meta.auth && !getToken()) return '/login'
  return true
})

const app = createApp(App)
app.use(router)
app.use(ElementPlus, { locale: zhCn })
app.mount('#app')
