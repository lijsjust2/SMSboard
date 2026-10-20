<template>
  <div class="setup-wrap">
    <el-card class="setup-card">
      <div class="login-logo"><span class="logo-badge">S</span></div>
      <h2 style="text-align:center; margin: 8px 0 4px">SmsBoard</h2>
      <p class="tip" style="text-align:center">登录看板管理你的设备</p>
      <el-form label-width="80px" @submit.prevent>
        <el-form-item label="账号">
          <el-input v-model="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="password" type="password" show-password @keyup.enter="doLogin" />
        </el-form-item>
        <el-button type="primary" style="width: 100%" :loading="loading" @click="doLogin">登录</el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api, { setToken } from '../api'

const username = ref('')
const password = ref('')
const loading = ref(false)
const router = useRouter()

async function doLogin() {
  loading.value = true
  try {
    const r = await api.post('/api/auth/login', { username: username.value, password: password.value })
    setToken(r.token)
    router.push('/')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.setup-wrap {
  display: flex; justify-content: center; align-items: center; min-height: 100vh;
  background: linear-gradient(150deg, #eef1fe 0%, #f6f7fb 55%, #eef6f2 100%);
}
.setup-card { width: 400px; border-radius: 16px !important; }
.login-logo { display: flex; justify-content: center; margin-top: 6px; }
.logo-badge {
  width: 52px; height: 52px; border-radius: 14px; display: inline-flex; align-items: center;
  justify-content: center; color: #fff; font-weight: 800; font-size: 26px;
  background: linear-gradient(135deg, #4f6ef7, #7c5cf5); box-shadow: 0 6px 16px rgba(79,110,247,.4);
}
.tip { color: #8a91a8; font-size: 13px; }
</style>
