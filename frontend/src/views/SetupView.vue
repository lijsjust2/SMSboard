<template>
  <div class="setup-wrap">
    <el-card class="setup-card">
      <h2 style="text-align:center; margin: 8px 0 4px">欢迎使用 SmsBoard</h2>
      <p class="tip" style="text-align:center">首次运行，请先设置管理员账号和密码（仅此一次）</p>
      <el-form label-width="80px" @submit.prevent>
        <el-form-item label="账号">
          <el-input v-model="username" placeholder="管理员账号（至少2位）" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="password" type="password" show-password placeholder="密码（至少6位）" />
        </el-form-item>
        <el-form-item label="确认密码">
          <el-input v-model="password2" type="password" show-password />
        </el-form-item>
        <el-button type="primary" style="width: 100%" :loading="loading" @click="doSetup">
          创建管理员并进入
        </el-button>
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
const password2 = ref('')
const loading = ref(false)
const router = useRouter()

async function doSetup() {
  if (password.value !== password2.value) return ElMessage.error('两次密码不一致')
  loading.value = true
  try {
    const r = await api.post('/api/setup/admin', { username: username.value, password: password.value })
    setToken(r.token)
    ElMessage.success('初始化完成')
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
.tip { color: #8a91a8; font-size: 13px; }
</style>
