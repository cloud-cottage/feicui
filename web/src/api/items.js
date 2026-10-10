// 印谱采集 API 契约调用层（feicui 侧，批 1）。
// 端点（拆解件 §4）：
//   POST /api/items/sync      触发采集（本体取 book/list 一次全量 → 逐本 graph/book 取关联 → detail 降 best-effort → 归一化 → 落独立库 → 就绪包）
//   GET  /api/items           列表（分页 / 筛选：有无影像 / 有无年份 / 题名关键字）
//   GET  /api/items/{seqid}   单本（详情 + 关联责任者）
//   GET  /api/items/batches   批次列表
// 本文件**只做形状转发**，不含业务真值、不做任何派生/估算；失败归一化统一走 client.request。
import { request } from './client'

// ── 列表：GET /api/items?page=&limit=&has_image=&has_year=&q=
export function listItems({ page, limit, has_image, has_year, q } = {}) {
  return request('/items', {
    query: { page, limit, has_image, has_year, q },
  })
}

// ── 单本：GET /api/items/{seqid}
export function getItem(seqid) {
  return request(`/items/${encodeURIComponent(seqid)}`)
}

// ── 批次：GET /api/items/batches
export function listBatches() {
  return request('/items/batches')
}

// ── 生成 xiai 就绪包：POST /api/items/package?batch_id=
// 从 feicui 本库重建（**不联网采集**）；响应＝就绪包摘要（rows / creators_rows / field_dict /
// key_face_status / detail_policy / idempotency / checks …）。
export function buildItemPackage(batchId) {
  return request('/items/package', { method: 'POST', query: { batch_id: batchId } })
}

// ── 采集：POST /api/items/sync
// 请求体（均可选）：{batch_id?, resume?, delay?, limit?}
// 响应＝批回执读数（items_ok / creators_ok / remaining / failed_count / failures[] / content_fingerprint …）
export function syncItems(payload = {}) {
  return request('/items/sync', { method: 'POST', body: payload })
}
