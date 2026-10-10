// 拖曳上传（**additive** 端点 `POST /api/jobs/upload`）—— 与 E1 的取数层分开：
// 本文件**只**把 `File` 以裸字节流 POST 上去、回吐服务器侧 `pdf_path`；
// **不建 job、不写 DB、不做任何派生**（建 job 仍走 `api/jobs.js` 的 E1）。
//
// 为什么必须 `XMLHttpRequest`：源 PDF 实测 38 MB、历史 372 MB ⇒ 上传**必须有进度反馈**，
// 而 `fetch()` 给不了上传进度（无 upload progress 事件）。
//
// 契约（由 feicui 侧本单定义，规范未定义该端点）：
//   请求：`Content-Type: application/pdf` ＋ 裸字节流；文件名走 `X-Filename`（**URL-encoded UTF-8**）
//   响应：201 新写入 / 200 幂等复用
//         `{pdf_path, rel_path, filename, bytes, sha256, idempotent, dedup_suffix}`
//   错误：400 `EMPTY_BODY` / 400 `NOT_A_PDF` / 413 `PAYLOAD_TOO_LARGE`（结构化 JSON）
import { API_BASE } from '@/config/env'
import { BackendUnreachableError } from './client'

export const UPLOAD_PATH = `${API_BASE}/jobs/upload`

/**
 * @param {File} file
 * @param {{onProgress?: (loaded:number, total:number)=>void}} [opts]
 * @returns {Promise<{ok:boolean, status:number, body:any, raw:string}>}
 */
export function uploadPdf(file, { onProgress } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', UPLOAD_PATH, true)
    xhr.setRequestHeader('Content-Type', 'application/pdf')
    // 中文文件名：URL-encoded UTF-8（HTTP 头值只能是 latin-1，直送会 mojibake）
    xhr.setRequestHeader('X-Filename', encodeURIComponent(file.name || 'upload.pdf'))
    xhr.upload.onprogress = (e) => {
      if (onProgress && e.lengthComputable) onProgress(e.loaded, e.total)
    }
    xhr.onload = () => {
      let body = null
      try {
        body = JSON.parse(xhr.responseText)
      } catch {
        body = null // 非 JSON（如 dev 代理错误页）⇒ 页面按 raw 文本原样展示
      }
      resolve({
        ok: xhr.status >= 200 && xhr.status < 300,
        status: xhr.status,
        body,
        raw: xhr.responseText || '',
      })
    }
    xhr.onerror = () =>
      reject(new BackendUnreachableError(`${UPLOAD_PATH} 上传未到达后端（连接失败）`))
    xhr.onabort = () => reject(new Error('上传已取消'))
    xhr.ontimeout = () => reject(new Error('上传超时'))
    xhr.send(file)
  })
}
