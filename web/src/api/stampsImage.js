// E6 取印面裁图 —— **正式契约**（`feicui/docs/feicui.spec.md` **v1.3** §3.5 E6 全表 + §3.1 E6 行）
// ─────────────────────────────────────────────────────────────────────────────
// 路径形状（**3 段**：`page` 与 `idx` 都必须给）：
//
//     GET /api/jobs/{job_id}/stamps/{page}/{idx}/image
//
//   * `{page}` **1-based**（↔ `stamps.page`）、`{idx}` **0-based**（↔ `stamps.idx`）；**无查询参数**；
//   * `200` = 影像字节（`Content-Type` 取**文件实际类型**、`Content-Length` 必填、**不包 JSON 信封**）；
//   * `404` = **三类同码**：`JOB_NOT_FOUND` / `STAMP_NOT_FOUND` / `IMAGE_UNAVAILABLE`；
//   * `400` = 参数非法；`500` = 读盘 / 解码异常、**影像类型不可判定**。
//
// 为什么必须带 `page`（规范 §3.5 依据）：行级唯一锚是 **`(pdf_name, page, idx)`**，
// `idx` 单值在 job 内**不唯一**（每页都从 0 重排）⇒ 只用 `idx` 取不到确定的那枚印面。
//
// 纪律（写死在此，便于**一处收口**）：
//   ① 本文件是取图路径的**唯一常量来源**——不得在任何页面 / 组件里硬编码该路径；
//   ② **已废止的 2 段形态**（`/api/jobs/{job_id}/stamps/{idx}/image`）**自 spec v1.2 起不是契约**；
//      后端**不两套并存**（调用它返 `404`），前端**不得**再生成该路径；
//   ③ 取不到图时页面显示「**裁图不可用**」并给出**真实原因码**（`JOB_NOT_FOUND` /
//      `STAMP_NOT_FOUND` / `IMAGE_UNAVAILABLE`），**绝不**用占位图 / 示例图冒充真实裁图；
//   ④ 只读：本模块不写库、不缓存影像字节。
import { API_BASE } from '@/config/env'

/** E6 路径模板（**3 段**，正式契约；前端唯一来源） */
export const STAMP_IMAGE_PATH_TEMPLATE = '/api/jobs/{job_id}/stamps/{page}/{idx}/image'

/** 人读口径说明（供页面提示，避免各处自述不一致） */
export const STAMP_IMAGE_CONTRACT_NOTE =
  'E6（spec v1.3 §3.5）：路径为 3 段 —— /api/jobs/{job_id}/stamps/{page}/{idx}/image；' +
  '{page} 1-based、{idx} 0-based，两者都必给。已废止的 2 段形态（不带 page 段）不是契约，后端不实现（返 404）。'

/** E6 的 404 原因码 → 人读解释（§3.5 三类同码、原因码分列） */
export const E6_REASON_TEXT = {
  JOB_NOT_FOUND: 'job 不存在',
  STAMP_NOT_FOUND: '该 (page, idx) 记录不存在',
  IMAGE_UNAVAILABLE: 'img_path 缺失 / 越界 / 文件不在盘上',
}

/**
 * 构造 **3 段**取图 URL（正式契约）。
 * `page` 1-based、`idx` 0-based；两者缺一即**拼不出**合法契约路径，调用方须先过 `stampAnchorOf`。
 */
export function stampImageUrl(jobId, page, idx) {
  return (
    `${API_BASE}/jobs/${encodeURIComponent(jobId)}` +
    `/stamps/${encodeURIComponent(page)}/${encodeURIComponent(idx)}/image`
  )
}

function _asInt(value) {
  if (typeof value === 'number' && Number.isInteger(value)) return value
  if (typeof value === 'string' && /^\d+$/.test(value.trim())) return parseInt(value.trim(), 10)
  return null
}

/**
 * 从 **E3 的 `items[]` 元素**里取 E6 需要的 `(page, idx)` 锚点。
 *
 * 键路径依据（spec §3.12「E3 `records` 形状与 AC-08 必填 11 项键路径」，v1.3 冻结）：
 *   * `page` = 顶层 **`sourcePageNo`**（1-based，§3.12 #8 **已冻结**）；
 *   * `idx`  = **`feicui.stampIdx`**（= `stamps.idx`，0-based）。
 *     真源＝§3.12 点名的**形状真源** `feicui/export.py::build_record`（未导出行由
 *     `server/app/records.py::_shell_record` 同形补壳），两处都产出该键。
 *     ⚠ **规范缺口 G-1b**：§3.1 E3 行与 §3.12 都**未逐项冻结 `feicui{}` 子对象的键集**，
 *     故 `feicui.stampIdx` 虽与真源一致，**不是规范明文冻结的键路径**——缺口已登记，**不在此猜值**。
 *
 * 取不到锚点 ⇒ `ok:false`（页面显示「无 page/idx 锚点」，**不发**请求、**不**用 2 段路径兜底）。
 */
export function stampAnchorOf(item) {
  if (!item || typeof item !== 'object') {
    return { ok: false, page: null, idx: null, note: 'items 元素不是对象 ⇒ 取不到 (page, idx)' }
  }
  const feicui = item.feicui && typeof item.feicui === 'object' ? item.feicui : {}
  const page = _asInt(item.sourcePageNo)
  let idx = _asInt(feicui.stampIdx)
  if (idx === null) {
    // 形状真源的同一份信息在 assets[].seq 上（`_shell_record` 与 `build_record` 都产出）；
    // 取不到 stampIdx 时按 seq 兜底，仍取不到就如实报缺，**不猜**。
    const assets = Array.isArray(item.assets) ? item.assets : []
    const seqs = assets.map((a) => _asInt(a && a.seq)).filter((v) => v !== null)
    if (seqs.length === 1) idx = seqs[0]
  }
  const missing = []
  if (page === null || page < 1) missing.push('sourcePageNo（1-based page）')
  if (idx === null || idx < 0) missing.push('feicui.stampIdx（0-based idx）')
  if (missing.length) {
    return {
      ok: false,
      page,
      idx,
      note: `本条 items 记录未携带取图锚点：缺 ${missing.join(' 与 ')}（规范缺口 G-1b）`,
    }
  }
  return { ok: true, page, idx, note: '' }
}

/** §3.13：响应头里的非 ASCII 值（如含中文书名的 `x-feicui-img-path`）是**百分号编码**的，
 *  展示时还原；还原失败则原样回吐（不猜、不吞）。 */
export function decodeHeaderValue(raw) {
  if (!raw) return ''
  try {
    return decodeURIComponent(raw)
  } catch (e) {
    return raw
  }
}

/** 从错误体里取 E6 原因码（两种错误体形状：顶层 `error` / `detail.error`，见 spec §3.4） */
export function e6ErrorCode(body) {
  if (!body || typeof body !== 'object') return null
  if (typeof body.error === 'string' && body.error) return body.error
  const d = body.detail
  if (d && typeof d === 'object' && typeof d.error === 'string' && d.error) return d.error
  return null
}

/**
 * 取一次裁图并归一化结果（**不造假图**）：
 *   * `ok`          —— 200；`url` 可直接给 `<img src>`；
 *   * `unavailable` —— 404（三类同码，带 `code`）；
 *   * `bad-param`   —— 400；`error` —— 其它状态码；`unknown` —— 网络异常；
 *   * `no-anchor`   —— items 里取不到 `(page, idx)` ⇒ **不发请求**（避免用废止的 2 段路径兜底）。
 */
export async function probeStampImage(jobId, page, idx) {
  const anchor = stampAnchorOf({ sourcePageNo: page, feicui: { stampIdx: idx } })
  if (!anchor.ok) return { state: 'no-anchor', url: null, note: anchor.note }
  const url = stampImageUrl(jobId, anchor.page, anchor.idx)
  try {
    const res = await fetch(url, { method: 'GET' })
    if (res.ok) {
      return {
        state: 'ok',
        url,
        status: res.status,
        contentType: res.headers.get('content-type') || '',
        imgPath: res.headers.get('x-feicui-img-path') || '',
      }
    }
    let body = null
    try {
      body = await res.json()
    } catch (e) {
      body = null
    }
    const code = e6ErrorCode(body)
    if (res.status === 404) {
      return { state: 'unavailable', url, status: 404, code, detail: E6_REASON_TEXT[code] || '' }
    }
    if (res.status === 400) {
      return { state: 'bad-param', url, status: 400, code, detail: '参数非法（page 1-based / idx 0-based）' }
    }
    return { state: 'error', url, status: res.status, code, detail: '' }
  } catch (e) {
    return { state: 'unknown', url, detail: String((e && e.message) || e) }
  }
}
