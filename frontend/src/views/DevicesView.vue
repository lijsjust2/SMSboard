<template>
  <AppLayout>
    <PageHeader title="设备管理" subtitle="查看设备信息、SIM 卡与统计数据，管理备注">
      <el-button :icon="Refresh" @click="load(true)">刷新</el-button>
      <el-button v-if="selected" type="danger" plain :icon="Delete" @click="removeDevice(selected)">删除设备</el-button>
    </PageHeader>

    <div class="dm-layout">
      <!-- 左侧设备列表 -->
      <el-card class="dm-list" body-style="padding: 10px">
        <el-input v-model="keyword" placeholder="搜索设备" clearable :prefix-icon="Search" size="small" />
        <div class="list-scroll">
          <div v-for="d in filtered" :key="d.id" class="dev-item"
               :class="{ active: selected?.id === d.id }" @click="select(d)">
            <div class="di-row">
              <span class="di-name">{{ d.name }}</span>
              <span class="di-state" :class="d.online ? 'on' : 'off'">{{ d.online ? '● 在线' : '● 离线' }}</span>
            </div>
            <div class="di-sub">{{ d.device_key }}</div>
            <div class="di-meta">
              <span>{{ d.plugged ? '🔌' : '🔋' }} {{ d.battery_pct != null ? d.battery_pct + '%' : '--' }}</span>
              <span>SIM × {{ d.sim_count }}</span>
              <span>💬 {{ d.sms_total }}</span>
            </div>
          </div>
          <el-empty v-if="!filtered.length" description="暂无设备" :image-size="60" />
        </div>
      </el-card>

      <!-- 右侧详情 -->
      <div class="dm-detail" v-if="selected">
        <el-card class="mb16">
          <div class="detail-head">
            <span class="detail-avatar">{{ (selected.name || 'D')[0].toUpperCase() }}</span>
            <div style="flex:1">
              <div style="display:flex; align-items:center; gap:10px">
                <b style="font-size:18px">{{ selected.name }}</b>
                <el-tag :type="selected.online ? 'success' : 'danger'" size="small" effect="light">
                  {{ selected.online ? '在线' : '离线' }}
                </el-tag>
              </div>
            </div>
            <el-button @click="openEdit(selected)">编辑</el-button>
          </div>
        </el-card>

        <el-card class="mb16">
          <el-tabs v-model="tab">
            <el-tab-pane label="概述" name="overview">
              <div class="info-grid">
                <div class="info-block">
                  <div class="ib-title">运行状态</div>
                  <div class="kv"><span>在线状态</span>
                    <b :style="{color: selected.online ? '#34c77b' : '#f56c6c'}">{{ selected.online ? '在线' : '离线' }}</b>
                  </div>
                  <div class="kv"><span>最后心跳</span><b>{{ selected.last_heartbeat || '从未' }}</b></div>
                  <div class="kv"><span>今日工作</span><b>{{ fmtDur(selected.working_seconds_today) }}</b></div>
                  <div class="kv"><span>累计工作</span><b>{{ fmtDur(selected.working_seconds_total) }}</b></div>
                  <div class="kv"><span>离线阈值</span><b>{{ threshold }} 分钟</b></div>
                </div>
                <div class="info-block">
                  <div class="ib-title">电量</div>
                  <div class="battery-big">
                    {{ selected.battery_pct != null ? selected.battery_pct + '%' : '--' }}
                  </div>
                  <div class="muted">{{ selected.plugged ? '🔌 正在充电' : '🔋 电池供电' }}</div>
                  <el-button size="small" style="margin-top:12px"
                    @click="$router.push(`/device?device_id=${selected.id}`)">查看电量曲线</el-button>
                </div>
                <div class="info-block">
                  <div class="ib-title">消息统计</div>
                  <div class="kv"><span>累计短信</span><b>{{ selected.sms_total }}</b></div>
                  <div class="kv"><span>累计电话</span><b>{{ selected.call_total }}</b></div>
                  <div class="kv"><span>SIM 卡数</span><b>{{ sims.length }}</b></div>
                  <el-button size="small" style="margin-top:12px"
                    @click="$router.push(`/messages?device_id=${selected.id}`)">查看短信记录</el-button>
                </div>
              </div>
            </el-tab-pane>

            <el-tab-pane :label="`SIM 卡 (${sims.length})`" name="sims">
              <el-table :data="sims" size="small" stripe>
                <el-table-column prop="slot_label" label="卡槽" width="80" />
                <el-table-column label="号码" width="140">
                  <template #default="{ row }">{{ row.number || '-' }}</template>
                </el-table-column>
                <el-table-column label="别名" width="140">
                  <template #default="{ row }">{{ row.alias || '-' }}</template>
                </el-table-column>
                <el-table-column prop="slot_key" label="原始标识" show-overflow-tooltip />
                <el-table-column prop="msg_count" label="消息数" width="90" />
                <el-table-column label="操作" width="140" fixed="right">
                  <template #default="{ row }">
                    <el-button size="small" @click="openSimEdit(row)">编辑</el-button>
                    <el-button size="small" type="danger" plain @click="removeSim(row)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
              <div class="muted" style="margin-top:8px; font-size:12px">
                SIM 卡由消息中的卡槽信息自动发现；删除不会删除消息记录
              </div>
            </el-tab-pane>
          </el-tabs>
        </el-card>
      </div>
      <el-card v-else class="dm-detail">
        <el-empty description="从左侧选择一台设备查看详情" />
      </el-card>
    </div>

    <!-- 设备编辑 -->
    <el-dialog v-model="editVisible" title="编辑设备" width="420px">
      <el-form label-width="70px">
        <el-form-item label="别名"><el-input v-model="editForm.name" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="editForm.note" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- SIM 编辑 -->
    <el-dialog v-model="simEditVisible" title="编辑 SIM 卡" width="420px" append-to-body>
      <el-form label-width="70px">
        <el-form-item label="号码"><el-input v-model="simEditForm.number" placeholder="手机号，可手动填写" /></el-form-item>
        <el-form-item label="别名"><el-input v-model="simEditForm.alias" placeholder="如：主卡-联通" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="simEditForm.note" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="simEditVisible = false">取消</el-button>
        <el-button type="primary" @click="saveSimEdit">保存</el-button>
      </template>
    </el-dialog>
  </AppLayout>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Delete, Search } from '@element-plus/icons-vue'
import AppLayout from '../components/AppLayout.vue'
import PageHeader from '../components/PageHeader.vue'
import api from '../api'

const route = useRoute()
const devices = ref([])
const selected = ref(null)
const sims = ref([])
const keyword = ref('')
const tab = ref('overview')
const editVisible = ref(false)
const editForm = ref({ id: null, name: '', note: '' })
const simEditVisible = ref(false)
const simEditForm = ref({ id: null, alias: '', note: '' })
const threshold = ref(15)

const filtered = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  if (!k) return devices.value
  return devices.value.filter((d) =>
    (d.name + d.device_key).toLowerCase().includes(k))
})

function fmtDur(sec) {
  sec = sec || 0
  const h = Math.floor(sec / 3600), m = Math.round((sec % 3600) / 60)
  return h > 0 ? `${h}小时${m}分` : `${m}分钟`
}

async function load(keepSelection = false) {
  devices.value = (await api.get('/api/devices')).items
  threshold.value = (await api.get('/api/stats/daily?days=1')).threshold_minutes
  if (!keepSelection && !selected.value && devices.value.length) {
    const fromQuery = Number(route.query.device_id)
    const target = devices.value.find((d) => d.id === fromQuery) || devices.value[0]
    select(target)
  } else if (selected.value) {
    selected.value = devices.value.find((d) => d.id === selected.value.id) || selected.value
    loadSims()
  }
}

async function select(d) {
  selected.value = d
  tab.value = 'overview'
  loadSims()
}

async function loadSims() {
  if (!selected.value) return
  sims.value = (await api.get(`/api/devices/${selected.value.id}/sims`)).items
}

function openEdit(row) {
  editForm.value = { id: row.id, name: row.name, note: row.note }
  editVisible.value = true
}
async function saveEdit() {
  await api.put(`/api/devices/${editForm.value.id}`, editForm.value)
  editVisible.value = false
  ElMessage.success('已保存')
  load(true)
}
function openSimEdit(row) {
  simEditForm.value = { id: row.id, alias: row.alias, note: row.note, number: row.number }
  simEditVisible.value = true
}
async function saveSimEdit() {
  await api.put(`/api/sims/${simEditForm.value.id}`, simEditForm.value)
  simEditVisible.value = false
  ElMessage.success('已保存')
  loadSims()
  load(true)
}
async function removeSim(row) {
  await ElMessageBox.confirm(`删除 SIM 卡「${row.alias || row.slot_key}」？`, '确认', { type: 'warning' })
  await api.delete(`/api/sims/${row.id}`)
  ElMessage.success('已删除')
  loadSims()
  load(true)
}
async function removeDevice(row) {
  await ElMessageBox.confirm(
    `删除设备「${row.name}」及其全部 SIM 卡和消息记录？此操作不可恢复！`,
    '危险操作', { type: 'error', confirmButtonText: '确认删除' }
  )
  await api.delete(`/api/devices/${row.id}`)
  selected.value = null
  sims.value = []
  ElMessage.success('已删除')
  load()
}

onMounted(() => load())
</script>

<style scoped>
.muted { color: #8a91a8; }
.dm-layout { display: flex; gap: 14px; align-items: flex-start; }
.dm-list { width: 280px; flex-shrink: 0; }
.dm-detail { flex: 1; min-width: 0; }
.list-scroll { margin-top: 10px; max-height: 62vh; overflow-y: auto; }
.dev-item {
  border: 1px solid #eef0f6; border-radius: 10px; padding: 10px 12px; margin-bottom: 8px;
  cursor: pointer; transition: all .12s ease; background: #fbfcff;
}
.dev-item:hover { border-color: #c3cef9; }
.dev-item.active { border-color: #4f6ef7; background: #f0f3ff; }
.di-row { display: flex; justify-content: space-between; align-items: center; }
.di-name { font-weight: 700; color: #2c3150; font-size: 14px; }
.di-state { font-size: 12px; }
.di-state.on { color: #34c77b; }
.di-state.off { color: #f56c6c; }
.di-sub { color: #9aa0b5; font-size: 12px; margin-top: 2px; }
.di-meta { display: flex; gap: 10px; margin-top: 6px; color: #6a7090; font-size: 12px; }
.detail-head { display: flex; align-items: center; gap: 14px; }
.detail-avatar {
  width: 46px; height: 46px; border-radius: 12px; flex-shrink: 0;
  background: linear-gradient(135deg, #4f6ef7, #7c5cf5); color: #fff;
  display: inline-flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: 20px;
}
.info-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }
.info-block { border: 1px solid #eef0f6; border-radius: 12px; padding: 14px 16px; background: #fbfcff; }
.ib-title { font-weight: 700; color: #2c3150; margin-bottom: 10px; }
.kv { display: flex; justify-content: space-between; padding: 4px 0; font-size: 13px; }
.kv span { color: #8a91a8; }
.kv b { color: #2c3150; }
.battery-big { font-size: 34px; font-weight: 800; color: #2c3150; }

@media (max-width: 768px) {
  .dm-layout { flex-direction: column; }
  .dm-list { width: 100%; }
}
</style>
