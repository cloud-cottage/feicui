// 通用格式化 / 展示辅助。不做任何业务真值推导。
export function fmtTime(value) {
  if (!value) return null
  return String(value)
}

export function nowStamp() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(
    d.getMinutes()
  )}:${p(d.getSeconds())}`
}

// 原始响应体展示：JSON 美化，非 JSON 原样文本；**绝不**改写内容
export function rawBodyText(body, rawText) {
  if (body !== undefined && body !== null) {
    try {
      return JSON.stringify(body, null, 2)
    } catch {
      /* fallthrough */
    }
  }
  if (rawText) return rawText
  return '（空响应体）'
}

export function isNil(v) {
  return v === undefined || v === null
}

export function nilDash(v) {
  return isNil(v) || v === '' ? '—' : String(v)
}
