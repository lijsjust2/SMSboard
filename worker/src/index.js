/**
 * SmsBoard Cloudflare Worker 后端（R2 存储）
 *
 * 与 Python(FastAPI) 后端同 API 形态，前端 SPA 完全复用：
 * - 数据存 R2：config/settings.json + data/messages/日.jsonl + data/heartbeats/日.jsonl
 * - 设备/SIM 由消息与心跳推导，支持重命名备注（存 settings 的 meta 覆盖）
 * - 在线状态/离线事件由心跳序列在读取时实时推导（Workers 无后台任务）
 * - 不支持 WebSocket（前端自动降级为轮询），不做 PushPlus 离线推送
 *
 * 时区：存储与展示按 UTC+8（中国）固定偏移。
 */

const TZ_OFFSET_MS = 8 * 3600 * 1000
const DEFAULT_SETTINGS = {
  admin_username: '',
  admin_password_hash: '',
  jwt_secret: '',
  push_key: '',
  webhook_secret: '',
  heartbeat_interval_min: 5,
  offline_threshold_min: 15,
  device_meta: {},   // device_key -> {name, note}
  sim_meta: {},      // device_key|slot_key -> {alias, note, number}
  deleted_devices: [],
  deleted_sims: [],  // device_key|slot_key
}

export default {
  async fetch(request, env) {
    try {
      return await handle(request, env)
    } catch (e) {
      return json({ code: 500, msg: String(e && e.message || e) }, 500)
    }
  },
}

// ---------- 基础工具 ----------

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  })
}

function pad2(n) { return String(n).padStart(2, '0') }

function fmtTs(epochMs) {
  const d = new Date(epochMs + TZ_OFFSET_MS)
  return d.toISOString().slice(0, 19).replace('T', ' ')
}

function dayStr(epochMs) { return fmtTs(epochMs).slice(0, 10) }

function b64url(buf) {
  const bytes = new Uint8Array(buf)
  let s = ''
  for (const b of bytes) s += String.fromCharCode(b)
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function b64urlDecode(s) {
  s = s.replace(/-/g, '+').replace(/_/g, '/')
  while (s.length % 4) s += '='
  const bin = atob(s)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return bytes
}

async function sha1Hex(text) {
  const h = await crypto.subtle.digest('SHA-1', new TextEncoder().encode(text))
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

async function hmacHex(secret, text) {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'])
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(text))
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

async function hashPassword(password) {
  const salt = crypto.getRandomValues(new Uint8Array(16))
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(password), 'PBKDF2', false, ['deriveBits'])
  const bits = await crypto.subtle.deriveBits(
    { name: 'PBKDF2', salt, iterations: 100000, hash: 'SHA-256' }, key, 256)
  const hex = [...new Uint8Array(bits)].map((b) => b.toString(16).padStart(2, '0')).join('')
  return `pbkdf2$100000$${[...salt].map((b) => b.toString(16).padStart(2, '0')).join('')}$${hex}`
}

async function verifyPassword(password, stored) {
  try {
    const [, iters, saltHex, dkHex] = stored.split('$')
    const salt = new Uint8Array(saltHex.match(/.{2}/g).map((h) => parseInt(h, 16)))
    const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(password), 'PBKDF2', false, ['deriveBits'])
    const bits = await crypto.subtle.deriveBits(
      { name: 'PBKDF2', salt, iterations: parseInt(iters), hash: 'SHA-256' }, key, 256)
    const hex = [...new Uint8Array(bits)].map((b) => b.toString(16).padStart(2, '0')).join('')
    return hex === dkHex
  } catch { return false }
}

function fnv32(str) {
  let h = 2166136261
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

function randHex(len) {
  const bytes = crypto.getRandomValues(new Uint8Array(Math.ceil(len / 2)))
  return [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('').slice(0, len)
}

function parseTime(raw) {
  if (raw == null || raw === '') return Date.now()
  if (typeof raw === 'number' || /^\d+$/.test(String(raw))) {
    const v = Number(raw)
    return v > 1e12 ? v : v * 1000  // SmsForwarder 的 [timestamp] 为毫秒
  }
  const m = String(raw).trim().match(/^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$/)
  if (m) {
    return Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]) - TZ_OFFSET_MS
  }
  return Date.now()
}

function parseBody(text) {
  try { return JSON.parse(text) } catch { /* 表单回退 */ }
  const out = {}
  for (const [k, v] of new URLSearchParams(text)) out[k] = v
  return out
}

// ---------- R2 存取 ----------

async function getSettings(env) {
  const obj = await env.R2.get('config/settings.json')
  if (!obj) return { ...DEFAULT_SETTINGS }
  const s = await obj.json()
  return { ...DEFAULT_SETTINGS, ...s }
}

async function putSettings(env, s) {
  await env.R2.put('config/settings.json', JSON.stringify(s))
}

async function loadLines(env, key) {
  const obj = await env.R2.get(key)
  if (!obj) return []
  const text = await obj.text()
  const lines = text.split('\n').filter(Boolean)
  try { return lines.map((l) => JSON.parse(l)) } catch { return [] }
}

async function appendLine(env, key, obj) {
  const lines = await loadLines(env, key)
  lines.push(obj)
  await env.R2.put(key, lines.map((l) => JSON.stringify(l)).join('\n'))
}

async function listDayKeys(env, prefix) {
  const out = []
  let cursor
  do {
    const page = await env.R2.list({ prefix, cursor })
    out.push(...page.objects.map((o) => o.key))
    cursor = page.truncated ? page.cursor : undefined
  } while (cursor)
  return out.sort()
}

// ---------- 认证 ----------

async function createToken(settings, sub) {
  const payload = b64url(new TextEncoder().encode(
    JSON.stringify({ sub, exp: Date.now() + 7 * 24 * 3600 * 1000 })))
  const sig = await hmacHex(settings.jwt_secret, payload)
  return `${payload}.${sig}`
}

async function requireAuth(request, env, settings) {
  const auth = request.headers.get('Authorization') || ''
  const token = auth.startsWith('Bearer ') ? auth.slice(7) : new URL(request.url).searchParams.get('token') || ''
  if (!token || !settings.jwt_secret) return null
  const [payload, sig] = token.split('.')
  if (!payload || !sig) return null
  const expect = await hmacHex(settings.jwt_secret, payload)
  if (expect !== sig) return null
  try {
    const body = JSON.parse(new TextDecoder().decode(b64urlDecode(payload)))
    if (!body.exp || body.exp < Date.now()) return null
    return body
  } catch { return null }
}

// ---------- 业务推导 ----------

function extractPhoneNumber(text) {
  if (!text) return ''
  let m = text.match(/\d{11}/)
  if (m) return m[0]
  m = text.match(/\d{4,}/)
  return m ? m[0] : ''
}

function parseSimKey(simStr) {
  const s = (simStr || '').trim()
  if (!s) return ['', '']
  if (s.includes('_')) {
    const [slot, ...rest] = s.split('_')
    return [slot || 'SIM', rest.join('_').trim()]
  }
  return [s, '']
}

async function loadAllMessages(env, maxDays = 120) {
  const keys = await listDayKeys(env, 'data/messages/')
  const recent = keys.slice(-maxDays)
  const all = []
  for (const k of recent) all.push(...await loadLines(env, k))
  return all
}

async function loadAllHeartbeats(env, maxDays = 120) {
  const keys = await listDayKeys(env, 'data/heartbeats/')
  const recent = keys.slice(-maxDays)
  const all = []
  for (const k of recent) all.push(...await loadLines(env, k))
  return all.sort((a, b) => a.ts - b.ts)
}

function deviceListOf(settings, messages, heartbeats) {
  const keys = new Set()
  for (const m of messages) if (m.device) keys.add(m.device)
  for (const h of heartbeats) if (h.device) keys.add(h.device)
  const deleted = new Set(settings.deleted_devices || [])
  return [...keys].filter((k) => !deleted.has(k)).sort()
}

function thresholdMin(settings) {
  const t = parseInt(settings.offline_threshold_min)
  return (t > 0 ? t : 15)
}

function workingSeconds(hbs, settings, dayStartMs, dayEndMs) {
  const threshold = thresholdMin(settings) * 60000
  const interval = parseInt(settings.heartbeat_interval_min || 5) * 60000
  const now = Date.now()
  let list = hbs
  if (dayStartMs != null) list = hbs.filter((h) => h.ts >= dayStartMs && h.ts < dayEndMs)
  if (!list.length) return 0
  let total = 0
  let segStart = list[0].ts
  let prev = list[0].ts
  for (const h of list.slice(1)) {
    if (h.ts - prev > threshold) {
      total += (prev - segStart) + interval
      segStart = h.ts
    }
    prev = h.ts
  }
  const online = Date.now() - list[list.length - 1].ts <= threshold
  if (online && (dayStartMs == null || (now >= dayStartMs && now < dayEndMs))) {
    total += (now - prev <= threshold ? now - segStart : (prev - segStart) + interval)
  } else {
    total += (prev - segStart) + interval
  }
  return Math.round(total / 1000)
}

function deriveSims(settings, deviceKey, messages) {
  const map = new Map()
  for (const m of messages) {
    if (m.device !== deviceKey || !m.sim_slot) continue
    if (!map.has(m.sim_slot)) map.set(m.sim_slot, 0)
    map.set(m.sim_slot, map.get(m.sim_slot) + 1)
  }
  const deleted = new Set(settings.deleted_sims || [])
  const out = []
  for (const [slotKey, msgCount] of map) {
    const sk = `${deviceKey}|${slotKey}`
    if (deleted.has(sk)) continue
    const meta = (settings.sim_meta || {})[sk] || {}
    const [slotLabel, tail] = parseSimKey(slotKey)
    out.push({
      id: fnv32(sk),
      slot_key: slotKey,
      slot_label: slotLabel,
      number: meta.number || extractPhoneNumber(tail),
      alias: meta.alias || '',
      note: meta.note || '',
      msg_count: msgCount,
    })
  }
  return out.sort((a, b) => a.slot_key.localeCompare(b.slot_key))
}

function deviceStatus(settings, hbs, deviceKey) {
  const list = hbs.filter((h) => h.device === deviceKey)
  const threshold = thresholdMin(settings) * 60000
  const now = Date.now()
  const last = list.length ? list[list.length - 1] : null
  const online = !!last && (now - last.ts <= threshold)
  return {
    online,
    last_heartbeat: last ? fmtTs(last.ts) : null,
    battery_pct: last ? last.battery_pct : null,
    plugged: last ? !!last.plugged : false,
    battery_info: last ? last.battery_info : '',
    threshold_minutes: thresholdMin(settings),
  }
}

function deriveEvents(settings, hbs, deviceKey) {
  const list = hbs.filter((h) => h.device === deviceKey).sort((a, b) => a.ts - b.ts)
  const threshold = thresholdMin(settings) * 60000
  const now = Date.now()
  const events = []
  let prev = null
  for (const h of list) {
    if (prev && h.ts - prev.ts > threshold) {
      events.push({ ts: fmtTs(prev.ts + threshold), state: 'offline', battery_pct: prev.battery_pct })
      events.push({ ts: fmtTs(h.ts), state: 'online', battery_pct: h.battery_pct })
    }
    prev = h
  }
  if (prev && now - prev.ts > threshold) {
    events.push({ ts: fmtTs(prev.ts + threshold), state: 'offline', battery_pct: prev.battery_pct })
  }
  return events.reverse().slice(0, 30)
}

// ---------- 路由 ----------

async function handle(request, env) {
  const url = new URL(request.url)
  const path = url.pathname
  const method = request.method
  const settings = await getSettings(env)

  // ----- 推送入口 -----
  if (method === 'POST' && path.startsWith('/api/push/')) {
    const key = path.slice('/api/push/'.length).trim()
    if (!settings.push_key || key !== settings.push_key) {
      return json({ code: 403, msg: 'invalid push key' }, 403)
    }
    return ingest(request, env, settings, {})
  }

  if (method === 'POST' && path === '/api/webhook') {
    const secret = settings.webhook_secret || ''
    if (secret) {
      const body0 = parseBody(await request.text())
      const ts = String(body0.timestamp || '')
      const sign = decodeURIComponent(String(body0.sign || ''))
      const sts = `${ts}\n${secret}`
      const sigBuf = await crypto.subtle.sign(
        'HMAC', await crypto.subtle.importKey('raw', new TextEncoder().encode(secret),
          { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']),
        new TextEncoder().encode(sts))
      // 与 Python 端一致：标准 base64（URL 解码后）
      const expect = btoa(String.fromCharCode(...new Uint8Array(sigBuf)))
      const tsVal = parseInt(ts) || 0
      const tsSec = tsVal > 1e12 ? tsVal / 1000 : tsVal
      if (expect !== sign || Math.abs(Date.now() / 1000 - tsSec) > 300) {
        return json({ code: 403, msg: 'invalid sign' }, 403)
      }
      return ingest(request, env, settings, body0)
    }
    return ingest(request, env, settings, {})
  }

  // ----- 初始化与登录 -----
  if (method === 'GET' && path === '/api/setup/status') {
    return json({ need_setup: !settings.admin_password_hash })
  }

  if (method === 'POST' && path === '/api/setup/admin') {
    if (settings.admin_password_hash) return json({ detail: '管理员已存在，禁止重复初始化' }, 403)
    const body = await request.json()
    const username = (body.username || '').trim()
    if (username.length < 2 || (body.password || '').length < 6) {
      return json({ detail: '账号至少2位，密码至少6位' }, 400)
    }
    settings.admin_username = username
    settings.admin_password_hash = await hashPassword(body.password)
    settings.jwt_secret = randHex(64)
    settings.push_key = randHex(16)
    await putSettings(env, settings)
    return json({ code: 200, msg: 'ok', token: await createToken(settings, username) })
  }

  if (method === 'POST' && path === '/api/auth/login') {
    const body = await request.json()
    if (!settings.admin_password_hash) return json({ detail: '尚未初始化，请先设置管理员账号' }, 403)
    if ((body.username || '').trim() !== settings.admin_username ||
        !(await verifyPassword(body.password || '', settings.admin_password_hash))) {
      return json({ detail: '账号或密码错误' }, 401)
    }
    return json({ code: 200, msg: 'ok', token: await createToken(settings, settings.admin_username) })
  }

  // ----- 以下接口均需登录 -----
  const user = await requireAuth(request, env, settings)
  const authedPaths = path === '/api/auth/me' || path.startsWith('/api/stats/') ||
    path.startsWith('/api/messages') || path === '/api/battery/history' ||
    path === '/api/device/status' || path === '/api/devices' ||
    path.startsWith('/api/devices/') || path.startsWith('/api/sims/') ||
    path === '/api/settings' || path.startsWith('/api/settings/')
  if (authedPaths) {
    if (!user) return json({ detail: '未登录或登录已过期' }, 401)
  }

  if (method === 'GET' && path === '/api/auth/me') {
    return json({ code: 200, username: user.sub })
  }

  if (method === 'POST' && path === '/api/settings/push_key/regenerate') {
    settings.push_key = randHex(16)
    await putSettings(env, settings)
    return json({ code: 200, msg: 'ok', push_key: settings.push_key })
  }

  if (method === 'GET' && path === '/api/settings') {
    return json({
      code: 200,
      webhook_secret: settings.webhook_secret || '',
      push_key: settings.push_key || '',
      pushplus_token: settings.pushplus_token || '',
      notify_on_offline: settings.notify_on_offline !== false,
      notify_on_online: settings.notify_on_online === true,
      heartbeat_interval_min: parseInt(settings.heartbeat_interval_min) || 5,
      offline_threshold_min: thresholdMin(settings),
      offline_threshold_minutes: thresholdMin(settings),
    })
  }

  if (method === 'PUT' && path === '/api/settings') {
    const body = await request.json()
    const interval = parseInt(body.heartbeat_interval_min) || 5
    const offline = parseInt(body.offline_threshold_min) || 15
    if (interval < 1 || interval > 60) return json({ detail: '心跳间隔需在 1~60 分钟之间' }, 400)
    if (offline < 2 || offline > 1440) return json({ detail: '离线阈值需在 2~1440 分钟之间' }, 400)
    if (body.webhook_secret !== undefined) settings.webhook_secret = String(body.webhook_secret || '').trim()
    settings.heartbeat_interval_min = interval
    settings.offline_threshold_min = offline
    await putSettings(env, settings)
    return json({ code: 200, msg: 'ok', offline_threshold_minutes: thresholdMin(settings) })
  }

  const messages = authedPaths ? await loadAllMessages(env) : []
  const heartbeats = authedPaths ? await loadAllHeartbeats(env) : []

  // ----- 消息记录 -----
  if (path === '/api/messages' || path.startsWith('/api/messages/')) {
    if (method === 'DELETE') {
      const id = path.slice('/api/messages/'.length)
      const keys = await listDayKeys(env, 'data/messages/')
      let removed = false
      for (const k of keys) {
        const lines = await loadLines(env, k)
        const kept = lines.filter((l) => l.id !== id)
        if (kept.length !== lines.length) {
          await env.R2.put(k, kept.map((l) => JSON.stringify(l)).join('\n'))
          removed = true
          break
        }
      }
      if (!removed) return json({ detail: '记录不存在' }, 404)
      return json({ code: 200, msg: 'ok' })
    }

    if (method === 'GET') {
      const q = url.searchParams
      const type = q.get('type') || 'sms'
      const page = Math.max(1, parseInt(q.get('page')) || 1)
      const size = Math.min(100, Math.max(1, parseInt(q.get('size')) || 20))
      const keyword = (q.get('keyword') || '').trim()
      const start = q.get('start') || ''
      const end = q.get('end') || ''
      const deviceId = q.get('device_id') ? parseInt(q.get('device_id')) : null
      const simId = q.get('sim_id') ? parseInt(q.get('sim_id')) : null

      const deviceKeyById = new Map()
      for (const k of deviceListOf(settings, messages, heartbeats)) {
        deviceKeyById.set(fnv32(k), k)
      }
      let items = messages.filter((m) => m.type === type)
      if (keyword) {
        items = items.filter((m) => (m.sender || '').includes(keyword) || (m.content || '').includes(keyword))
      }
      if (start) items = items.filter((m) => m.receive_time >= start)
      if (end) items = items.filter((m) => m.receive_time <= end)
      if (deviceId != null) {
        const dk = deviceKeyById.get(deviceId)
        items = items.filter((m) => dk && m.device === dk)
      }
      if (simId != null) {
        items = items.filter((m) => fnv32(`${m.device}|${m.sim_slot}`) === simId)
      }
      items.sort((a, b) => b.ts - a.ts)
      const total = items.length
      const pageItems = items.slice((page - 1) * size, page * size)
      return json({
        code: 200, total, page, size,
        items: pageItems.map((m) => ({
          id: m.id, sender: m.sender, content: m.content,
          sim_slot: m.sim_slot, device: m.device,
          device_id: m.device ? fnv32(m.device) : null,
          sim_id: m.sim_slot ? fnv32(`${m.device}|${m.sim_slot}`) : null,
          receive_time: m.receive_time,
        })),
      })
    }
  }

  // ----- 设备列表与详情 -----
  if (method === 'GET' && path === '/api/devices') {
    const q = url.searchParams
    const todayStart = new Date(fmtTs(Date.now()).slice(0, 10) + ' 00:00:00')
    const todayStartMs = parseTime(todayStart)
    const items = deviceListOf(settings, messages, heartbeats).map((key) => {
      const meta = (settings.device_meta || {})[key] || {}
      const dh = heartbeats.filter((h) => h.device === key)
      const st = deviceStatus(settings, heartbeats, key)
      const dm = messages.filter((m) => m.device === key)
      return {
        id: fnv32(key),
        device_key: key,
        name: meta.name || key,
        note: meta.note || '',
        online: st.online,
        battery_pct: st.battery_pct,
        plugged: st.plugged,
        last_heartbeat: st.last_heartbeat,
        working_seconds_today: workingSeconds(dh, settings, todayStartMs, todayStartMs + 86400000),
        working_seconds_total: workingSeconds(dh, settings, null, null),
        sms_total: dm.filter((m) => m.type === 'sms').length,
        call_total: dm.filter((m) => m.type === 'call').length,
        sim_count: new Set(dm.map((m) => m.sim_slot).filter(Boolean)).size,
      }
    })
    return json({ code: 200, items, threshold_minutes: thresholdMin(settings) })
  }

  if (path.startsWith('/api/devices/') && path.endsWith('/sims') && method === 'GET') {
    const deviceId = parseInt(path.split('/')[3])
    const key = deviceListOf(settings, messages, heartbeats).find((k) => fnv32(k) === deviceId)
    if (!key) return json({ detail: '设备不存在' }, 404)
    return json({
      code: 200,
      device: { id: deviceId, name: (settings.device_meta || {})[key]?.name || key },
      items: deriveSims(settings, key, messages),
    })
  }

  if (method === 'PUT' && path.startsWith('/api/devices/')) {
    const deviceId = parseInt(path.split('/')[3])
    const key = deviceListOf(settings, messages, heartbeats).find((k) => fnv32(k) === deviceId)
    if (!key) return json({ detail: '设备不存在' }, 404)
    const body = await request.json()
    settings.device_meta = settings.device_meta || {}
    settings.device_meta[key] = {
      name: (body.name || '').trim() || key,
      note: body.note || '',
    }
    await putSettings(env, settings)
    return json({ code: 200, msg: 'ok' })
  }

  if (method === 'DELETE' && path.startsWith('/api/devices/')) {
    const deviceId = parseInt(path.split('/')[3])
    const key = deviceListOf(settings, messages, heartbeats).find((k) => fnv32(k) === deviceId)
    if (!key) return json({ detail: '设备不存在' }, 404)
    settings.deleted_devices = [...(settings.deleted_devices || []), key]
    await putSettings(env, settings)
    // 移除该设备的消息与心跳
    for (const prefix of ['data/messages/', 'data/heartbeats/']) {
      for (const k of await listDayKeys(env, prefix)) {
        const lines = await loadLines(env, k)
        const kept = lines.filter((l) => l.device !== key)
        if (kept.length !== lines.length) {
          await env.R2.put(k, kept.map((l) => JSON.stringify(l)).join('\n'))
        }
      }
    }
    // 同步移除其 SIM meta
    for (const sk of Object.keys(settings.sim_meta || {})) {
      if (sk.startsWith(`${key}|`)) delete settings.sim_meta[sk]
    }
    await putSettings(env, settings)
    return json({ code: 200, msg: 'ok' })
  }

  if (method === 'PUT' && path.startsWith('/api/sims/')) {
    const simId = parseInt(path.split('/')[3])
    const body = await request.json()
    for (const key of deviceListOf(settings, messages, heartbeats)) {
      for (const slotKey of new Set(messages.filter((m) => m.device === key).map((m) => m.sim_slot).filter(Boolean))) {
        if (fnv32(`${key}|${slotKey}`) === simId) {
          settings.sim_meta = settings.sim_meta || {}
          const sk = `${key}|${slotKey}`
          settings.sim_meta[sk] = {
            ...(settings.sim_meta[sk] || {}),
            alias: (body.alias || '').trim(),
            note: body.note || '',
            number: (body.number || '').trim(),
          }
          await putSettings(env, settings)
          return json({ code: 200, msg: 'ok' })
        }
      }
    }
    return json({ detail: 'SIM 卡不存在' }, 404)
  }

  if (method === 'DELETE' && path.startsWith('/api/sims/')) {
    const simId = parseInt(path.split('/')[3])
    for (const key of deviceListOf(settings, messages, heartbeats)) {
      for (const slotKey of new Set(messages.filter((m) => m.device === key).map((m) => m.sim_slot).filter(Boolean))) {
        if (fnv32(`${key}|${slotKey}`) === simId) {
          settings.deleted_sims = [...(settings.deleted_sims || []), `${key}|${slotKey}`]
          await putSettings(env, settings)
          return json({ code: 200, msg: 'ok' })
        }
      }
    }
    return json({ detail: 'SIM 卡不存在' }, 404)
  }

  // ----- 统计 -----
  if (method === 'GET' && path === '/api/stats/summary') {
    const q = url.searchParams
    const deviceId = q.get('device_id') ? parseInt(q.get('device_id')) : null
    const keys = deviceListOf(settings, messages, heartbeats)
    const deviceKeyById = new Map(keys.map((k) => [fnv32(k), k]))
    const deviceKey = deviceId != null ? deviceKeyById.get(deviceId) : null
    if (deviceId != null && !deviceKey) return json({ detail: '设备不存在' }, 404)

    let msgs = messages
    let dh = heartbeats
    if (deviceKey) {
      msgs = messages.filter((m) => m.device === deviceKey)
      dh = heartbeats.filter((h) => h.device === deviceKey)
    }
    const dayStartMs = parseTime(fmtTs(Date.now()).slice(0, 10) + ' 00:00:00')

    let online, battery, plugged
    if (deviceKey) {
      const st = deviceStatus(settings, heartbeats, deviceKey)
      online = st.online; battery = st.battery_pct; plugged = st.plugged
    } else {
      online = keys.some((k) => deviceStatus(settings, heartbeats, k).online)
      const latest = heartbeats.length ? heartbeats[heartbeats.length - 1] : null
      battery = latest ? latest.battery_pct : null
      plugged = latest ? !!latest.plugged : false
    }
    const last = msgs.length ? msgs.reduce((a, b) => (a.ts > b.ts ? a : b)) : null

    return json({
      code: 200,
      device_id: deviceId,
      sms_total: msgs.filter((m) => m.type === 'sms').length,
      sms_today: msgs.filter((m) => m.type === 'sms' && m.ts >= dayStartMs).length,
      call_total: msgs.filter((m) => m.type === 'call').length,
      call_today: msgs.filter((m) => m.type === 'call' && m.ts >= dayStartMs).length,
      online_now: online,
      battery_pct: battery,
      plugged,
      working_seconds_today: workingSeconds(dh, settings, dayStartMs, dayStartMs + 86400000),
      working_seconds_total: workingSeconds(dh, settings, null, null),
      last_message: last ? {
        type: last.type, sender: last.sender, content: last.content,
        receive_time: last.receive_time,
      } : null,
    })
  }

  if (method === 'GET' && path === '/api/battery/history') {
    const q = url.searchParams
    const hours = Math.min(720, Math.max(1, parseInt(q.get('hours')) || 24))
    const deviceId = q.get('device_id') ? parseInt(q.get('device_id')) : null
    const deviceKeyById = new Map(deviceListOf(settings, messages, heartbeats).map((k) => [fnv32(k), k]))
    const since = Date.now() - hours * 3600 * 1000
    const items = heartbeats
      .filter((h) => h.ts >= since && h.battery_pct != null)
      .filter((h) => deviceId == null || deviceKeyById.get(deviceId) === h.device)
      .map((h) => ({
        ts: fmtTs(h.ts).slice(0, 16),
        battery_pct: h.battery_pct,
        plugged: !!h.plugged,
        device_id: h.device ? fnv32(h.device) : null,
      }))
    return json({ code: 200, items })
  }

  if (method === 'GET' && path === '/api/device/status') {
    const deviceId = parseInt(url.searchParams.get('device_id'))
    const key = deviceListOf(settings, messages, heartbeats).find((k) => fnv32(k) === deviceId)
    if (!key) return json({ detail: '设备不存在' }, 404)
    const dh = heartbeats.filter((h) => h.device === key).slice(-50)
    return json({
      code: 200,
      device: { id: deviceId, name: (settings.device_meta || {})[key]?.name || key, device_key: key },
      current: deviceStatus(settings, heartbeats, key),
      heartbeats: dh.reverse().map((h) => ({
        ts: fmtTs(h.ts), battery_pct: h.battery_pct, plugged: !!h.plugged, battery_info: h.battery_info,
      })),
      events: deriveEvents(settings, heartbeats, key),
    })
  }

  if (method === 'GET' && path === '/api/stats/hourly') {
    const days = Math.min(90, Math.max(1, parseInt(url.searchParams.get('days')) || 7))
    const deviceId = url.searchParams.get('device_id') ? parseInt(url.searchParams.get('device_id')) : null
    const deviceKeyById = new Map(deviceListOf(settings, messages, heartbeats).map((k) => [fnv32(k), k]))
    const since = Date.now() - days * 86400000
    const out = { sms: Array(24).fill(0), call: Array(24).fill(0) }
    for (const m of messages) {
      if (m.ts < since) continue
      if (deviceId != null && deviceKeyById.get(deviceId) !== m.device) continue
      const hour = parseInt(fmtTs(m.ts).slice(11, 13))
      if (out[m.type] != null) out[m.type][hour]++
    }
    return json({ code: 200, days, hourly: out })
  }

  if (method === 'GET' && path === '/api/stats/daily') {
    const days = Math.min(90, Math.max(1, parseInt(url.searchParams.get('days')) || 7))
    const deviceId = url.searchParams.get('device_id') ? parseInt(url.searchParams.get('device_id')) : null
    const deviceKeyById = new Map(deviceListOf(settings, messages, heartbeats).map((k) => [fnv32(k), k]))
    const items = []
    const nowDay = fmtTs(Date.now()).slice(0, 10)
    for (let i = days - 1; i >= 0; i--) {
      const dayStartMs = parseTime(fmtTs(Date.now() - i * 86400000).slice(0, 10) + ' 00:00:00')
      const dayEndMs = dayStartMs + 86400000
      const inDay = messages.filter((m) => m.ts >= dayStartMs && m.ts < dayEndMs)
      let sms = inDay.filter((m) => m.type === 'sms').length
      let call = inDay.filter((m) => m.type === 'call').length
      if (deviceId != null) {
        const dk = deviceKeyById.get(deviceId)
        sms = inDay.filter((m) => m.type === 'sms' && m.device === dk).length
        call = inDay.filter((m) => m.type === 'call' && m.device === dk).length
      }
      const dayHbs = deviceId != null
        ? heartbeats.filter((h) => deviceKeyById.get(deviceId) === h.device)
        : heartbeats
      items.push({
        date: fmtTs(dayStartMs).slice(5, 10),
        sms, call,
        working_minutes: Math.round(workingSeconds(dayHbs, settings, dayStartMs, dayEndMs) / 60),
      })
    }
    void nowDay
    return json({ code: 200, items, threshold_minutes: thresholdMin(settings) })
  }

  return json({ detail: 'Not Found' }, 404)
}

// ---------- 推送入库 ----------

async function ingest(request, env, settings, preBody) {
  let body = preBody
  if (!Object.keys(body).length) {
    const text = await request.text()
    body = parseBody(text)
  }
  if (!body || !Object.keys(body).length) return json({ code: 400, msg: 'bad request body' }, 400)

  const msgType = String(body.type || '').trim().toLowerCase() || 'sms'
  if (!['sms', 'call', 'heartbeat'].includes(msgType)) {
    return json({ code: 400, msg: `unknown type: ${msgType}` }, 400)
  }

  const deviceStr = String(body.device || '').trim() || '未命名设备'
  const simStr = String(body.sim || '').trim()
  const ts = parseTime(body.time != null && body.time !== '' ? body.time : body.timestamp)

  if (msgType === 'heartbeat') {
    const text = `${body.battery || ''} ${body.plugged || ''} ${body.info || ''}`
    let pct = null
    const digits = String(body.battery ?? '').match(/[\d.]+/)
    if (digits) pct = parseFloat(digits[0])
    const plugged = /充电|AC|USB|Wireless|正在充电/.test(text)
    await appendLine(env, `data/heartbeats/${dayStr(ts)}.jsonl`, {
      ts, battery_pct: pct, plugged, battery_info: String(body.battery ?? ''), device: deviceStr,
    })
    return json({ code: 200, msg: 'ok' })
  }

  const sender = String(body.from ?? '').trim()
  const content = String(body.content ?? '').trim()
  if (!sender && !content) return json({ code: 400, msg: 'empty message' }, 400)
  const dedup = await sha1Hex(`${msgType}|${sender}|${content}|${ts}`)
  const dayKey = `data/messages/${dayStr(ts)}.jsonl`
  const existing = await loadLines(env, dayKey)
  if (existing.some((m) => m.dedup_key === dedup)) return json({ code: 200, msg: 'ok' })

  existing.push({
    id: crypto.randomUUID(),
    type: msgType, sender, content, sim_slot: simStr, device: deviceStr,
    receive_time: fmtTs(ts), ts, dedup_key: dedup,
  })
  await env.R2.put(dayKey, existing.map((m) => JSON.stringify(m)).join('\n'))
  return json({ code: 200, msg: 'ok' })
}
