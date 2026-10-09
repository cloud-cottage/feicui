// 印人采集 API 契约调用层（feicui 侧，批 1）。
// 端点（拆解件 §4.2）：
//   POST /api/persons/sync        触发采集（拉全量 → 归一化 → 落独立库 → 批次包）
//   GET  /api/persons             列表（分页 / 筛选）
//   GET  /api/persons/{grbsm}     单人（详情 + 关联印谱/印章）
//   GET  /api/persons/batches     批次列表
// 本文件**只做形状转发**，不含业务真值、不做任何派生/估算；失败归一化统一走 client.request。
import { request } from './client'

// ── 列表：GET /api/persons?page=&limit=&initial=&nationality=&has_dates=&has_relations=&q=
export function listPersons({ page, limit, initial, nationality, has_dates, has_relations, q } = {}) {
  return request('/persons', {
    query: { page, limit, initial, nationality, has_dates, has_relations, q },
  })
}

// ── 单人：GET /api/persons/{grbsm}
export function getPerson(grbsm) {
  return request(`/persons/${encodeURIComponent(grbsm)}`)
}

// ── 批次：GET /api/persons/batches
export function listBatches() {
  return request('/persons/batches')
}

// ── 采集：POST /api/persons/sync
// 请求体（均可选）：{batch_id?, resume?, delay?, limit?}
// 响应＝批回执读数（persons_ok / relations_ok / failed_count / failures[] / content_fingerprint …）
export function syncPersons(payload = {}) {
  return request('/persons/sync', { method: 'POST', body: payload })
}
