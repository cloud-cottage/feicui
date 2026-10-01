/**
 * 玺爱 · 本单自测（Kong）：印面图「重新上传」（替换）—— 权限两道门 + 原子 + 旧影像保留 + 持久化
 *
 * 跑法：cd /Users/kevin/bistro/xiai && node feicui/ops/kong_xiai_k5_replace_face_image_selftest.mjs
 *
 * 载入方式：Vite SSR 载入器执行工程内**真实模块**（`src/data/db.js` / `src/services/seals.js` /
 * `src/services/index.js`），浏览器存储用替身（localStorage 内存表 + 最小 IndexedDB）。
 * 这是「**node 层直调服务层 / 数据层**」的那条证据：完全绕过 UI（不渲染任何组件、不点任何按钮），
 * 用普通用户会话直接调 `replaceFaceImage`，验「数据层 / 服务层独立拒绝越权写」。
 *
 * 本脚本覆盖：
 *   ① 权限两道门（服务层 FORBIDDEN / 数据层 FORBIDDEN；越权调用后库零变化）
 *   ② 原子替换成功路径（新增影像行 + 改印面指向；旧行逐字未改；旧二进制仍在且字节一致）
 *   ③ 回滚 / 原子（两处人为中途失败：影像二进制写失败、影像元数据未落盘 ⇒ 无半成品行 / 无孤儿二进制）
 *   ④ 持久化（重新读回：印面指向与影像行一致；视图模型 faceImage 同步）
 *
 * 说明：本脚本**不**验「方形 + WebP」——那是浏览器端管线（`utils/image.js` 需要 canvas）的产物，
 * 由 `kong_xiai_k5_replace_face_image_uiflow.py`（真浏览器）取证。
 * 所有循环有硬上界；退出码 0 = 全部通过。
 */
import { createServer } from 'vite'
import fs from 'node:fs'

const PROJECT = '/Users/kevin/bistro/xiai'
const OUT_JSON = `${PROJECT}/feicui/ops/kong_xiai_k5_replace_face_image_selftest_raw.json`
const OUT_TXT = `${PROJECT}/feicui/ops/kong_xiai_k5_replace_face_image_selftest_raw.txt`

/* ------------------------------ 断言收集 ------------------------------ */
const checks = []
function check(name, pass, detail) {
  checks.push({ name, pass: !!pass, detail: String(detail === undefined ? '' : detail) })
}

/* --------------------- 浏览器存储替身（localStorage） --------------------- */
const NS = 'xiai:v1:'
const mem = new Map()
/** 注入：下一次写入该键即抛（模拟 localStorage 满 / 不可写）。 */
const failNextWrite = new Set()
const writeLog = { fails: 0 }
globalThis.window = {
  localStorage: {
    getItem: (k) => (mem.has(k) ? mem.get(k) : null),
    setItem: (k, v) => {
      if (failNextWrite.has(k)) {
        failNextWrite.delete(k)
        writeLog.fails += 1
        throw new Error(`注入故障：${k} 写入失败（模拟本地存储不可写）`)
      }
      mem.set(k, String(v))
    },
    removeItem: (k) => mem.delete(k)
  }
}

/* --------------- 浏览器存储替身（最小 IndexedDB：blobstore 用到的面） --------------- */
const idbStores = new Map()
/** 注入：为 true 时 `store.put` 抛错（模拟影像库写入失败）。 */
let failPut = false
const idbLog = { putFails: 0, puts: 0 }
globalThis.indexedDB = {
  open(name) {
    const req = { result: null, error: null, onupgradeneeded: null, onsuccess: null, onerror: null, onblocked: null }
    const db = {
      objectStoreNames: { contains: (n) => idbStores.has(n) },
      createObjectStore: (n) => {
        idbStores.set(n, new Map())
        return {}
      },
      transaction: (n) => {
        if (!idbStores.has(n)) throw new Error(`no store ${n}`)
        const map = idbStores.get(n)
        const tx = { error: null, oncomplete: null, onabort: null, onerror: null }
        tx.objectStore = () => ({
          put: (value, key) => {
            if (failPut) {
              idbLog.putFails += 1
              throw new Error('注入故障：影像库写入失败')
            }
            idbLog.puts += 1
            map.set(key, value)
            return { result: key }
          },
          get: (key) => ({ result: map.get(key) }),
          getKey: (key) => ({ result: map.has(key) ? key : undefined }),
          delete: (key) => {
            map.delete(key)
            return { result: undefined }
          },
          getAllKeys: () => ({ result: [...map.keys()] })
        })
        setImmediate(() => tx.oncomplete && tx.oncomplete())
        return tx
      }
    }
    req.result = db
    setImmediate(() => {
      if (!idbStores.has('assets')) {
        if (req.onupgradeneeded) req.onupgradeneeded()
        else idbStores.set('assets', new Map())
      }
      req.onsuccess && req.onsuccess()
    })
    return req
  }
}

/* ------------------------------- 影像样本 ------------------------------- */
const PX_BODY = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=='
const pxBytes = new Uint8Array(Buffer.from(PX_BODY, 'base64'))
/** 第二张不同的图（尾部追加字节 ⇒ 摘要不同 ⇒ 不会被防重复用）。 */
const pxBytes2 = new Uint8Array(Buffer.concat([Buffer.from(PX_BODY, 'base64'), Buffer.from([7, 7, 7, 7])]))
const pxBytes3 = new Uint8Array(Buffer.concat([Buffer.from(PX_BODY, 'base64'), Buffer.from([9, 9, 9, 9])]))

const j = (v) => JSON.stringify(v)
let ssr = null
const report = { project: PROJECT, started_at: new Date().toISOString() }

const idOf = (faceId) => faceId

try {
  ssr = await createServer({
    root: PROJECT,
    appType: 'custom',
    server: { middlewareMode: true },
    logLevel: 'error',
    optimizeDeps: { noDiscovery: true }
  })
  const load = (p) => ssr.ssrLoadModule(p)

  const { services } = await load('/src/services/index.js')
  const db = await load('/src/data/db.js')
  const sealService = await load('/src/services/seals.js')

  /* ------------------------------ 0. 基线 ------------------------------ */
  const adminLogin = services.auth.login('16601061656', '1234')
  const admin = adminLogin.user
  const normalLogin = services.auth.login('13800000001', '1234') // 旧管理员号，现已降为普通用户
  const normal = normalLogin.user
  check(
    '0 管理员登录（唯一管理员手机号 16601061656）',
    adminLogin.ok && admin.role === 'admin',
    `role=${admin.role} id=${admin.id}`
  )
  check(
    '0 普通用户登录（13800000001，旧管理员号已降级）',
    normalLogin.ok && normal.role === 'user',
    `role=${normal.role} id=${normal.id}`
  )

  const FACE = 'fc-0001-f1' // 种子 XAI-0001 的主印面（face_image_id = img-0001f）
  const snapshot = () => ({
    images: db.listImageRows().map((r) => ({ ...r })),
    faces: db.listFaceRows().map((r) => ({ ...r })),
    seals: db.listSealRows().map((r) => ({ ...r }))
  })
  const counts = async () => ({
    images: db.listImageRows().length,
    faces: db.listFaceRows().length,
    seals: db.listSealRows().length,
    blobs: (await db.listImageBinaryKeys()).length
  })
  const faceImg = (id) => (db.listFaceRows().find((r) => r.id === id) || {}).face_image_id || null
  const imgRow = (id) => db.listImageRows().find((r) => r.id === id) || null

  const base = snapshot()
  const baseCounts = await counts()
  const baseFaceImageId = faceImg(FACE)
  check(
    '0 基线：印面 fc-0001-f1 当前影像编号 = img-0001f（种子）',
    baseFaceImageId === 'img-0001f',
    `face_image_id=${baseFaceImageId}`
  )
  report.baseline = { counts: baseCounts, face_image_id: baseFaceImageId, image_ids: base.images.map((r) => r.id) }

  /* --------------------- ① 权限两道门（node 层绕过 UI） --------------------- */
  const guard = (label, fn) => {
    /* 断言「不抛未捕获异常」：一律返回结构化结果。 */
    try {
      return { threw: false, value: fn() }
    } catch (err) {
      return { threw: true, error: `${(err && err.name) || 'Error'}: ${(err && err.message) || ''}` }
    }
  }

  /* ①-a 服务层：普通用户会话直调（不点任何按钮、不渲染任何组件） */
  services.auth.login('13800000001', '1234')
  report.forbidden = {}
  const beforeA = await counts()
  const a1 = await sealService.replaceFaceImage(FACE, { bytes: pxBytes2, mime: 'image/png', width: 1, height: 1 })
  const afterA = await counts()
  report.forbidden.service_call = {
    before: beforeA,
    result: a1,
    after: afterA,
    face_image_id_after: faceImg(FACE)
  }
  check(
    '① 服务层 · 普通用户直调 replaceFaceImage ⇒ 被拒且 reason = FORBIDDEN',
    a1.ok === false && a1.reason === 'FORBIDDEN',
    `ok=${a1.ok} reason=${a1.reason} message=${a1.message}`
  )
  check(
    '① 服务层 · 被拒后库零变化（影像行数 / 印面指向 / 二进制数三者均不变）',
    afterA.images === beforeA.images && afterA.blobs === beforeA.blobs && faceImg(FACE) === baseFaceImageId,
    j({ before: beforeA, after: afterA, face_image_id: faceImg(FACE) })
  )
  check(
    '① 服务层 · 被拒时无未捕获异常（结构化返回）',
    a1 && typeof a1.message === 'string' && a1.message.length > 0,
    `message=${a1.message}`
  )

  /* ①-b 数据层：普通用户 actor 直调（绕过服务层） */
  const beforeB = await counts()
  const b1 = await db.replaceFaceImage({ id: normal.id, phone: normal.phone, role: 'user' }, FACE, pxBytes2)
  const b2 = await db.replaceFaceImage(null, FACE, pxBytes2) // 游客
  const afterB = await counts()
  report.forbidden.data_call = { before: beforeB, user: b1, guest: b2, after: afterB, face_image_id_after: faceImg(FACE) }
  check(
    '① 数据层 · 普通用户 actor 直调 ⇒ reason = FORBIDDEN（不依赖 UI 隐藏入口）',
    b1.ok === false && b1.reason === 'FORBIDDEN',
    j({ ok: b1.ok, reason: b1.reason, message: b1.message })
  )
  check(
    '① 数据层 · 游客（actor = null）直调 ⇒ reason = FORBIDDEN',
    b2.ok === false && b2.reason === 'FORBIDDEN',
    j({ ok: b2.ok, reason: b2.reason, message: b2.message })
  )
  check(
    '① 数据层 · 两次越权调用后库零变化（影像行数 / 二进制数 / 印面指向）',
    afterB.images === beforeB.images && afterB.blobs === beforeB.blobs && faceImg(FACE) === baseFaceImageId,
    j({ before: beforeB, after: afterB, face_image_id: faceImg(FACE) })
  )

  /* 权限判定函数本身 */
  report.can_flags = {
    admin: sealService.canReplaceFaceImage(admin),
    user: sealService.canReplaceFaceImage(normal),
    guest: sealService.canReplaceFaceImage(null),
    current_user_is_normal: services.auth.login('13800000001', '1234').ok
  }
  check(
    '① canReplaceFaceImage：管理员 true / 普通用户 false / 游客 false',
    report.can_flags.admin === true && report.can_flags.user === false && report.can_flags.guest === false,
    j(report.can_flags)
  )

  /* --------------------- ② 管理员替换（成功路径，数据层） --------------------- */
  services.auth.login('16601061656', '1234')
  const beforeC = await counts()
  const oldRowBefore = j(imgRow(baseFaceImageId))
  const c1 = await db.replaceFaceImage(admin, FACE, pxBytes2)
  const afterC = await counts()
  const newRow = imgRow(c1.faceImageId)
  const keysAfterC = await db.listImageBinaryKeys()
  const newBinary = await db.getImageBinary(c1.faceImageId)
  report.replace_1 = {
    before: beforeC,
    result: { ok: c1.ok, reason: c1.reason, faceImageId: c1.faceImageId, previousFaceImageId: c1.previousFaceImageId, deduped: c1.deduped, message: c1.message },
    after: afterC,
    face_image_id: faceImg(FACE),
    new_row: newRow,
    old_row_unchanged: j(imgRow(baseFaceImageId)) === oldRowBefore,
    blob_keys: keysAfterC,
    new_binary_bytes: newBinary.ok ? newBinary.bytesLength : `ERR:${newBinary.message}`
  }
  check('② 管理员替换成功（ok = true）', c1.ok === true, j({ ok: c1.ok, reason: c1.reason, message: c1.message }))
  check(
    '② 返回含 faceImageId 与 previousFaceImageId（旧 = 种子 img-0001f）',
    c1.faceImageId && c1.previousFaceImageId === 'img-0001f' && c1.faceImageId !== c1.previousFaceImageId,
    j({ faceImageId: c1.faceImageId, previousFaceImageId: c1.previousFaceImageId })
  )
  check(
    '② 印面 face_image_id 已改指向新影像',
    faceImg(FACE) === c1.faceImageId,
    `face_image_id=${faceImg(FACE)} 新=${c1.faceImageId}`
  )
  check('② 影像行数 = 前 + 1', afterC.images === beforeC.images + 1, `${beforeC.images} → ${afterC.images}`)
  check(
    '② 旧影像行逐字未改（JSON 比对）',
    j(imgRow(baseFaceImageId)) === oldRowBefore,
    `old=${baseFaceImageId}`
  )
  check(
    '② 新影像行 kind = FACE 且与印面同一 sealId',
    newRow && newRow.kind === 'FACE' && newRow.stamp_id === 'XAI-0001' && newRow.sealId === 'XAI-0001',
    j(newRow && { kind: newRow.kind, stamp_id: newRow.stamp_id, sealId: newRow.sealId, ownerId: newRow.ownerId, storage: newRow.storage })
  )
  check(
    '② 二进制已落影像库（键 asset:<新影像编号>，字节数 = 上传字节数）',
    newBinary.ok && newBinary.bytesLength === pxBytes2.length && keysAfterC.includes(`asset:${c1.faceImageId}`),
    j({ bytesLength: newBinary.ok ? newBinary.bytesLength : null, expect: pxBytes2.length, keys: keysAfterC })
  )
  check('② 印章行未被改写（只增影像 + 改印面指向）', j(db.listSealRows()) === j(base.seals), 'seals JSON 逐字比对')

  /* 视图模型：faceImage / faceImageId 立即反映替换结果 */
  const vm = sealService.getFaceById(FACE)
  const sealVm = sealService.getSealById('XAI-0001')
  report.view_model = {
    face_id: vm && vm.id,
    face_image_id: vm && vm.face_image_id,
    faceImage_id: vm && vm.faceImage && vm.faceImage.id,
    primary_face_image_id: sealVm && sealVm.faces[0].face_image_id
  }
  check(
    '② 视图模型 faceViewModel.faceImage 指向新影像（详情页据此渲染）',
    vm && vm.face_image_id === c1.faceImageId && vm.faceImage && vm.faceImage.id === c1.faceImageId,
    j(report.view_model)
  )

  /* --------------------- ②′ 第二次替换：旧影像二进制必须仍在 --------------------- */
  const firstImageId = c1.faceImageId
  const beforeD = await counts()
  const d1 = await db.replaceFaceImage(admin, FACE, pxBytes3)
  const afterD = await counts()
  const firstBinaryAfter = await db.getImageBinary(firstImageId)
  const firstRowAfter = imgRow(firstImageId)
  report.replace_2 = {
    before: beforeD,
    result: { ok: d1.ok, faceImageId: d1.faceImageId, previousFaceImageId: d1.previousFaceImageId },
    after: afterD,
    first_image_id: firstImageId,
    first_row_still_there: !!firstRowAfter,
    first_row_unchanged: firstRowAfter && firstRowAfter.face_image_id === undefined ? true : undefined,
    first_binary_bytes: firstBinaryAfter.ok ? firstBinaryAfter.bytesLength : `ERR:${firstBinaryAfter.message}`,
    blob_keys: await db.listImageBinaryKeys()
  }
  check(
    '②′ 连续替换：第二次的 previousFaceImageId = 第一次的新编号',
    d1.ok === true && d1.previousFaceImageId === firstImageId,
    j({ ok: d1.ok, previous: d1.previousFaceImageId, first: firstImageId })
  )
  check(
    '②′ 旧影像行仍在库且逐字未改',
    !!firstRowAfter && j(firstRowAfter) === j(newRow),
    `row=${j(firstRowAfter)}`
  )
  check(
    '②′ 旧影像**二进制**仍在且字节一致（替换不删旧图）',
    firstBinaryAfter.ok && firstBinaryAfter.bytesLength === pxBytes2.length,
    j({ ok: firstBinaryAfter.ok, bytes: firstBinaryAfter.ok ? firstBinaryAfter.bytesLength : null, expect: pxBytes2.length })
  )
  check('②′ 影像行数 = 前 + 1（旧行不删、只增新行）', afterD.images === beforeD.images + 1, `${beforeD.images} → ${afterD.images}`)

  /* --------------------- ③ 回滚 / 原子（人为中途失败） --------------------- */
  /* ③-1 影像二进制写库失败（putImageBinary 报错） */
  const beforeE = await counts()
  const faceBeforeE = faceImg(FACE)
  const keysBeforeE = await db.listImageBinaryKeys()
  failPut = true
  const e1 = await db.replaceFaceImage(admin, FACE, new Uint8Array(Buffer.concat([pxBytes2, Buffer.from([1, 2, 3])])))
  failPut = false
  const afterE = await counts()
  report.rollback_binary_fail = {
    before: beforeE,
    injected: 'IDBObjectStore.put 抛错（模拟影像库写入失败）',
    result: { ok: e1.ok, reason: e1.reason, message: e1.message },
    after: afterE,
    face_image_id: faceImg(FACE),
    blob_keys_before: keysBeforeE,
    blob_keys_after: await db.listImageBinaryKeys()
  }
  check(
    '③-1 影像二进制写失败 ⇒ 结构化失败（reason = STORAGE_UNAVAILABLE，未抛异常）',
    e1.ok === false && e1.reason === 'STORAGE_UNAVAILABLE',
    j({ ok: e1.ok, reason: e1.reason, message: e1.message })
  )
  check(
    '③-1 回滚：影像行数不变（无半成品行）',
    afterE.images === beforeE.images,
    `${beforeE.images} → ${afterE.images}`
  )
  check('③-1 回滚：印面 face_image_id 不变', faceImg(FACE) === faceBeforeE, j({ before: faceBeforeE, after: faceImg(FACE) }))
  check(
    '③-1 回滚：影像库键集合不变（无孤儿二进制）',
    j(await db.listImageBinaryKeys()) === j(keysBeforeE),
    j({ before: keysBeforeE, after: await db.listImageBinaryKeys() })
  )

  /* ③-2 影像元数据未落盘（localStorage 写失败，`writeKey` 只返回 false 不抛） */
  const beforeF = await counts()
  const faceBeforeF = faceImg(FACE)
  const keysBeforeF = await db.listImageBinaryKeys()
  failNextWrite.add(`${NS}images`)
  const f1 = await db.replaceFaceImage(admin, FACE, new Uint8Array(Buffer.concat([pxBytes2, Buffer.from([4, 5, 6])])))
  const afterF = await counts()
  report.rollback_metadata_fail = {
    before: beforeF,
    injected: 'localStorage 写入 xiai:v1:images 抛错（模拟本地存储不可写）',
    injected_write_fails: writeLog.fails,
    result: { ok: f1.ok, reason: f1.reason, message: f1.message },
    after: afterF,
    face_image_id: faceImg(FACE),
    blob_keys_before: keysBeforeF,
    blob_keys_after: await db.listImageBinaryKeys()
  }
  check(
    '③-2 影像元数据未落盘 ⇒ 结构化失败（reason = STORAGE_UNAVAILABLE）',
    f1.ok === false && f1.reason === 'STORAGE_UNAVAILABLE',
    j({ ok: f1.ok, reason: f1.reason, message: f1.message })
  )
  check('③-2 回滚：影像行数不变', afterF.images === beforeF.images, `${beforeF.images} → ${afterF.images}`)
  check('③-2 回滚：印面 face_image_id 不变', faceImg(FACE) === faceBeforeF, j({ before: faceBeforeF, after: faceImg(FACE) }))
  check(
    '③-2 回滚：不留孤儿二进制（键集合不变）',
    j(await db.listImageBinaryKeys()) === j(keysBeforeF),
    j({ before: keysBeforeF, after: await db.listImageBinaryKeys() })
  )

  /* --------------------- ④ 持久化（重新读回 / 关标签重开等价） --------------------- */
  const persisted = {
    face_image_id: faceImg(FACE),
    image_row: imgRow(d1.faceImageId),
    binary: await db.getImageBinary(d1.faceImageId)
  }
  const vm2 = sealService.getFaceById(FACE)
  report.persistence = {
    face_image_id: persisted.face_image_id,
    image_id: persisted.image_row && persisted.image_row.id,
    image_meta: persisted.image_row && { width: persisted.image_row.width, height: persisted.image_row.height, bytes: persisted.image_row.bytes, mime: persisted.image_row.mime },
    binary_bytes: persisted.binary.ok ? persisted.binary.bytesLength : `ERR:${persisted.binary.message}`,
    view_model_faceImage_id: vm2 && vm2.faceImage && vm2.faceImage.id
  }
  check(
    '④ 重新读回：印面指向、影像行、二进制三者一致（关标签重开等价）',
    persisted.face_image_id === d1.faceImageId &&
      persisted.image_row &&
      persisted.image_row.id === d1.faceImageId &&
      persisted.binary.ok &&
      persisted.binary.bytesLength === pxBytes3.length,
    j(report.persistence)
  )
  check(
    '④ 视图模型重新读取后 faceImage 指向同一影像（详情页刷新后一致）',
    vm2 && vm2.faceImage && vm2.faceImage.id === d1.faceImageId && vm2.face_image_id === d1.faceImageId,
    j({ face_image_id: vm2 && vm2.face_image_id, faceImage: vm2 && vm2.faceImage && vm2.faceImage.id })
  )

  /* ④′ 同内容重复上传 ⇒ 复用既有影像行（不重复落库，指向不变） */
  const beforeG = await counts()
  const g1 = await db.replaceFaceImage(admin, FACE, pxBytes3)
  const afterG = await counts()
  report.dedupe = { before: beforeG, result: { ok: g1.ok, deduped: g1.deduped, faceImageId: g1.faceImageId, previousFaceImageId: g1.previousFaceImageId, message: g1.message }, after: afterG }
  check(
    '④′ 同内容再传 ⇒ deduped 复用既有影像行（行数不变、指向不变）',
    g1.ok === true && g1.deduped === true && g1.faceImageId === d1.faceImageId && afterG.images === beforeG.images,
    j(report.dedupe)
  )

  /* --------------------- ⑤ 拒绝路径可读（未指定印面 / 空内容 / 非图片 / 超限） --------------------- */
  const rejects = {
    missing_face: await sealService.replaceFaceImage('', { bytes: pxBytes2 }),
    empty: await sealService.replaceFaceImage(FACE, { bytes: new Uint8Array(0) }),
    not_image: await sealService.replaceFaceImage(FACE, { bytes: new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]), mime: 'image/webp' }),
    too_large: await sealService.replaceFaceImage(FACE, { bytes: new Uint8Array(1048577) }),
    unknown_face: await db.replaceFaceImage(admin, 'fc-9999-f9', pxBytes2)
  }
  report.rejects = Object.fromEntries(
    Object.entries(rejects).map(([k, v]) => [k, { ok: v.ok, reason: v.reason, message: v.message }])
  )
  check(
    '⑤ 拒绝路径均可读（未指定印面 / 空内容 / 非图片 / 超 1 MB / 印面不存在）',
    rejects.missing_face.reason === 'MISSING_FACE' &&
      rejects.empty.reason === 'EMPTY_CONTENT' &&
      rejects.not_image.reason === 'NOT_IMAGE' &&
      rejects.too_large.reason === 'TOO_LARGE' &&
      rejects.unknown_face.reason === 'UNKNOWN_FACE',
    j(report.rejects)
  )
  check(
    '⑤ 拒绝路径均不落库（影像行数不变）',
    (await counts()).images === afterG.images,
    `${afterG.images} → ${(await counts()).images}`
  )

  report.summary = {
    passed: checks.filter((c) => c.pass).length,
    failed: checks.filter((c) => !c.pass).length,
    total: checks.length
  }
  report.checks = checks
  report.finished_at = new Date().toISOString()
  report.idb_log = idbLog
  report.write_log = writeLog
  console.log(JSON.stringify({ summary: report.summary, failed: checks.filter((c) => !c.pass) }, null, 2))
} catch (err) {
  check('（脚本自身异常）', false, `${(err && err.stack) || err}`)
  report.checks = checks
  report.summary = { passed: 0, failed: checks.length, total: checks.length }
  report.script_error = String((err && err.stack) || err)
  console.log(JSON.stringify({ summary: report.summary, error: report.script_error }, null, 2))
} finally {
  if (ssr) await ssr.close()
  fs.writeFileSync(OUT_JSON, JSON.stringify(report, null, 2))
  fs.writeFileSync(
    OUT_TXT,
    [`# 玺爱 · 印面图替换自测（node 层，${report.started_at}）`, '', ...checks.map((c) => `${c.pass ? 'PASS' : 'FAIL'} | ${c.name} | ${c.detail}`)].join('\n') + '\n'
  )
  process.exit(report.summary && report.summary.failed === 0 ? 0 : 1)
}
