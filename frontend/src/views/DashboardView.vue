<template>
  <AppLayout>
    <PageHeader title="仪表盘" subtitle="设备在线状态、消息统计与活跃时段总览">
      <el-select v-model="deviceId" style="width: 220px" @change="reloadAll">
        <el-option :value="null" label="全部设备" />
        <el-option v-for="d in deviceList" :key="d.id" :value="d.id"
          :label="`${d.online ? '🟢' : '🔴'} ${d.name}`" />
      </el-select>
      <el-button :icon="Refresh" @click="reloadAll">刷新</el-button>
    </PageHeader>

    <!-- 设备总览 -->
    <el-card class="mb16">
      <template #header>
        <div style="display:flex; align-items:center">
          <b>设备总览</b>
          <span class="muted" style="margin-left:10px">
            共 {{ deviceList.length }} 台 · 在线 {{ onlineCount }} 台
          </span>
        </div>
      </template>
      <el-empty v-if="!deviceList.length" description="还没有设备，请在手机 SmsForwarder 配置 Webhook 推送" :image-size="70" />
      <div v-else class="device-grid">
        <div v-for="d in deviceList" :key="d.id" class="device-chip"
             :class="{ selected: deviceId === d.id }" @click="goDevice(d)">
          <div class="dc-head">
            <span class="dc-name">{{ d.name }}</span>
            <span class="dc-state" :class="d.online ? 'on' : 'off'">
              {{ d.online ? '在线' : '离线' }}
            </span>
          </div>
          <div class="dc-meta">
            <span>{{ d.plugged ? '🔌' : '🔋' }} {{ d.battery_pct != null ? d.battery_pct + '%' : '--' }}</span>
            <span>💬 {{ d.sms_total }}</span>
            <span>📞 {{ d.call_total }}</span>
            <span>⏱ {{ fmtDur(d.working_seconds_today) }}</span>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 统计卡片 -->
    <div class="card-row">
      <el-card class="stat-card">
        <div class="num">{{ fmtDur(summary.working_seconds_today) }}</div>
        <div class="label">今日工作时长</div>
      </el-card>
      <el-card class="stat-card">
        <div class="num">{{ fmtDur(summary.working_seconds_total) }}</div>
        <div class="label">累计工作时长</div>
      </el-card>
      <el-card class="stat-card">
        <div class="num">{{ summary.sms_today }} <span class="dim">/ {{ summary.sms_total }}</span></div>
        <div class="label">今日 / 累计短信</div>
      </el-card>
      <el-card class="stat-card">
        <div class="num">{{ summary.call_today }} <span class="dim">/ {{ summary.call_total }}</span></div>
        <div class="label">今日 / 累计电话</div>
      </el-card>
      <el-card class="stat-card">
        <div class="num">{{ summary.battery_pct != null ? summary.battery_pct + '%' : '--' }}</div>
        <div class="label">{{ summary.plugged ? '充电中' : '当前电量' }}</div>
      </el-card>
    </div>

    <div class="card-row">
      <el-card class="grow-card">
        <template #header>近 7 天消息与工作时长</template>
        <div ref="dailyChart" style="height: 300px"></div>
      </el-card>
    </div>
    <div class="card-row">
      <el-card class="half-card">
        <template #header>活跃时段分布（近 7 天）</template>
        <div ref="hourlyChart" style="height: 280px"></div>
      </el-card>
      <el-card class="half-card">
        <template #header>最近消息</template>
        <el-empty v-if="!lastMessage" description="暂无消息" :image-size="60" />
        <div v-else>
          <el-tag size="small" :type="lastMessage.type === 'call' ? 'warning' : 'primary'">
            {{ lastMessage.type === 'call' ? '电话' : '短信' }}
          </el-tag>
          <b style="margin-left: 8px">{{ lastMessage.sender }}</b>
          <span class="muted" style="font-size:12px; margin-left:8px">{{ lastMessage.receive_time }}</span>
          <p style="white-space: pre-wrap; margin-bottom: 0">{{ lastMessage.content }}</p>
        </div>
      </el-card>
    </div>
  </AppLayout>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { Refresh } from '@element-plus/icons-vue'
import AppLayout from '../components/AppLayout.vue'
import PageHeader from '../components/PageHeader.vue'
import api from '../api'
import { onWsEvent } from '../ws'

const summary = ref({})
const lastMessage = ref(null)
const dailyChart = ref(null)
const hourlyChart = ref(null)
const deviceList = ref([])
const deviceId = ref(null)
let dailyInst = null
let hourlyInst = null
let timer = null

const onlineCount = computed(() => deviceList.value.filter((d) => d.online).length)
const router = useRouter()

function fmtDur(sec) {
  sec = sec || 0
  const h = Math.floor(sec / 3600), m = Math.round((sec % 3600) / 60)
  return h > 0 ? `${h}小时${m}分` : `${m}分钟`
}
function goDevice(d) {
  if (deviceId.value === d.id) deviceId.value = null
  else deviceId.value = d.id
  reloadAll()
}

async function loadSummary() {
  const qs = deviceId.value ? `?device_id=${deviceId.value}` : ''
  summary.value = await api.get(`/api/stats/summary${qs}`)
  if (summary.value.last_message) lastMessage.value = summary.value.last_message
}

async function loadDaily() {
  const qs = deviceId.value ? `&device_id=${deviceId.value}` : ''
  const r = await api.get(`/api/stats/daily?days=7${qs}`)
  dailyInst.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['短信', '电话', '工作时长(分钟)'] },
    grid: { left: 40, right: 50, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: r.items.map((i) => i.date) },
    yAxis: [{ type: 'value', name: '条数' }, { type: 'value', name: '分钟', splitLine: { show: false } }],
    series: [
      { name: '短信', type: 'bar', data: r.items.map((i) => i.sms), itemStyle: { color: '#4f6ef7', borderRadius: [4, 4, 0, 0] } },
      { name: '电话', type: 'bar', data: r.items.map((i) => i.call), itemStyle: { color: '#f5a623', borderRadius: [4, 4, 0, 0] } },
      { name: '工作时长(分钟)', type: 'line', yAxisIndex: 1, smooth: true, data: r.items.map((i) => i.working_minutes), itemStyle: { color: '#34c77b' } },
    ],
  })
}

async function loadHourly() {
  const qs = deviceId.value ? `&device_id=${deviceId.value}` : ''
  const r = await api.get(`/api/stats/hourly?days=7${qs}`)
  const hours = Array.from({ length: 24 }, (_, i) => `${i}时`)
  hourlyInst.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['短信', '电话'] },
    grid: { left: 40, right: 20, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: hours },
    yAxis: { type: 'value' },
    series: [
      { name: '短信', type: 'bar', stack: 'x', data: r.hourly.sms, itemStyle: { color: '#4f6ef7' } },
      { name: '电话', type: 'bar', stack: 'x', data: r.hourly.call, itemStyle: { color: '#f5a623' } },
    ],
  })
}

function reloadAll() {
  loadSummary().then(loadDaily).then(loadHourly).catch(() => {})
}

async function loadDevices() {
  deviceList.value = (await api.get('/api/devices')).items
}

onMounted(async () => {
  dailyInst = echarts.init(dailyChart.value)
  hourlyInst = echarts.init(hourlyChart.value)
  await loadDevices()
  await reloadAll()
  timer = setInterval(() => { loadSummary().catch(() => {}); loadDevices().catch(() => {}) }, 30000)
})

onUnmounted(() => {
  clearInterval(timer)
  dailyInst?.dispose()
  hourlyInst?.dispose()
})

onWsEvent((p) => {
  if (p.event === 'message') {
    lastMessage.value = { type: p.type, sender: p.sender, content: p.content, receive_time: p.receive_time }
    reloadAll()
    loadDevices().catch(() => {})
  } else if (['heartbeat', 'device_online', 'device_offline'].includes(p.event)) {
    reloadAll()
    loadDevices().catch(() => {})
  }
})
</script>

<style scoped>
.muted { color: #8a91a8; font-size: 12px; }
.dim { color: #b0b6c9; font-size: 17px; font-weight: 500; }
.device-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 12px; }
.device-chip {
  border: 1px solid #eef0f6; border-radius: 12px; padding: 12px 14px; cursor: pointer;
  transition: all .15s ease; background: #fbfcff;
}
.device-chip:hover { border-color: #4f6ef7; box-shadow: 0 4px 12px rgba(79,110,247,.12); }
.device-chip.selected { border-color: #4f6ef7; background: #f0f3ff; }
.dc-head { display: flex; justify-content: space-between; align-items: center; }
.dc-name { font-weight: 700; color: #2c3150; }
.dc-state { font-size: 12px; }
.dc-state.on { color: #34c77b; }
.dc-state.off { color: #f56c6c; }
.dc-meta { display: flex; gap: 12px; margin-top: 8px; color: #6a7090; font-size: 13px; flex-wrap: wrap; }
.grow-card { flex: 1 1 100%; }
.half-card { flex: 1 1 460px; }
</style>
