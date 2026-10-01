/**
 * 玺爱 · 印章与印面读取服务
 *
 * 层级（canonical）：印章 `seal` 1 对 N 印面 `face`；边款是 `kind = EDGE` 的特殊印面。
 * 三类属性按**印面**归属：固定属性（印面图片 / 材质 / 边款图片 ID）、
 * 可标记属性（印文简体字 / 印文古字 / 朝代 / 分类 / 作者 / 印文释义）、
 * 影像属性（实物照片，见 photos.js）。
 *
 * 兼容说明：印面行同时带规范字段名 `id` / `sealId` / `kind` 与既落盘视图在用的
 * `stamp_id` 别名（＝`sealId`）；印章行保留 `stamp_id`，并另给规范字段名
 * `id` / `name` / `category` 作别名。
 */

import {
  listSealRows,
  listFaceRows,
  listImageRows,
  createSealWithFaceRows,
  writeFaceFixedAttributes,
  replaceFaceImage as dbReplaceFaceImage,
  readImageDataUrl,
  toUint8Array,
  PermissionError
} from '../data/db.js'
import { currentUser } from '../data/session.js'
import { FACE_KIND } from '../data/seed.js'
import { IMAGE_LIMITS, describeBytes, sniffBytesMime } from '../utils/image.js'

export { FACE_KIND }

const KIND_LABELS = {
  [FACE_KIND.FACE]: '印面',
  [FACE_KIND.EDGE]: '边款'
}

const ORDINALS = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']

/** 可标记属性（勘误对象）在印面上的键名。 */
const MARKABLE_KEYS = [
  'transcription_simplified',
  'seal_name',
  'dynasty',
  'seal_type',
  'author',
  'transcription'
]

export function faceKindLabel(kind) {
  return KIND_LABELS[kind] || KIND_LABELS[FACE_KIND.FACE]
}

/* -------------------------------- 印面 -------------------------------- */

/**
 * 把一行印面组装为视图模型。
 * 固定属性里指向影像的编号会在这里解析成影像行；解析不到的编号单独列出，
 * 供页面给出**可读空态**（不得静默忽略）。
 */
export function faceViewModel(row) {
  const images = listImageRows()
  const byId = (id) => images.find((img) => img.id === id) || null
  const sealId = row.sealId || row.stamp_id || ''
  const edgeIds = Array.isArray(row.edge_image_ids) ? row.edge_image_ids.map((id) => String(id)) : []
  const edgeImages = edgeIds.map(byId).filter(Boolean)
  return {
    ...row,
    id: row.id, // 规范字段：印面主键
    sealId, // 规范字段：所属印章
    stamp_id: sealId, // 兼容别名：＝sealId，勿删
    kind: row.kind, // FACE＝印面 / EDGE＝边款
    isEdge: row.kind === FACE_KIND.EDGE,
    faceImage: byId(row.face_image_id), // 固定属性「印面图片」解析结果
    edgeImages, // 固定属性「边款图片 ID」解析结果
    missingEdgeIds: edgeIds.filter((id) => !byId(id)) // 解析不到的编号 ⇒ 页面出空态
  }
}

/** 某印章的全部印面（按种子顺序，含边款）。 */
export function listFacesOf(sealId) {
  return listFaceRows()
    .filter((row) => (row.sealId || row.stamp_id) === sealId)
    .map(faceViewModel)
}

export function getFaceById(faceId) {
  const row = listFaceRows().find((item) => item.id === faceId)
  return row ? faceViewModel(row) : null
}

/** 主印面（kind = FACE 的第一个）；无印面时返回 null。 */
export function primaryFaceOf(sealId) {
  const faces = listFacesOf(sealId)
  return faces.find((face) => face.kind === FACE_KIND.FACE) || faces[0] || null
}

/** 印面标签：所属印章内**同类别**序号 + 类别，如「印面二」「边款一」。 */
export function faceLabelOf(faceId, sealId = '') {
  const rows = listFaceRows()
  if (faceId) {
    const row = rows.find((item) => item.id === faceId)
    if (row) {
      const sealKey = row.sealId || row.stamp_id
      const siblings = rows.filter(
        (item) => (item.sealId || item.stamp_id) === sealKey && item.kind === row.kind
      )
      const index = siblings.findIndex((item) => item.id === faceId)
      return `${faceKindLabel(row.kind)}${ORDINALS[index] || String(index + 1)}`
    }
  }
  if (sealId) {
    const primary = rows.find(
      (item) => (item.sealId || item.stamp_id) === sealId && item.kind === FACE_KIND.FACE
    )
    if (primary) return faceLabelOf(primary.id)
  }
  return '印面归属待考'
}

/* -------------------------------- 印章 -------------------------------- */

/** 印面级取值，缺值时回落到印章行（兼容既落盘种子）。 */
function markableValue(primary, sealRow, key) {
  const faceValue = primary ? primary[key] : ''
  if (faceValue !== undefined && faceValue !== null && faceValue !== '') return faceValue
  const sealValue = sealRow ? sealRow[key] : ''
  return sealValue === undefined || sealValue === null ? '' : sealValue
}

/** 将印章行与印面、影像组装为页面视图模型。 */
export function listSeals({ dynasty = '', sealType = '', keyword = '' } = {}) {
  const kw = String(keyword || '').trim()

  return listSealRows()
    .map((row) => {
      const faces = listFacesOf(row.stamp_id)
      const primary = faces.find((face) => face.kind === FACE_KIND.FACE) || faces[0] || null
      const edges = faces.filter((face) => face.kind === FACE_KIND.EDGE)
      const edgeImages = edges.reduce((acc, face) => acc.concat(face.edgeImages), [])
      const resolved = {}
      MARKABLE_KEYS.forEach((key) => {
        resolved[key] = markableValue(primary, row, key)
      })
      return {
        ...row,
        id: row.stamp_id, // §4.1.1 规范字段名（印章主键）
        name: row.seal_name, // 兼容别名（＝印文 `seal_name`；「印章名称」概念已删，可空）
        category: row.seal_type, // §4.1.1 规范字段名（分类）
        faces, // 印面集合（印章 1 对 N 印面）
        faceCount: faces.length,
        faceImage: (primary && primary.faceImage) || null,
        edgeFaces: edges,
        edgeImages,
        hasEdge: edges.length > 0,
        images: listImageRows().filter((img) => img.stamp_id === row.stamp_id),
        ...resolved
      }
    })
    .filter((seal) => (dynasty ? seal.dynasty === dynasty : true))
    .filter((seal) => (sealType ? seal.seal_type === sealType : true))
    .filter((seal) => {
      if (!kw) return true
      const haystack = [
        seal.seal_name,
        seal.transcription_simplified,
        seal.author,
        seal.stamp_id,
        ...seal.faces.map((face) => face.seal_name),
        ...seal.faces.map((face) => face.transcription_simplified)
      ]
        .filter(Boolean)
        .join(' ')
      return haystack.includes(kw)
    })
}

export function getSealById(stampId) {
  return listSeals().find((seal) => seal.stamp_id === stampId) || null
}

export function listImagesByStamp(stampId) {
  return listImageRows().filter((img) => img.stamp_id === stampId)
}

/**
 * 固定属性（**按印面归属**）。
 * 传入印面 → 该印面的三项固定属性；传入印章（兼容旧调用）→ 该印章主印面的三项。
 * @returns {{face_id:string|null, face_image_id:string|null, material:string, edge_image_ids:string[]}}
 */
export function fixedAttributesOf(target) {
  const empty = { face_id: null, face_image_id: null, material: '', edge_image_ids: [] }
  if (!target) return empty
  if (target.kind) {
    return {
      face_id: target.id,
      face_image_id: target.face_image_id || null,
      material: target.material || '',
      edge_image_ids: Array.isArray(target.edge_image_ids) ? target.edge_image_ids.map((id) => String(id)) : []
    }
  }
  const primary = primaryFaceOf(target.stamp_id)
  if (primary) return fixedAttributesOf(primary)
  return { ...empty, material: target.material || '' }
}

/* ------------------------------ 权限判定 ------------------------------ */

export function canBrowse() {
  return true
}

export function canSubmitCorrection() {
  return currentUser() !== null
}

export function canUploadPhoto() {
  return currentUser() !== null
}

export function canDownloadHd() {
  return currentUser() !== null
}

export function canEditFixedAttributes() {
  const user = currentUser()
  return user !== null && user.role === 'admin'
}

/** 当前（或指定）账号是否可**重新上传印面图** —— 供详情页决定按钮是否渲染。 */
export function canReplaceFaceImage(actor) {
  const user = actor || currentUser()
  return user !== null && user !== undefined && user.role === 'admin'
}

/* ============================================================================
   能力 6「上传印章（新增进藏品库）」（v1.3｜口径 B）
   ----------------------------------------------------------------------------
   权限（§3.7 / §6.1 第 6 行，与第 5 行同规格）：**仅管理员**。
   本段是**冻结给 UI 单**的服务层 API（函数名不得改）；「入口不可见」由 UI 单负责，
   「数据层拒绝越权写」在本段与数据层双层兜底（§6.2 第 1 条）。
   约定：`actor` 显式传入（缺省时回落到当前登录态）；**一律返回结构化结果**
   （`{ok:false, reason, message}`），**不抛未捕获异常**（AC-30 判负形态）。
   ============================================================================ */

/** 当前（或指定）账号是否可上传印章 —— 供广场页决定按钮是否渲染。 */
export function canUploadSeal(actor) {
  const user = actor || currentUser()
  return user !== null && user !== undefined && user.role === 'admin'
}

function deniedResult(message) {
  return { ok: false, reason: 'PERMISSION_DENIED', message }
}

function isPermissionError(err) {
  return err instanceof PermissionError || (err && err.name === 'PermissionError')
}

/**
 * **冻结 API ①**：管理员新增一枚印章（含 1 个印面 + 印面图，可选边款图）。
 *
 * @param {object|null} actor 操作者（须为管理员；缺省回落到当前登录态）
 * @param {object} payload
 *   - `seal_name`（**选填**，印文；旧键 `name` 保留为兼容别名。**可空 ⇒ 对外显示「佚名」**）
 *   - `dynasty`（**必填**，朝代 —— 广场筛选维度）
 *   - `type`（**必填**，分类 —— 广场筛选维度；也接受 `category` / `seal_type`）
 *   - `material`（可选）、`author` / `transcription` / `transcription_simplified` / `seal_style`（可选）
 *   - `faceImage`（**必填**，二进制（`Uint8Array` / `ArrayBuffer`）或 `data:image/...;base64,...`）
 *   - `edgeImage`（可选，同上）
 * @returns {Promise<{ok:boolean, deduped?:boolean, seal?:object, face?:object, faces?:Array, images?:Array,
 *   id?:string, stampId?:string, faceId?:string, reason?:string, missing?:string[], message:string}>}
 *   - 成功：`seal` / `face` 为视图模型（含 `stamp_id` / `id` / `faces` / `faceImage`），
 *     `images` 为**影像元数据**行（二进制在 IndexedDB，见 `loadImageDataUrl`）；
 *     `deduped: true` 表示**语义等价的印章此前已上传**，本次未新增（AC-35）。
 *   - 拒绝：非管理员 ⇒ `{ok:false, reason:'PERMISSION_DENIED'}`；
 *     必填缺失 ⇒ `{ok:false, reason:'MISSING_REQUIRED', missing:[...]}` 且**无半成品记录**（AC-34）。
 */
export async function createSealWithFace(actor, payload = {}) {
  const who = actor || currentUser()
  let written
  try {
    written = await createSealWithFaceRows(who, payload)
  } catch (err) {
    if (isPermissionError(err)) return deniedResult(err.message)
    return { ok: false, reason: 'ERROR', message: `上传印章失败：${(err && err.message) || '未知原因'}` }
  }
  if (!written.ok) {
    return {
      ok: false,
      reason: written.reason || 'ERROR',
      missing: written.missing || [],
      message: written.message
    }
  }
  const stampId = written.stampId || (written.seal && (written.seal.stamp_id || written.seal.id)) || ''
  const faceId = written.faceId || (written.face && written.face.id) || ''
  return {
    ok: true,
    deduped: written.deduped === true,
    id: stampId,
    stampId,
    faceId,
    seal: getSealById(stampId) || written.seal || null,
    face: faceId ? getFaceById(faceId) : null,
    faces: listFacesOf(stampId),
    images: listImagesByStamp(stampId),
    message: written.message
  }
}

/**
 * **冻结 API ②**：编辑印面的固定属性（印面图片 / 材质 / 边款图片 ID）。
 *
 * 与既有 `updateFaceFixedAttributes`（data 层同义能力，签名不同、出错即抛）同义；
 * 本函数是**冻结给 UI 单**的入口（显式 `actor` + 结构化返回）。
 * @param {object|null} actor 操作者（须为管理员；缺省回落到当前登录态）
 * @param {string} faceId 印面编号
 * @param {object} patch 仅限 `face_image_id` / `material` / `edge_image_ids`
 * @returns {{ok:boolean, face?:object, reason?:string, message:string}}
 */
export function updateSealFixedAttributes(actor, faceId, patch = {}) {
  const who = actor || currentUser()
  try {
    const row = writeFaceFixedAttributes(who, faceId, patch)
    return { ok: true, face: faceViewModel(row), message: '固定属性已保存' }
  } catch (err) {
    if (isPermissionError(err)) return deniedResult(err.message)
    return { ok: false, reason: 'ERROR', message: (err && err.message) || '固定属性保存失败' }
  }
}

/**
 * **附加能力（非冻结项，UI 单可直接用）**：按影像编号取回二进制并转 dataURL（**仅运行时渲染**）。
 * 二进制只在 IndexedDB，页面要用 `<img>` 显示时必须走这里（不得直接读 IndexedDB，§3.2 收口注）。
 * @returns {Promise<{ok:boolean, dataUrl?:string, bytes?:number, meta?:object, message:string}>}
 */
export async function loadImageDataUrl(imageId) {
  const meta = listImageRows().find((row) => row.id === imageId) || null
  if (!meta) return { ok: false, reason: 'NOT_FOUND', message: `未找到编号为「${imageId}」的影像` }
  const out = await readImageDataUrl(imageId)
  if (!out.ok) return { ok: false, reason: out.reason || 'ERROR', message: out.message }
  return { ok: true, dataUrl: out.dataUrl, bytes: out.bytes, meta, message: '' }
}

/**
 * **附加能力（非冻结项）**：广场筛选的朝代 / 分类选项 —— **由已入库数据派生**
 * （所以「上传印章」新写入的朝代 / 分类会立即出现在筛选条里，AC-28 的端到端筛选才成立）。
 */
export function listDynastyOptions() {
  return [...new Set(listSeals().map((seal) => seal.dynasty).filter(Boolean))]
}

export function listSealTypeOptions() {
  return [...new Set(listSeals().map((seal) => seal.seal_type).filter(Boolean))]
}

/* ============================================================================
   「重新上传印面图」（管理员，按印面逐个）—— 冻结给 UI 单的服务层 API
   ----------------------------------------------------------------------------
   口径：
   ① **仅管理员**（`canReplaceFaceImage`）：非管理员 ⇒ `{ok:false, reason:'FORBIDDEN'}`，
      数据层再独立拒一次（两道门，不依赖「按钮不渲染」这一条）。
   ② **入参是浏览器端处理管线产出的二进制**（`utils/image.js` 的 `exportSquareImage`
      产物：方形 + WebP），本服务**不接收 dataURL**、不自写 canvas 处理；
      对上再兜一道 1 MB 与「是否真是图片」（按字节魔数判定，**不采信声称的 mime**）。
   ③ **旧影像保留**：替换 ＝ 数据层「新增影像行 + 改印面指向」，本服务从不删旧影像。
   ④ 一律返回结构化结果（`{ok:false, reason, message}`），**不抛未捕获异常**。
   ============================================================================ */

/** 印面图入库字节上限（＝管线口径 `IMAGE_LIMITS.maxInputBytes` ＝ 1 MB）。 */
export const FACE_IMAGE_MAX_BYTES = IMAGE_LIMITS.maxInputBytes

/**
 * 重新上传某个印面的印面图（管理员专属；旧影像行与二进制保留）。
 *
 * @param {string} faceId 目标印面编号（如 `fc-0001-f1`）
 * @param {{bytes:Uint8Array|ArrayBuffer, mime?:string, width?:number, height?:number}} payload
 *        `bytes` ＝ 浏览器端处理后的图片字节（方形 WebP）；`mime` / `width` / `height`
 *        仅为调用方的声称值（**入库元数据以字节解析为准**，出入会在 `message` 里如实并列）。
 * @returns {Promise<{ok:boolean, faceImageId?:string, previousFaceImageId?:string|null, face?:object,
 *   image?:object, sealId?:string, deduped?:boolean, reason?:string, message:string}>}
 *   - 成功：`face` 为**替换后**的印面视图模型（`faceImage` / `face_image_id` 已指向新影像），
 *     详情页据此重读即可显示新图（刷新后一致）。
 *   - 拒绝路径（均可读、均有 `reason`）：未登录 ⇒ `UNAUTHENTICATED`；非管理员 ⇒ `FORBIDDEN`；
 *     未指定印面 ⇒ `MISSING_FACE`；内容空 ⇒ `EMPTY_CONTENT`；超 1 MB ⇒ `TOO_LARGE`；
 *     非图片字节 ⇒ `NOT_IMAGE`；印面不存在 ⇒ `UNKNOWN_FACE`；影像库写失败 ⇒ `STORAGE_UNAVAILABLE`。
 */
export async function replaceFaceImage(faceId, payload = {}) {
  const id = String(faceId || '').trim()
  const before = id ? listFaceRows().find((row) => row.id === id) || null : null
  const previousFaceImageId = before ? before.face_image_id || null : null

  const user = currentUser()
  if (!user) {
    return {
      ok: false,
      reason: 'UNAUTHENTICATED',
      previousFaceImageId,
      message: '请先登录管理员账号后再重新上传印面图'
    }
  }
  if (!canReplaceFaceImage(user)) {
    return {
      ok: false,
      reason: 'FORBIDDEN',
      previousFaceImageId,
      message: '仅管理员可以重新上传印面图'
    }
  }
  if (!id) {
    return { ok: false, reason: 'MISSING_FACE', previousFaceImageId, message: '未指定要替换影像的印面' }
  }

  const bytes = toUint8Array(payload.bytes)
  if (!bytes || bytes.length === 0) {
    return {
      ok: false,
      reason: 'EMPTY_CONTENT',
      previousFaceImageId,
      message: '印面图内容为空，请重新选择图片文件'
    }
  }
  if (bytes.length > FACE_IMAGE_MAX_BYTES) {
    return {
      ok: false,
      reason: 'TOO_LARGE',
      previousFaceImageId,
      message:
        `印面图过大：当前内容 ${describeBytes(bytes.length)}，上限 ${describeBytes(FACE_IMAGE_MAX_BYTES)}（1 MB）。` +
        '请换一张更小的图，或先用手机 / 系统自带的压缩再上传。'
    }
  }
  /* 如实口径：格式按**字节魔数**判定；认不出 ⇒ 可读拒绝，绝不把非图片内容入库。 */
  const actualMime = sniffBytesMime(bytes)
  if (!actualMime) {
    const claimed = String(payload.mime || '').trim().toLowerCase()
    return {
      ok: false,
      reason: 'NOT_IMAGE',
      previousFaceImageId,
      message:
        '这不是可用的图片内容（无法识别图片格式），请重新选择 JPG / PNG / WebP 图片'
        + (claimed ? `（声称类型 ${claimed}）` : '')
    }
  }

  try {
    const written = await dbReplaceFaceImage(user, id, {
      bytes,
      mime: actualMime,
      width: payload.width,
      height: payload.height
    })
    if (!written.ok) {
      return {
        ok: false,
        reason: written.reason || 'ERROR',
        previousFaceImageId: written.previousFaceImageId ?? previousFaceImageId,
        message: written.message
      }
    }
    return {
      ok: true,
      deduped: written.deduped === true,
      sealId: written.sealId || '',
      faceId: id,
      /* 视图模型按**当前库态**重建 ⇒ `faceImage` / `face_image_id` 立即反映替换结果。 */
      face: getFaceById(id),
      faceImageId: written.faceImageId,
      previousFaceImageId: written.previousFaceImageId ?? previousFaceImageId,
      image: written.image || null,
      message: written.message
    }
  } catch (err) {
    if (isPermissionError(err)) {
      return { ok: false, reason: 'FORBIDDEN', previousFaceImageId, message: err.message }
    }
    return {
      ok: false,
      reason: 'ERROR',
      previousFaceImageId,
      message: `替换印面图失败：${(err && err.message) || '未知原因'}`
    }
  }
}
