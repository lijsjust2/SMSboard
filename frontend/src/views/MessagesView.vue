<template>
  <AppLayout>
    <PageHeader :title="isCall ? '通话记录' : '短信记录'"
      :subtitle="isCall ? '所有设备推送的通话记录，支持按设备/SIM筛选' : '所有设备推送的短信记录，支持按设备/SIM筛选'" />
    <el-card>
      <template #header>
        <div style="display:flex; gap:12px; align-items:center; flex-wrap: wrap">
          <b>{{ isCall ? '通话记录' : '短信记录' }}</b>
          <el-select v-model="deviceId" style="width: 170px" placeholder="全部设备" clearable @change="onDeviceChange">
            <el-option v-for="d in deviceList" :key="d.id" :value="d.id" :label="d.name" />
          </el-select>
          <el-select v-model="simId" style="width: 170px" placeholder="全部SIM卡" clearable>
            <el-option v-for="s in simList" :key="s.id" :value="s.id"
              :label="s.alias || s.slot_key" />
          </el-select>
          <el-input v-model="keyword" placeholder="搜索号码/内容" style="width: 200px" clearable @keyup.enter="load" />
          <el-date-picker v-model="range" type="datetimerange" value-format="YYYY-MM-DD HH:mm:ss"
            start-placeholder="开始时间" end-placeholder="结束时间" style="width: 340px" />
          <el-button type="primary" @click="load">查询</el-button>
          <span style="color:#909399; font-size:12px; margin-left:auto">共 {{ total }} 条</span>
        </div>
      </template>

      <el-table :data="items" stripe style="width: 100%" v-loading="loading">
        <el-table-column prop="receive_time" label="时间" width="170" />
        <el-table-column prop="sender" label="号码" width="150" />
        <el-table-column prop="sim_slot" label="卡槽" width="150" />
        <el-table-column prop="content" label="内容" show-overflow-tooltip>
          <template #default="{ row }">
            <span style="white-space: pre-wrap">{{ row.content }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" plain @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination style="margin-top: 12px; justify-content: flex-end" background layout="prev, pager, next, sizes"
        :total="total" :page-size="size" :current-page="page" :page-sizes="[20, 50, 100]"
        @current-change="(p) => { page = p; load() }" @size-change="(s) => { size = s; page = 1; load() }" />
    </el-card>
  </AppLayout>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '../components/AppLayout.vue'
import PageHeader from '../components/PageHeader.vue'
import api from '../api'
import { onWsEvent } from '../ws'

const route = useRoute()
const isCall = computed(() => !!route.meta.callMode)
const items = ref([])
const total = ref(0)
const page = ref(1)
const size = ref(20)
const keyword = ref('')
const range = ref(null)
const loading = ref(false)
const deviceList = ref([])
const simList = ref([])
const deviceId = ref(null)
const simId = ref(null)

async function load() {
  loading.value = true
  try {
    const params = new URLSearchParams({
      type: isCall.value ? 'call' : 'sms',
      page: String(page.value), size: String(size.value),
      keyword: keyword.value,
      start: range.value?.[0] || '', end: range.value?.[1] || '',
    })
    if (deviceId.value != null) params.set('device_id', String(deviceId.value))
    if (simId.value != null) params.set('sim_id', String(simId.value))
    const r = await api.get(`/api/messages?${params}`)
    items.value = r.items
    total.value = r.total
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function onDeviceChange() {
  simId.value = null
  simList.value = []
  if (deviceId.value) {
    simList.value = (await api.get(`/api/devices/${deviceId.value}/sims`)).items
  }
  page.value = 1
  load()
}

async function remove(row) {
  await ElMessageBox.confirm(
    `确定删除这条${isCall.value ? '通话' : '短信'}记录？（${row.sender} · ${row.receive_time}）`,
    '删除确认', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
  )
  try {
    await api.delete(`/api/messages/${row.id}`)
    ElMessage.success('已删除')
    if (items.value.length === 1 && page.value > 1) page.value -= 1
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

const off = onWsEvent((p) => {
  if (p.event === 'message' && p.type === (isCall.value ? 'call' : 'sms')) load()
})

let pollTimer = null
onMounted(async () => {
  try { deviceList.value = (await api.get('/api/devices')).items } catch { /* 忽略 */ }
  await load()
  // Worker 部署无 WebSocket，退化为定时轮询
  pollTimer = setInterval(() => {
    if (!window.__smsboard_ws_ok) load()
  }, 20000)
})
onUnmounted(() => { off(); if (pollTimer) clearInterval(pollTimer) })
</script>
