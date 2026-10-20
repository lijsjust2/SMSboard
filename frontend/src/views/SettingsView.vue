<template>
  <AppLayout>
    <PageHeader title="系统设置" subtitle="复制推送地址，到手机 SmsForwarder 里配置即可" />

    <!-- 第 1 步：推送地址 -->
    <el-card class="mb16">
      <template #header>
        <b>第 1 步 · 复制推送地址</b>
        <el-tag size="small" type="success" style="margin-left:10px">Bark 式 · Key 即鉴权</el-tag>
      </template>
      <el-input :model-value="pushUrl" readonly size="large" class="url-input">
        <template #append>
          <el-button type="primary" :icon="CopyDocument" @click="copy(pushUrl)">复制</el-button>
        </template>
      </el-input>
      <div class="hint" style="margin-top:8px">
        这个地址已包含鉴权 Key，无需再配置签名。多台手机共用同一个地址，用不同的「设备标记」区分。
      </div>
    </el-card>

    <!-- 第 2 步：三个通道参数 -->
    <el-card class="mb16">
      <template #header><b>第 2 步 · 在 SmsForwarder 新建 3 个 Webhook 通道</b></template>
      <div v-for="(ch, i) in channels" :key="ch.name" class="ch-block">
        <div class="ch-head">
          <span class="ch-step">{{ i + 1 }}</span>
          <b>{{ ch.name }}</b>
          <span class="hint" style="margin-left:8px">{{ ch.desc }}</span>
        </div>
        <div class="field-row">
          <span class="field-label">服务器地址</span>
          <el-input :model-value="pushUrl" readonly size="small">
            <template #append><el-button :icon="CopyDocument" @click="copy(pushUrl)">复制</el-button></template>
          </el-input>
        </div>
        <div class="field-row">
          <span class="field-label">请求参数</span>
          <div class="field-value">
            <el-input :model-value="ch.body" readonly type="textarea" :rows="2" size="small" class="mono" />
            <el-button size="small" :icon="CopyDocument" @click="copy(ch.body)">复制</el-button>
          </div>
        </div>
        <div class="field-row">
          <span class="field-label"></span>
          <div class="hint">↑ 复制后粘贴到 App 该通道的「消息模板」输入框（消息模板为空时设备/SIM 等信息会缺失）</div>
        </div>
      </div>
      <div class="hint">
        依次在 App「发送通道 → 新建通道 → Webhook」中创建，请求类型选 POST 即可。完成后为短信/通话各建一条转发规则选对应通道。
      </div>
    </el-card>

    <!-- 第 3 步：心跳定时任务 -->
    <el-card class="mb16">
      <template #header><b>第 3 步 · 心跳定时任务（用于在线状态与电量）</b></template>
      <div class="hint" style="margin-bottom:10px">
        App「自动任务 → 定时任务」新建：Cron 填
        <code class="code-inline">0 0/{{ form.heartbeat_interval_min || 5 }} * * * ?</code>
        （注意：SmsForwarder 用 7 位 Quartz 格式，<b>第一位是秒</b>，直接抄上面的即可），发送通道选「看板-心跳」。填完点 App 里的「测试」可预览最近执行时间。
      </div>
      <div class="ch-block">
        <div class="ch-head"><b>看板-心跳</b><span class="hint" style="margin-left:8px">请求参数</span></div>
        <el-input :model-value="channels[2].body" readonly type="textarea" :rows="2" size="small" class="mono">
          <template #append><el-button :icon="CopyDocument" @click="copy(channels[2].body)">复制</el-button></template>
        </el-input>
      </div>
    </el-card>

    <!-- 高级选项 -->
    <el-card>
      <el-collapse>
        <el-collapse-item title="高级设置（离线告警 / 心跳判定）" name="adv">
          <el-form label-width="150px" v-loading="loading">
            <el-divider content-position="left">离线告警（PushPlus）</el-divider>
            <el-form-item label="PushPlus Token">
              <el-input v-model="form.pushplus_token" placeholder="设备离线时用于向你推送提醒" show-password />
            </el-form-item>
            <el-form-item label="离线时推送"><el-switch v-model="form.notify_on_offline" /></el-form-item>
            <el-form-item label="上线时推送"><el-switch v-model="form.notify_on_online" /></el-form-item>

            <el-divider content-position="left">心跳与离线判定</el-divider>
            <el-form-item label="心跳间隔(分钟)">
              <el-input-number v-model="form.heartbeat_interval_min" :min="1" :max="60" />
              <span class="hint" style="margin-left:8px">
                仅用于生成第 3 步的推荐 Cron；实际心跳由 <b>App 的定时任务</b> 定时推送，请按第 3 步在 App 中配置，两处间隔保持一致
              </span>
            </el-form-item>
            <el-form-item label="离线阈值(分钟)">
              <el-input-number v-model="form.offline_threshold_min" :min="2" :max="1440" :step="5" />
              <span class="hint" style="margin-left:8px">超过该时长未收到 App 推送的心跳即判定设备离线（建议 ≥ 心跳间隔 × 3）</span>
            </el-form-item>

            <el-form-item>
              <el-button type="primary" :loading="saving" @click="save">保存高级设置</el-button>
            </el-form-item>
          </el-form>
        </el-collapse-item>
        <el-collapse-item title="推送 Key 管理" name="key">
          <el-form label-width="150px">
            <el-form-item label="当前 Key">
              <el-input :model-value="form.push_key" readonly>
                <template #append>
                  <el-button @click="regenerateKey" :loading="regenerating">重新生成</el-button>
                </template>
              </el-input>
              <div class="hint">重新生成后，旧的推送地址立即失效，需更新手机端配置</div>
            </el-form-item>
          </el-form>
        </el-collapse-item>
      </el-collapse>
    </el-card>
  </AppLayout>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { CopyDocument } from '@element-plus/icons-vue'
import AppLayout from '../components/AppLayout.vue'
import PageHeader from '../components/PageHeader.vue'
import api, { copyText } from '../api'

const form = ref({})
const loading = ref(false)
const saving = ref(false)
const regenerating = ref(false)
const threshold = computed(() => form.value.offline_threshold_min || 15)

const pushUrl = computed(() =>
  `${window.location.origin}/api/push/${form.value.push_key || '你的Key'}`)

const channels = computed(() => {
  const smsBody = '{"type":"sms","from":"[from]","content":"[content]","sim":"[card_slot]","device":"[device_mark]","time":"[receive_time:yyyy-MM-dd HH:mm:ss]","timestamp":[timestamp]}'
  return [
    { name: '看板-短信', desc: '转发短信内容', body: smsBody },
    { name: '看板-通话', desc: '转发来电/去电记录', body: smsBody.replace('"sms"', '"call"') },
    {
      name: '看板-心跳', desc: '定时上报在线状态与电量',
      body: '{"type":"heartbeat","battery":"{{BATTERY_PCT}}","plugged":"{{BATTERY_PLUGGED}}","info":"{{BATTERY_INFO}}","device":"[device_mark]","time":"[CURRENT_TIME]","timestamp":[timestamp]}',
    },
  ]
})

async function copy(text) {
  const ok = await copyText(text)
  if (ok) ElMessage.success('已复制')
  else ElMessage.warning('复制失败，请手动选择复制')
}

async function regenerateKey() {
  regenerating.value = true
  try {
    const r = await api.post('/api/settings/push_key/regenerate')
    form.value.push_key = r.push_key
    ElMessage.success('已重新生成')
  } catch (e) { ElMessage.error(e.message) }
  finally { regenerating.value = false }
}

onMounted(async () => {
  loading.value = true
  try { form.value = await api.get('/api/settings') } catch (e) { ElMessage.error(e.message) }
  finally { loading.value = false }
})

async function save() {
  saving.value = true
  try {
    await api.put('/api/settings', form.value)
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e.message)
  } finally { saving.value = false }
}
</script>

<style scoped>
.hint { color: #8a91a8; font-size: 12px; }
.url-input :deep(.el-input__inner) { font-family: monospace; color: #4f6ef7; font-weight: 600; }
.ch-block {
  border: 1px solid #eef0f6; border-radius: 12px; padding: 14px 16px; margin-bottom: 14px;
  background: #fbfcff;
}
.ch-head { display: flex; align-items: center; margin-bottom: 10px; }
.ch-step {
  width: 22px; height: 22px; border-radius: 50%; background: #4f6ef7; color: #fff;
  display: inline-flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700;
  margin-right: 8px; flex-shrink: 0;
}
.field-row { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 8px; }
.field-label { width: 80px; flex-shrink: 0; color: #6a7090; font-size: 13px; padding-top: 6px; text-align: right; }
.field-value { display: flex; align-items: flex-start; gap: 8px; flex: 1; min-width: 0; }
.mono :deep(.el-textarea__inner) { font-family: monospace; font-size: 12px; }
.code-inline {
  background: #f0f3ff; border-radius: 4px; padding: 2px 6px; color: #4f6ef7; font-family: monospace;
}
</style>
