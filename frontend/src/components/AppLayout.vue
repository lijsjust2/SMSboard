<template>
  <el-container class="shell">
    <!-- 桌面端侧边栏 -->
    <aside class="sidebar">
      <div class="logo">
        <span class="logo-badge">S</span>
        <span class="logo-text">SmsBoard</span>
      </div>
      <el-menu :default-active="active" router class="side-menu">
        <el-menu-item index="/"><el-icon><Odometer /></el-icon>仪表盘</el-menu-item>
        <el-menu-item index="/messages"><el-icon><ChatDotRound /></el-icon>短信记录</el-menu-item>
        <el-menu-item index="/calls"><el-icon><Phone /></el-icon>通话记录</el-menu-item>
        <el-menu-item index="/devices"><el-icon><Iphone /></el-icon>设备管理</el-menu-item>
        <el-menu-item index="/device"><el-icon><TrendCharts /></el-icon>设备状态</el-menu-item>
        <el-menu-item index="/settings"><el-icon><Setting /></el-icon>系统设置</el-menu-item>
      </el-menu>
      <div class="side-footer">
        <div class="admin-chip">
          <span class="admin-avatar">{{ (username || 'A')[0].toUpperCase() }}</span>
          <div style="flex:1">
            <div class="admin-name">{{ username || 'Admin' }}</div>
            <div class="admin-role">Administrator</div>
          </div>
          <el-button link type="danger" @click="logout">退出</el-button>
        </div>
      </div>
    </aside>

    <!-- 移动端抽屉 -->
    <el-drawer v-model="drawer" direction="ltr" size="230px" :with-header="false">
      <div class="logo" style="padding: 16px 14px 8px">
        <span class="logo-badge">S</span><span class="logo-text">SmsBoard</span>
      </div>
      <el-menu :default-active="active" router @select="drawer = false">
        <el-menu-item index="/">仪表盘</el-menu-item>
        <el-menu-item index="/messages">短信记录</el-menu-item>
        <el-menu-item index="/calls">通话记录</el-menu-item>
        <el-menu-item index="/devices">设备管理</el-menu-item>
        <el-menu-item index="/device">设备状态</el-menu-item>
        <el-menu-item index="/settings">系统设置</el-menu-item>
      </el-menu>
      <div style="padding: 12px">
        <el-button style="width: 100%" type="danger" plain @click="logout">退出登录</el-button>
      </div>
    </el-drawer>

    <el-container class="body-col">
      <header class="topbar">
        <el-button class="burger" text @click="drawer = true">
          <el-icon :size="20"><Menu /></el-icon>
        </el-button>
      </header>
      <el-main class="page">
        <slot />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Menu, Odometer, ChatDotRound, Phone, Iphone, TrendCharts, Setting } from '@element-plus/icons-vue'
import { clearToken } from '../api'
import { startWs, stopWs } from '../ws'

const route = useRoute()
const router = useRouter()
const active = computed(() => route.path)
const drawer = ref(false)
const username = ref('')

let timer
onMounted(async () => {
  startWs()
  try { username.value = (await (await import('../api')).default.get('/api/auth/me')).username } catch { /* 忽略 */ }
})
onUnmounted(() => { stopWs() })

function logout() {
  clearToken()
  router.push('/login')
}
</script>

<style scoped>
.shell { min-height: 100vh; }
.sidebar {
  width: 220px; flex-shrink: 0; background: #fff;
  border-right: 1px solid #eef0f6; display: flex; flex-direction: column;
  position: sticky; top: 0; height: 100vh;
}
.logo { display: flex; align-items: center; gap: 10px; padding: 18px 16px 14px; }
.logo-badge {
  width: 34px; height: 34px; border-radius: 10px; display: inline-flex;
  align-items: center; justify-content: center; color: #fff; font-weight: 800; font-size: 17px;
  background: linear-gradient(135deg, #4f6ef7, #7c5cf5); box-shadow: 0 4px 10px rgba(79, 110, 247, .35);
}
.logo-text { font-weight: 800; font-size: 17px; color: #23283f; }
.side-menu { border-right: none !important; padding: 4px 10px; }
.side-menu :deep(.el-menu-item) {
  border-radius: 10px; margin: 3px 0; height: 44px; color: #4a5080;
}
.side-menu :deep(.el-menu-item.is-active) {
  background: #eef1fe; color: #4f6ef7; font-weight: 600;
}
.side-menu :deep(.el-menu-item:hover) { background: #f5f7ff; }
.side-footer { margin-top: auto; padding: 14px; border-top: 1px solid #f0f2f8; }
.admin-chip { display: flex; align-items: center; gap: 10px; }
.admin-avatar {
  width: 34px; height: 34px; border-radius: 50%; background: linear-gradient(135deg, #4f6ef7, #7c5cf5);
  color: #fff; display: inline-flex; align-items: center; justify-content: center; font-weight: 700;
}
.admin-name { font-size: 13px; font-weight: 600; color: #2c3150; }
.admin-role { font-size: 11px; color: #9aa0b5; }

.body-col { min-width: 0; }
.topbar { display: none; }
.burger { display: none; }

@media (max-width: 768px) {
  .sidebar { display: none; }
  .topbar {
    display: flex; align-items: center; height: 46px; padding: 0 8px;
    background: #fff; border-bottom: 1px solid #eef0f6; position: sticky; top: 0; z-index: 50;
  }
  .burger { display: inline-flex; color: #4a5080; }
}
</style>
