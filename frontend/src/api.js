// 统一请求封装：自动带 JWT，401 跳转登录
const TOKEN_KEY = 'smsboard_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}
export function setToken(t) {
  localStorage.setItem(TOKEN_KEY, t)
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

function formatDetail(detail) {
  // FastAPI 422 会返回 detail: [{msg, loc...}, ...]
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg || JSON.stringify(d)).join('；')
  }
  if (detail && typeof detail === 'object') return JSON.stringify(detail)
  return detail || '请求失败'
}

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const resp = await fetch(path, { ...options, headers })
  if (resp.status === 401) {
    clearToken()
    window.location.href = '/login'
    throw new Error('未登录')
  }
  const data = await resp.json().catch(() => ({}))
  if (!resp.ok) throw Object.assign(new Error(formatDetail(data.detail)), { status: resp.status })
  return data
}

export default {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) }),
  put: (path, body) => request(path, { method: 'PUT', body: JSON.stringify(body) }),
  delete: (path) => request(path, { method: 'DELETE' }),
}

// 复制到剪贴板：优先 Clipboard API（HTTPS/localhost），HTTP 环境回退 execCommand
export async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch { /* 走回退 */ }
  }
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.top = '-9999px'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.focus()
  ta.select()
  let ok = false
  try {
    ok = document.execCommand('copy')
  } catch {
    ok = false
  }
  document.body.removeChild(ta)
  return ok
}
