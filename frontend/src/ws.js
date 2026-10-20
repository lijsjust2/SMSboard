// WebSocket 客户端：自动重连，分发事件给订阅者
import { getToken } from './api'

let ws = null
let retryTimer = null
const listeners = new Set()

export function onWsEvent(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

function connect() {
  if (!getToken()) return
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${window.location.host}/ws?token=${getToken()}`)
  ws.onopen = () => { window.__smsboard_ws_ok = true }
  ws.onmessage = (e) => {
    try {
      const payload = JSON.parse(e.data)
      listeners.forEach((fn) => fn(payload))
    } catch { /* ignore */ }
  }
  ws.onclose = () => {
    window.__smsboard_ws_ok = false
    retryTimer = setTimeout(connect, 3000)
  }
}

export function startWs() {
  if (ws && ws.readyState <= 1) return
  connect()
}

export function stopWs() {
  clearTimeout(retryTimer)
  if (ws) ws.close()
  ws = null
  window.__smsboard_ws_ok = false
}
