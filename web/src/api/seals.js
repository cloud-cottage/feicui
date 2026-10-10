// 印章采集 API 契约调用层（feicui 侧，批 1）。
// 端点：
//   POST /api/seals/sync      触发采集（本体取 seal/list 一次全量 → 行内字段构建关联 → 归一化 → 落独立库 → 就绪包）
//   GET  /api/seals           列表（分页 / 筛选：审核状态 / 有无影像 / 印文关键字）
//   GET  /api/seals/{seqid}   单枚（详情 + 关联 + 影像台账）
//   GET  /api/seals/batches   批次列表
//   POST /api/seals/package   生成 xiai 就绪包（从本库重建、不联网；含 TIFF 内容寻址影像树）
//   GET  /api/seals/{seqid}/image/{kind}   读本地影像（kind ∈ yt|ytsw|yzbk）
// 本文件**只做形状转发**，不含业务真值、不做任何派生/估算；失败归一化统一走 client.request。
import { request } from './client'
import { API_BASE } from '@/config/env'

// ── 列表：GET /api/seals?page=&limit=&q=&audit_status=&has_image=
export function listSeals({ page, limit, q, audit_status, has_image } = {}) {
  return request('/seals', {
    query: { page, limit, q, audit_status, has_image },
  })
}

// ── 单枚：GET /api/seals/{seqid}
export function getSeal(seqid) {
  return request(`/seals/${encodeURIComponent(seqid)}`)
}

// ── 批次：GET /api/seals/batches
export function listBatches() {
  return request('/seals/batches')
}

// ── 生成 xiai 就绪包：POST /api/seals/package?batch_id=
// 从 feicui 本库重建（**不联网采集**）；响应＝就绪包摘要（rows / links_rows / field_dict /
// seal_ys_lookup / audit_status_distribution / image_policy / key_face_status / idempotency / checks …）。
export function buildSealPackage(batchId) {
  return request('/seals/package', { method: 'POST', query: { batch_id: batchId } })
}

// ── 采集：POST /api/seals/sync
// 请求体（均可选）：{batch_id?, resume?, delay?, limit?, with_detail?, with_graph?}
// 响应＝批回执读数（seals_ok / links_ok / remaining / failed_count / failures[] / content_fingerprint …）
export function syncSeals(payload = {}) {
  return request('/seals/sync', { method: 'POST', body: payload })
}

// ── 本地影像 URL（供 <img> 缩略图）：随 base 走，经既有 /feicui/api 代理
export function sealImageUrl(seqid, kind) {
  return `${API_BASE}/seals/${encodeURIComponent(seqid)}/image/${encodeURIComponent(kind)}`
}
