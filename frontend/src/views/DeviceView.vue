<template>
  <AppLayout>
    <PageHeader title="设备状态" subtitle="设备电量曲线与在线/离线时间线" />
    <div class="card-row">
      <el-card class="stat-card" style="min-width: 49%">
        <template #header>
          当前状态
          <el-select v-model="deviceId" style="width: 200px; margin-left: 12px" @change="reloadAll">
            <el-option v-for="d in deviceList" :key="d.id" :value="d.id"
              :label="`${d.online ? '🟢' : '🔴'} ${d.name}`" />
          </el-select>
        </template>
        <div style="display:flex; align-items:center; gap:24px">
          <div style="position:relative; width:140px; height:140px">
            <div ref="gaugeChart" style="width:140px; height:140px"></div>
            <div v-if="!current.online" class="offline-cover">离线</div>
          </div>
          <div>
            <p><b>状态：</b>
              <el-tag :type="current.online ? 'success' : 'danger'">{{ current.online ? '在线' : '离线' }}</el-tag>
            </p>
            <p><b>最后心跳：</b>{{ current.last_heartbeat || '从未' }}</p>
            <p><b>充电状态：</b>{{ current.plugged ? '🔌 充电中' : '🔋 电池供电' }}</p>
            <p><b>离线阈值：</b>{{ current.threshold_minutes }} 分钟无心跳判离线</p>
            <p v-if="current.battery_info"><b>电池信息：</b>{{ current.battery_info }}</p>
          </div>
        </div>
      </el-card>
      <el-card class="stat-card" style="min-width: 49%">
        <template #header>
          电量曲线
          <el-radio-group v-model="hours" size="small" style="margin-left:12px" @change="loadHistory">
            <el-radio-button :value="6">6小时</el-radio-button>
            <el-radio-button :value="24">24小时</el-radio-button>
            <el-radio-button :value="72">3天</el-radio-button>
            <el-radio-button :value="168">7天</el-radio-button>
          </el-radio-group>
        </template>
        <div ref="batteryChart" style="height: 260px"></div>
      </el-card>
    </div>

    <el-card>
      <template #header>
        最近 50 次心跳
        <span class="muted" style="margin-left:10px; font-size:12px">每条含心跳时间与当时电量</span>
      </template>
      <el-table :data="heartbeats" stripe size="small" max-height="420">
        <el-table-column prop="ts" label="心跳时间" width="180" />
        <el-table-column label="当时电量" width="120">
          <template #default="{ row }">{{ row.battery_pct != null ? row.battery_pct + '%' : '-' }}</template>
        </el-table-column>
        <el-table-column label="充电状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.plugged ? 'success' : 'info'" size="small">
              {{ row.plugged ? '🔌 充电中' : '🔋 电池' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="battery_info" label="电池信息" show-overflow-tooltip />
      </el-table>
      <el-empty v-if="!heartbeats.length" description="暂无心跳记录，等待下一次心跳" :image-size="60" />
    </el-card>
  </AppLayout>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import * as echarts from 'echarts'
import AppLayout from '../components/AppLayout.vue'
import PageHeader from '../components/PageHeader.vue'
import api from '../api'
import { onWsEvent } from '../ws'

const current = ref({})
const events = ref([])
const heartbeats = ref([])
const hours = ref(24)
const deviceList = ref([])
const deviceId = ref(null)
const gaugeChart = ref(null)
const batteryChart = ref(null)
let gaugeInst = null
let batteryInst = null
let timer = null

async function loadStatus() {
  if (!deviceId.value) return
  const r = await api.get(`/api/device/status?device_id=${deviceId.value}`)
  current.value = r.current
  events.value = r.events || []
  heartbeats.value = r.heartbeats || []
  renderGauge()
}

async function loadDevices() {
  deviceList.value = (await api.get('/api/devices')).items
  if (!deviceId.value && deviceList.value.length) {
    const fromQuery = Number(new URLSearchParams(window.location.search).get('device_id'))
    deviceId.value = deviceList.value.some((d) => d.id === fromQuery)
      ? fromQuery : deviceList.value[0].id
  }
}

function renderGauge() {
  const pct = current.value.battery_pct ?? 0
  gaugeInst.setOption({
    series: [{
      type: 'gauge', startAngle: 220, endAngle: -40, min: 0, max: 100,
      progress: { show: true, width: 12, itemStyle: { color: current.value.plugged ? '#67c23a' : '#409eff' } },
      axisLine: { lineStyle: { width: 12 } },
      axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false },
      pointer: { show: false },
      detail: { formatter: '{value}%', fontSize: 26, offsetCenter: [0, 0] },
      data: [{ value: pct }],
    }],
  })
}

async function loadHistory() {
  if (!deviceId.value) return
  const r = await api.get(`/api/battery/history?hours=${hours.value}&device_id=${deviceId.value}`)
  batteryInst.setOption({
    tooltip: { trigger: 'axis', formatter: (ps) => {
      const p = ps[0]
      return `${p.axisValue}<br/>电量: ${p.value}%${p.data.plugged ? ' 🔌' : ''}`
    } },
    grid: { left: 40, right: 20, top: 20, bottom: 60 },
    xAxis: { type: 'category', data: r.items.map((i) => i.ts), axisLabel: { rotate: 30, fontSize: 10 } },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' } },
    series: [{
      type: 'line', smooth: true, symbol: 'none',
      data: r.items.map((i) => ({ value: i.battery_pct, plugged: i.plugged })),
      areaStyle: { opacity: 0.15 }, lineStyle: { color: '#409eff' },
    }],
  })
}

function reloadAll() { loadStatus().then(loadHistory).catch(() => {}) }

onMounted(async () => {
  gaugeInst = echarts.init(gaugeChart.value)
  batteryInst = echarts.init(batteryChart.value)
  await loadDevices()
  await reloadAll()
  timer = setInterval(loadStatus, 30000)
})
onUnmounted(() => { clearInterval(timer); gaugeInst?.dispose(); batteryInst?.dispose() })

onWsEvent((p) => {
  if (['heartbeat', 'device_online', 'device_offline'].includes(p.event)) {
    if (p.device_id == null || p.device_id === deviceId.value) reloadAll()
    loadDevices().catch(() => {})
  }
})
</script>

<style scoped>
.offline-cover {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  background: rgba(255,255,255,.75); border-radius: 50%; color: #f56c6c; font-weight: 700; font-size: 18px;
}
</style>
