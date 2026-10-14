// PDF 资料登记 API 契约调用层（output 四总目录落地单，2026-10-14）。
// 端点（docs/output-layout-v0.1.md §PDF 资料）：
//   GET   /api/pdf-records        列表＋筛选（status/q/page/limit）
//   PATCH /api/pdf-records/{id}   人工补填 {dynasty?/author?/notes?}（缺省键＝不改）
// 本文件只做形状转发，不含业务真值；失败归一化统一走 client.request。
import { request } from './client'

// ── 列表：GET /api/pdf-records?page=&limit=&status=&q=
// 出参：{total, page, limit, records[{id,filename,rel_path,sha256,size_bytes,page_count,
//        page_mm,scan_dpi,dir_key,isbn,dynasty,author,notes,status,created_at,updated_at}]}
export function listPdfRecords({ page, limit, status, q } = {}) {
  return request('/pdf-records', {
    query: { page, limit, status, q },
  })
}

// ── 补填：PATCH /api/pdf-records/{id}
// 请求体（缺省键＝不改）：{dynasty?, author?, notes?}；dynasty 必须 ∈ 15 枚举或 null。
// 成功 ⇒ {record: {…}}；朝代非法 ⇒ 400 DYNASTY_INVALID；id 不存在 ⇒ 404。
export function patchPdfRecord(id, payload) {
  return request(`/pdf-records/${encodeURIComponent(String(id))}`, {
    method: 'PATCH',
    body: payload,
  })
}
