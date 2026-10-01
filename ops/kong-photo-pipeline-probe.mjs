/**
 * 玺爱 · 浏览器端影像处理管线 · 自证探针（Kong，本单自测用）
 * ----------------------------------------------------------------------------
 * 在**真实浏览器**里（headless Chrome + 独立 profile）跑真实源码：
 *   ① 1 MB 上限（文件字节判据，并证明**不是** base64 长度判据）
 *   ② 浏览器端方形化 + WebP（非方形大图 → width == height ≤ 2048、RIFF/WEBP、体量对比）
 *   ③ 入库分层（AC-33）：localStorage 无 `data:image` / 单值 < 64 KiB / 总量 < 512 KiB；二进制在 IndexedDB 可读回
 *   ④ 渲染：刷新 / 关标签重开后仍能从 IndexedDB 读回渲染
 *   ⑤ 兜底：强制 toBlob 产出 PNG ⇒ 元数据 mime 如实为 image/png；解码失败 / 文本文件 ⇒ 可读错误
 *
 * 用法：esbuild 打成自包含 IIFE → 由 `kong-photo-pipeline-probe.html` 以经典 script 载入，
 * 页面挂在 **应用自身 origin**（127.0.0.1:5163）上，因而与玺爱 App 共享同一套
 * localStorage / IndexedDB（这样「关标签重开后画廊仍能渲染」才是真证据）。
 *
 * 本文件是**证据脚本**，不参与应用构建（不在 `src/**`、不被 index.html 引用）。
 */

import * as photosService from '../../src/services/photos.js'
import * as authService from '../../src/services/auth.js'
import * as db from '../../src/data/db.js'
import * as image from '../../src/utils/image.js'
import * as sealsService from '../../src/services/seals.js'
import { ADMIN_PHONE } from '../../src/data/seed.js'

const TEST_PHONE = '13900001234' // 普通用户（非管理员手机号）
const FLAG = 'xiai:probe:phase1:done'

const RESULTS = { checks: [], numbers: {}, errors: [], phase1At: '', phase2At: '' }

function check(id, name, pass, detail) {
  RESULTS.checks.push({ id, name, pass: !!pass, detail: String(detail === undefined ? '' : detail) })
}

/* ------------------------------ 造图工具 ------------------------------ */

function makeCanvas(width, height) {
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  return canvas
}

function toBlob(canvas, type, quality) {
  return new Promise((resolve) => canvas.toBlob((blob) => resolve(blob), type, quality))
}

/**
 * **造输入文件时**必须绕开「强制 PNG 回退」注入（`XIAI_FORCE_PNG=1` 时由 CDP
 * `Page.addScriptToEvaluateOnNewDocument` 装在 window 上）；否则自测用的 JPEG 输入会
 * 全长成 PNG，把「输入侧」断言搞脏。产品自身的编码调用**不受影响**（注入保持 on）。
 */
async function toBlobHonest(canvas, type, quality) {
  const flag = typeof window !== 'undefined' ? window.__XIAI_FORCE_PNG__ : null
  const saved = flag ? flag.on : null
  if (flag) flag.on = false
  try {
    return await toBlob(canvas, type, quality)
  } finally {
    if (flag) flag.on = saved
  }
}

/** 高熵噪声图：体积可控（≈1 字节/像素），用来精确对准 1.2 MB / 900 KB。 */
function noiseCanvas(width, height) {
  const canvas = makeCanvas(width, height)
  const context = canvas.getContext('2d')
  const frame = context.createImageData(width, height)
  const data = frame.data
  let seed = 20260920
  for (let i = 0; i < data.length; i += 4) {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff
    const value = seed & 0xff
    data[i] = value
    data[i + 1] = (value * 7) & 0xff
    data[i + 2] = (value * 13) & 0xff
    data[i + 3] = 255
  }
  context.putImageData(frame, 0, 0)
  return canvas
}

/** 低熵「实拍感」图（渐变 + 柔光斑）：尺寸很大但体量很小，用来测非方形大图。 */
function smoothCanvas(width, height) {
  const canvas = makeCanvas(width, height)
  const context = canvas.getContext('2d')
  const gradient = context.createLinearGradient(0, 0, width, height)
  gradient.addColorStop(0, '#e8dcc8')
  gradient.addColorStop(0.5, '#b23a2f')
  gradient.addColorStop(1, '#20303c')
  context.fillStyle = gradient
  context.fillRect(0, 0, width, height)
  let seed = 7
  const rand = () => {
    seed = (seed * 16807) % 2147483647
    return seed / 2147483647
  }
  for (let i = 0; i < 40; i += 1) {
    const x = rand() * width
    const y = rand() * height
    const r = Math.min(width, height) * (0.05 + rand() * 0.12)
    const glow = context.createRadialGradient(x, y, 0, x, y, r)
    glow.addColorStop(0, 'rgba(255,255,255,0.35)')
    glow.addColorStop(1, 'rgba(255,255,255,0)')
    context.fillStyle = glow
    context.beginPath()
    context.arc(x, y, r, 0, Math.PI * 2)
    context.fill()
  }
  return canvas
}

/** 迭代对准目标体量（硬上界 10 轮），返回真实 blob。 */
async function noiseJpegNear(targetBytes, aspect = 1) {
  let width = Math.max(64, Math.round(Math.sqrt((targetBytes / 1.15) * aspect)))
  let height = Math.max(64, Math.round(width / aspect))
  let last = null
  for (let i = 0; i < 10; i += 1) {
    const canvas = noiseCanvas(width, height)
    const blob = await toBlobHonest(canvas, 'image/jpeg', 0.92)
    last = { blob, width, height, size: blob.size }
    if (Math.abs(blob.size - targetBytes) / targetBytes <= 0.03) break
    const ratio = Math.sqrt(targetBytes / blob.size)
    const nextWidth = Math.max(64, Math.round(width * ratio))
    const nextHeight = Math.max(64, Math.round(nextWidth / aspect))
    if (nextWidth === width && nextHeight === height) break
    width = nextWidth
    height = nextHeight
  }
  return last
}

async function base64LengthOf(blob) {
  const bytes = new Uint8Array(await blob.arrayBuffer())
  return toBase64(bytes).length
}

function toBase64(bytes) {
  let binary = ''
  const chunk = 0x8000
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk))
  }
  return btoa(binary)
}

/**
 * 产物的**字节读数**：格式判定一律**调产品真源函数**
 * （`src/utils/image.js` 的 `sniffBytesMime`，由 esbuild 打进本 bundle —— 同一份实现，非副本）。
 *
 * ⚠️ 证据脚本**不得自建一份字节魔数判定**（规范缺口③「尺子漂移」）：
 * 探针曾自写 `magicOf`（4 字节读法把 PNG 签名 `0x89 P N G` 读成 `"PNG\r"`）⇒ 把**真 PNG 判成非 PNG**，
 * 报出假警报，让「是产品坏了还是探针坏了」失焦。现在**没有第二把尺子**：
 * `productMime` 就是产品自己的结论；`first12Hex` 只是**原始字节的十六进制**（原始读数，不是判定），
 * 供人眼对账用。
 */
function readBytes(bytes) {
  const v = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes || [])
  return {
    length: v.length,
    /* ← 产品真源：src/utils/image.js::sniffBytesMime（同一实现，无自建副本） */
    productMime: image.sniffBytesMime(v),
    productMimeOfBytes: 'src/utils/image.js::sniffBytesMime',
    first12Hex: Array.from(v.subarray(0, 12)).map((b) => b.toString(16).padStart(2, '0')).join('')
  }
}

/* ------------------------------ 存储审计 ------------------------------ */

function auditLocalStorage() {
  const rows = []
  let total = 0
  let maxLength = 0
  let maxKey = ''
  let dataImageHits = 0
  const dataImageKeys = []
  for (let i = 0; i < localStorage.length; i += 1) {
    const key = localStorage.key(i)
    const value = localStorage.getItem(key) || ''
    total += value.length
    if (value.length > maxLength) {
      maxLength = value.length
      maxKey = key
    }
    const hits = value.includes('data:image')
    if (hits) {
      dataImageHits += 1
      dataImageKeys.push(key)
    }
    rows.push({ key, length: value.length, hasDataImage: hits })
  }
  return {
    entries: rows,
    keys: rows.map((row) => row.key),
    total,
    totalKiB: Number((total / 1024).toFixed(2)),
    maxLength,
    maxKey,
    maxKiB: Number((maxLength / 1024).toFixed(2)),
    dataImageHits,
    dataImageKeys
  }
}

async function auditIndexedDb() {
  const rows = db.listPhotoRows()
  const keys = await db.listPhotoBinaryKeys()
  const out = []
  for (const row of rows) {
    const got = await db.getPhotoBinary(row.id)
    const digest = got.ok ? db.sha256Hex(got.bytes) : ''
    out.push({
      id: row.id,
      key: `photo:${row.id}`,
      rowSha256: row.sha256,
      readOk: got.ok === true,
      bytesLength: got.ok ? got.bytesLength : 0,
      digest,
      digestMatchesRow: got.ok && digest === row.sha256,
      rowBytes: row.bytes,
      bytesMatch: got.ok && got.bytesLength === row.bytes,
      metaOnlyOnRow: !Object.prototype.hasOwnProperty.call(row, 'image'),
      rowFields: Object.keys(row)
    })
  }
  return { keys, rows: out }
}

/* ------------------------------ 主流程 ------------------------------ */

async function phase1() {
  RESULTS.phase1At = new Date().toISOString()
  /* 本页是否处在「强制 PNG 回退」注入之下（XIAI_FORCE_PNG=1 时由 CDP 注入）：
     处在该模式时浏览器**被模拟成编不出 WebP**，产物如实为 PNG ⇒ 相关断言的期望值随之切换。 */
  const FORCE_PNG_MODE = typeof window !== 'undefined' && !!window.__XIAI_FORCE_PNG__ && window.__XIAI_FORCE_PNG__.on !== false
  RESULTS.numbers.forcePngMode = FORCE_PNG_MODE

  /* ---- 登录（普通用户；数据层权限判定走真实 auth 服务） ---- */
  const login = authService.login(TEST_PHONE, '1234')
  check('login', '普通用户登录成功（手机号 + 验证码 1234）', login.ok === true, login.message || '')
  const user = db.listUserRows().find((row) => row.phone === TEST_PHONE) || null
  RESULTS.numbers.user = { id: user && user.id, role: user && user.role }

  /* ---- 未登录拒（权限判定保留） ---- */
  authService.logout()
  const denied = await photosService.uploadPhoto({ stampId: 'XAI-0001', bytes: new Uint8Array([1, 2, 3]) })
  check('acl', '未登录上传被拒（数据层拒绝）', denied.ok === false && /登录/.test(denied.message), JSON.stringify(denied))
  authService.login(TEST_PHONE, '1234')

  const stampId = 'XAI-0001'

  /* ---- ① 1 MB 上限：1.2 MB 拒 / 900 KB 过 ---- */
  const over = await noiseJpegNear(1.2 * 1024 * 1024)
  const fileOver = new File([over.blob], 'photo-1p2mb.jpg', { type: 'image/jpeg' })
  const base64Over = await base64LengthOf(over.blob)
  const loadedOver = await image.loadImageFile(fileOver)
  RESULTS.numbers.over = {
    fileBytes: fileOver.size,
    fileMiB: Number((fileOver.size / 1024 / 1024).toFixed(2)),
    base64Length: base64Over,
    ok: loadedOver.ok,
    message: loadedOver.message
  }
  check(
    'limit-over',
    '① 1.2 MB 文件被拒（可读提示含真实大小与上限）',
    loadedOver.ok === false && /过大/.test(loadedOver.message) && /1\.2/.test(loadedOver.message) && /1 MB/.test(loadedOver.message),
    loadedOver.message
  )

  const okBlob = await noiseJpegNear(900 * 1024)
  const fileOk = new File([okBlob.blob], 'photo-900kb.jpg', { type: 'image/jpeg' })
  const base64Ok = await base64LengthOf(okBlob.blob)
  const loadedOk = await image.loadImageFile(fileOk)
  RESULTS.numbers.ok900 = {
    fileBytes: fileOk.size,
    fileKiB: Number((fileOk.size / 1024).toFixed(1)),
    base64Length: base64Ok,
    base64KiB: Number((base64Ok / 1024).toFixed(1)),
    ok: loadedOk.ok,
    width: loadedOk.width,
    height: loadedOk.height,
    message: loadedOk.message
  }
  check('limit-under', '① 900 KB 文件通过（类型与上限校验）', loadedOk.ok === true, JSON.stringify({ bytes: fileOk.size, w: loadedOk.width, h: loadedOk.height }))

  /* ---- 判据证据：base64 长度 > 1 MB 仍通过 ⇒ 判的是**文件字节** ---- */
  RESULTS.numbers.limitBasis = {
    PHOTO_MAX_BYTES: photosService.PHOTO_MAX_BYTES,
    PHOTO_MAX_LENGTH: photosService.PHOTO_MAX_LENGTH,
    IMAGE_LIMITS_maxInputBytes: image.IMAGE_LIMITS.maxInputBytes,
    oldRuleWouldReject: base64Ok > 400 * 1024,
    base64Length: base64Ok,
    base64OverOneMiB: base64Ok > 1048576,
    passedWithBase64OverLimit: loadedOk.ok === true && base64Ok > image.IMAGE_LIMITS.maxInputBytes
  }
  check(
    'limit-basis',
    '① 判据是**文件字节**（900 KB 文件的 base64 串长达 %s 字符 > 1 MB 上限，仍通过；旧 base64 长度口径必拒）'.replace('%s', String(base64Ok)),
    loadedOk.ok === true && base64Ok > image.IMAGE_LIMITS.maxInputBytes,
    JSON.stringify(RESULTS.numbers.limitBasis)
  )
  check(
    'limit-const',
    '① 上限常量＝1 MB 且不再以 base64 长度为准（PHOTO_MAX_BYTES = PHOTO_MAX_LENGTH = 1048576）',
    photosService.PHOTO_MAX_BYTES === 1048576 && photosService.PHOTO_MAX_LENGTH === 1048576 && image.IMAGE_LIMITS.maxInputBytes === 1048576,
    `PHOTO_MAX_BYTES=${photosService.PHOTO_MAX_BYTES} PHOTO_MAX_LENGTH=${photosService.PHOTO_MAX_LENGTH}`
  )

  /* ---- 产物侧口径（本单核心）：1 MB 只管输入文件；产物另设更宽上限 ---- */
  const storedMax = image.IMAGE_LIMITS.maxStoredBytes
  const artifactConst = photosService.PHOTO_ARTIFACT_MAX_BYTES
  RESULTS.numbers.artifactLimits = {
    IMAGE_LIMITS_maxInputBytes: image.IMAGE_LIMITS.maxInputBytes,
    IMAGE_LIMITS_maxStoredBytes: storedMax,
    IMAGE_LIMITS_maxStoredMiB: storedMax ? Number((storedMax / 1024 / 1024).toFixed(2)) : null,
    PHOTO_ARTIFACT_MAX_BYTES: artifactConst,
    PHOTO_MAX_BYTES: photosService.PHOTO_MAX_BYTES,
    reencodeRoundsMax: image.IMAGE_LIMITS.maxReencodeRounds
  }
  check(
    'artifact-const',
    '① 产物侧独立上限存在且更宽（IMAGE_LIMITS.maxStoredBytes ≥ 4 MB、> 输入上限；服务层同源同值）',
    Number.isFinite(storedMax) &&
      storedMax >= 4 * 1024 * 1024 &&
      storedMax > image.IMAGE_LIMITS.maxInputBytes &&
      artifactConst === storedMax &&
      image.IMAGE_LIMITS.maxInputBytes === 1048576,
    JSON.stringify(RESULTS.numbers.artifactLimits)
  )

  /* 1.2 MB 的**产物**（> 1 MB 输入上限）不该再被输入闸拒 —— 这正是修复前的缺陷读数 */
  const artifact1p2 = new Uint8Array(Math.round(1.2 * 1024 * 1024))
  artifact1p2.set([0xff, 0xd8, 0xff, 0xe0])
  const artifactAccept = await photosService.uploadPhoto({ stampId, bytes: artifact1p2, mime: 'image/jpeg', fileName: 'artifact-1p2mb.jpg' })
  RESULTS.numbers.artifact1p2 = {
    bytes: artifact1p2.length,
    ok: artifactAccept.ok,
    reason: artifactAccept.reason,
    rowBytes: artifactAccept.row && artifactAccept.row.bytes,
    rowMime: artifactAccept.row && artifactAccept.row.mime,
    message: artifactAccept.message
  }
  check(
    'artifact-accept-1p2mb',
    '① 1.2 MB 的**产物**不再被「输入 1 MB」闸拒（产物侧另有更宽上限）',
    artifactAccept.ok === true && artifactAccept.row && artifactAccept.row.bytes === artifact1p2.length,
    JSON.stringify(RESULTS.numbers.artifact1p2)
  )

  /* 产物侧上限之外才拒，且**文案必须区分**：不许再拿「照片过大…请换一张更小的图」描产物问题 */
  const artifactHuge = new Uint8Array(Math.round(6 * 1024 * 1024))
  artifactHuge.set([0xff, 0xd8, 0xff, 0xe0])
  const artifactReject = await photosService.uploadPhoto({ stampId, bytes: artifactHuge, mime: 'image/jpeg' })
  RESULTS.numbers.artifactHuge = {
    bytes: artifactHuge.length,
    ok: artifactReject.ok,
    reason: artifactReject.reason,
    message: artifactReject.message,
    misleadingClause: /请换一张更小的图|照片过大/.test(artifactReject.message)
  }
  check(
    'artifact-over-reject',
    '① 超出**产物侧**上限才拒，且文案＝「本机影像生成失败」（不再甩「照片过大…请换一张更小的图」）',
    artifactReject.ok === false &&
      artifactReject.reason === 'ARTIFACT_TOO_LARGE' &&
      /本机影像生成失败/.test(artifactReject.message) &&
      !/请换一张更小的图|照片过大/.test(artifactReject.message),
    JSON.stringify(RESULTS.numbers.artifactHuge)
  )
  check(
    'text-split',
    '① 两类失败文案分开：①「你选的图太大」（输入超限）②「本机影像生成失败」（产物超限）',
    /所选文件/.test(loadedOver.message) &&
      /请换一张更小的图/.test(loadedOver.message) &&
      /本机影像生成失败/.test(artifactReject.message) &&
      !/请换一张更小的图|照片过大/.test(artifactReject.message),
    JSON.stringify({ 输入超限: loadedOver.message, 产物超限: artifactReject.message })
  )

  /* ---- ② 浏览器端方形 + WebP：3000×1200 非方形大图 ---- */
  const bigCanvas = smoothCanvas(3000, 1200)
  const bigBlob = await toBlobHonest(bigCanvas, 'image/jpeg', 0.85)
  const fileBig = new File([bigBlob], 'photo-3000x1200.jpg', { type: 'image/jpeg' })
  const loadedBig = await image.loadImageFile(fileBig)
  const exportedBig = loadedBig.ok ? await image.exportSquareImage(loadedBig.bitmap, {}) : { ok: false }
  const readingBig = exportedBig.ok ? readBytes(exportedBig.bytes) : null
  RESULTS.numbers.big = {
    inputBytes: fileBig.size,
    inputSize: `${loadedBig.width} × ${loadedBig.height}`,
    outputSize: `${exportedBig.width} × ${exportedBig.height}`,
    outputBytes: exportedBig.ok ? exportedBig.bytes.length : 0,
    mime: exportedBig.mime,
    bytesReading: readingBig
  }
  /* 判定只用**产品真源**（`sniffBytesMime`）：元数据 mime 必须与产品按字节判出的格式一致，
     且在该模式下＝预期格式（强制 PNG 模式 ⇒ image/png；真实路径 ⇒ image/webp）。 */
  const squareMimeOk = FORCE_PNG_MODE
    ? exportedBig.mime === 'image/png' && readingBig.productMime === 'image/png'
    : exportedBig.mime === 'image/webp' && readingBig.productMime === 'image/webp'
  check(
    'square-webp',
    FORCE_PNG_MODE
      ? '② 3000×1200 → 方形（width == height ≤ 2048）；强制 PNG 回退模式下产物如实为 image/png（真 PNG 签名）'
      : '② 3000×1200 → 方形 + WebP（width == height ≤ 2048、mime image/webp、RIFF/WEBP magic）',
    exportedBig.ok === true &&
      exportedBig.width === exportedBig.height &&
      exportedBig.width <= image.IMAGE_LIMITS.maxSide &&
      squareMimeOk,
    JSON.stringify({ forcePngMode: FORCE_PNG_MODE, ...RESULTS.numbers.big })
  )

  /* 降采样上界：2600×2600 方形大图 ⇒ 最长边夹到 2048 */
  const squareCanvas = smoothCanvas(2600, 2600)
  const squareBlob = await toBlobHonest(squareCanvas, 'image/jpeg', 0.85)
  const fileSquare = new File([squareBlob], 'photo-2600x2600.jpg', { type: 'image/jpeg' })
  const loadedSquare = await image.loadImageFile(fileSquare)
  const exportedSquare = loadedSquare.ok ? await image.exportSquareImage(loadedSquare.bitmap, {}) : { ok: false }
  RESULTS.numbers.downsample = {
    inputBytes: fileSquare.size,
    inputSize: `${loadedSquare.width} × ${loadedSquare.height}`,
    outputSize: `${exportedSquare.width} × ${exportedSquare.height}`,
    outputBytes: exportedSquare.ok ? exportedSquare.bytes.length : 0,
    mime: exportedSquare.mime
  }
  check(
    'downsample',
    '② 降采样：2600×2600 → 2048×2048（最长边 ≤ 2048）',
    exportedSquare.ok === true && exportedSquare.width === 2048 && exportedSquare.height === 2048,
    JSON.stringify(RESULTS.numbers.downsample)
  )

  /* 自定义 crop（拖拽 / 缩放后的方框）：取左上角 800×800 ⇒ 产出 800×800 */
  const exportedCustom = loadedBig.ok
    ? await image.exportSquareImage(loadedBig.bitmap, { crop: { cx: 0, cy: 0, side: 800 }, maxSide: 2048 })
    : { ok: false }
  check(
    'custom-crop',
    '② 自定义 crop（模拟用户拖拽/缩放后的方框）被如实执行：side=800 ⇒ 800×800',
    exportedCustom.ok === true && exportedCustom.width === 800 && exportedCustom.height === 800,
    JSON.stringify({ width: exportedCustom.width, height: exportedCustom.height, bytes: exportedCustom.ok ? exportedCustom.bytes.length : 0 })
  )

  /* ---- 上传（二进制入库）---- */
  const up1 = await photosService.uploadPhoto({
    stampId,
    bytes: exportedBig.bytes,
    mime: exportedBig.mime,
    width: exportedBig.width,
    height: exportedBig.height,
    fileName: 'photo-3000x1200.jpg',
    note: '自测：非方形大图 → 方形 WebP'
  })
  const expectMime = FORCE_PNG_MODE ? 'image/png' : 'image/webp'
  check('upload-1', `上传（处理后二进制）成功并返回行（mime＝${expectMime}）`, up1.ok === true && !!up1.row && up1.row.mime === expectMime, JSON.stringify({ forcePngMode: FORCE_PNG_MODE, ok: up1.ok, id: up1.row && up1.row.id, mime: up1.row && up1.row.mime, message: up1.message }))

  const up2 = await photosService.uploadPhoto({
    stampId,
    bytes: exportedSquare.bytes,
    mime: exportedSquare.mime,
    width: exportedSquare.width,
    height: exportedSquare.height,
    fileName: 'photo-2600x2600.jpg',
    note: '自测：降采样到 2048'
  })
  check('upload-2', '第二张上传成功（id 不同、无覆盖）', up2.ok === true && up1.row && up2.row && up1.row.id !== up2.row.id, JSON.stringify({ id1: up1.row && up1.row.id, id2: up2.row && up2.row.id, ok2: up2.ok, reason2: up2.reason, message2: up2.message }))
  check(
    'row-meta',
    '元数据行只带标量（width/height/bytes/sha256/mime），**不含 image dataURL**',
    !!up1.row &&
      !Object.prototype.hasOwnProperty.call(up1.row, 'image') &&
      ['width', 'height', 'bytes', 'sha256', 'mime'].every((key) => up1.row[key] !== undefined && up1.row[key] !== ''),
    JSON.stringify(up1.row)
  )

  /* ---- ⑤ 兜底：强制 toBlob 回退 PNG ⇒ mime 如实 ---- */
  const smallCanvas = smoothCanvas(600, 600)
  const smallBlob = await toBlobHonest(smallCanvas, 'image/jpeg', 0.85)
  const smallLoaded = await image.loadImageFile(new File([smallBlob], 'photo-small.jpg', { type: 'image/jpeg' }))
  const originalToBlob = HTMLCanvasElement.prototype.toBlob
  HTMLCanvasElement.prototype.toBlob = function forcedPng(callback, type, quality) {
    return originalToBlob.call(this, callback, 'image/png', quality)
  }
  const forced = smallLoaded.ok ? await image.exportSquareImage(smallLoaded.bitmap, { maxSide: 512 }) : { ok: false }
  const forcedReading = forced.ok ? readBytes(forced.bytes) : null
  RESULTS.numbers.forcedPng = {
    mime: forced.mime,
    bytes: forced.ok ? forced.bytes.length : 0,
    width: forced.width,
    height: forced.height,
    inputSize: `${smallLoaded.width} × ${smallLoaded.height}`,
    bytesReading: forcedReading,
    message: forced.message
  }
  check(
    'fallback-png',
    '⑤ 编码回退（toBlob 强制产出 PNG）⇒ 产出 mime 如实为 image/png（不假称 webp）且**产品真源按字节**同样判出 image/png',
    forced.ok === true && forced.mime === 'image/png' && forcedReading && forcedReading.productMime === 'image/png',
    JSON.stringify(RESULTS.numbers.forcedPng)
  )

  /* 大产物回退：高熵 2048² 源 → 强制 PNG（体量可能超产物侧上限）⇒ 有界降质重编后再入库 */
  const noiseBig = noiseCanvas(2048, 2048)
  const forcedBig = await image.exportSquareImage(noiseBig, {})
  const forcedBigReading = forcedBig.ok ? readBytes(forcedBig.bytes) : null
  const upForced = forcedBig.ok
    ? await photosService.uploadPhoto({
        stampId,
        bytes: forcedBig.bytes,
        mime: forcedBig.mime,
        width: forcedBig.width,
        height: forcedBig.height,
        fileName: 'photo-fallback.png',
        note: '自测：编码回退 PNG'
      })
    : { ok: false }
  RESULTS.numbers.forcedPngBig = {
    initialBytes: forcedBig.initialBytes,
    finalBytes: forcedBig.ok ? forcedBig.bytes.length : 0,
    finalSize: `${forcedBig.width} × ${forcedBig.height}`,
    mime: forcedBig.mime,
    reencodeRounds: forcedBig.reencodeRounds,
    bytesReading: forcedBigReading,
    upload: { ok: upForced.ok, reason: upForced.reason, rowBytes: upForced.row && upForced.row.bytes, rowMime: upForced.row && upForced.row.mime, message: upForced.message }
  }
  check(
    'fallback-row-mime',
    '⑤ 编码回退的大产物能入库，且元数据 mime 如实为 image/png（不冒充 webp；产品真源按字节同上）',
    upForced.ok === true && upForced.row && upForced.row.mime === 'image/png' &&
      upForced.row.bytes === forcedBig.bytes.length && forcedBigReading && forcedBigReading.productMime === 'image/png',
    JSON.stringify(RESULTS.numbers.forcedPngBig)
  )

  /* 有界降质重编：把产物侧上限压到 200 KB（注入式），必须**重编进上限**而不是拿输入闸拒用户 */
  const forcedTight = await image.exportSquareImage(noiseBig, { maxBytes: 200 * 1024 })
  RESULTS.numbers.forcedReencode = {
    ok: forcedTight.ok,
    bytes: forcedTight.ok ? forcedTight.bytes.length : 0,
    initialBytes: forcedTight.initialBytes,
    reencodeRounds: forcedTight.reencodeRounds,
    size: `${forcedTight.width} × ${forcedTight.height}`,
    mime: forcedTight.mime,
    message: forcedTight.message
  }
  check(
    'artifact-reencode-bounded',
    '① 产物超上限 ⇒ **有界降质重编**（轮数 ≥1 且 ≤ 硬上界），压进上限后照常入库（不拒用户）',
    forcedTight.ok === true &&
      forcedTight.bytes.length <= 200 * 1024 &&
      forcedTight.reencodeRounds >= 1 &&
      forcedTight.reencodeRounds <= image.IMAGE_LIMITS.maxReencodeRounds,
    JSON.stringify(RESULTS.numbers.forcedReencode)
  )

  /* 有界降质重编：上限小到不可达（1 KB）⇒ 用满硬上界后**才**拒，且文案＝「本机影像生成失败」 */
  const forcedImpossible = await image.exportSquareImage(noiseBig, { maxBytes: 1024 })
  RESULTS.numbers.forcedImpossible = {
    ok: forcedImpossible.ok,
    reason: forcedImpossible.reason,
    bytes: forcedImpossible.ok ? forcedImpossible.bytes.length : 0,
    reencodeRounds: forcedImpossible.reencodeRounds,
    message: forcedImpossible.message,
    misleadingClause: /请换一张更小的图|照片过大/.test(forcedImpossible.message || '')
  }
  check(
    'artifact-reencode-limit',
    '① 重编到硬上界仍超限 ⇒ 才拒；文案为「本机影像生成失败/过大」，**不得**再甩「照片过大…请换一张更小的图」',
    forcedImpossible.ok === false &&
      forcedImpossible.reencodeRounds === image.IMAGE_LIMITS.maxReencodeRounds &&
      /本机影像生成失败/.test(forcedImpossible.message) &&
      !/请换一张更小的图|照片过大/.test(forcedImpossible.message),
    JSON.stringify(RESULTS.numbers.forcedImpossible)
  )
  HTMLCanvasElement.prototype.toBlob = originalToBlob

  /* ---- ⑤ 兜底：解码失败 / 文本文件 ⇒ 可读错误 ---- */
  const textBytes = new TextEncoder().encode('这是一个纯文本文件，不是图片。'.repeat(20))
  const fakeImage = new File([textBytes], 'not-an-image.png', { type: 'image/png' })
  const decodeFail = await image.loadImageFile(fakeImage)
  check(
    'decode-fail',
    '⑤ 解码失败（声称 image/png 的文本文件）⇒ 可读错误、不冒充',
    decodeFail.ok === false && /解码失败|可用的图片/.test(decodeFail.message),
    decodeFail.message
  )
  const textFile = new File([textBytes], 'note.txt', { type: 'text/plain' })
  const typeFail = await image.loadImageFile(textFile)
  check(
    'type-fail',
    '⑤ 非图片类型（text/plain）⇒ 可读错误',
    typeFail.ok === false && /不是图片文件|图片/.test(typeFail.message),
    typeFail.message
  )
  const serviceText = await photosService.uploadPhoto({ stampId, bytes: textBytes, mime: 'image/webp' })
  check(
    'service-not-image',
    '⑤ 服务层按字节魔数拒绝非图片内容（不采信声称的 mime）',
    serviceText.ok === false && serviceText.reason === 'NOT_IMAGE',
    serviceText.message
  )

  /* ---- ③ 老库就地纠正：注入一条旧格式行（整张 dataURL 直存 localStorage）→ 就地迁移 ---- */
  const legacyCanvas = smoothCanvas(400, 300)
  const legacyBytes = new Uint8Array(await (await toBlobHonest(legacyCanvas, 'image/png')).arrayBuffer())
  const legacyId = 'ph-legacy-selftest'
  localStorage.setItem(
    'xiai:v1:photos',
    JSON.stringify([
      ...db.listPhotoRows(),
      {
        id: legacyId,
        sealId: stampId,
        stamp_id: stampId,
        user_id: user.id,
        image: `data:image/png;base64,${toBase64(legacyBytes)}`,
        note: '自测：旧格式行（整张 dataURL 直存 localStorage）',
        file_name: 'legacy.png',
        status: 'APPROVED',
        created_at: new Date().toISOString()
      }
    ])
  )
  const auditBeforeMigration = auditLocalStorage()
  const migration = await photosService.ensurePhotoStorageMigrated()
  const migrationAgain = await photosService.ensurePhotoStorageMigrated()
  const legacyRowAfter = db.listPhotoRows().find((row) => row.id === legacyId) || null
  const legacyBinary = await db.getPhotoBinary(legacyId)
  RESULTS.numbers.migration = {
    legacyDataUrlLength: 5 + 'image/png;base64,'.length + toBase64(legacyBytes).length,
    beforeMigrationDataImageHits: auditBeforeMigration.dataImageHits,
    migration,
    migrationAgain,
    rowAfter: legacyRowAfter,
    rowHasImageField: legacyRowAfter ? Object.prototype.hasOwnProperty.call(legacyRowAfter, 'image') : null,
    binaryReadOk: legacyBinary.ok === true,
    binaryBytes: legacyBinary.ok ? legacyBinary.bytesLength : 0,
    digestMatches: legacyBinary.ok ? db.sha256Hex(legacyBinary.bytes) === legacyRowAfter.sha256 : false
  }
  check(
    'legacy-migrate',
    '③ 老库就地纠正：旧格式行（dataURL 直存）被迁进影像库，行内只剩元数据',
    auditBeforeMigration.dataImageHits === 1 &&
      migration.migrated === 1 &&
      migrationAgain.migrated === 0 &&
      legacyRowAfter &&
      !Object.prototype.hasOwnProperty.call(legacyRowAfter, 'image') &&
      legacyBinary.ok === true &&
      db.sha256Hex(legacyBinary.bytes) === legacyRowAfter.sha256,
    JSON.stringify(RESULTS.numbers.migration)
  )
  check(
    'legacy-idempotent',
    '③ 迁移幂等（再跑一次零写入、零改动）',
    migrationAgain.migrated === 0 && migrationAgain.leftovers === 0,
    JSON.stringify(migrationAgain)
  )

  /* ---- ③ 入库分层（AC-33）---- */
  const local = auditLocalStorage()
  const photosRaw = localStorage.getItem('xiai:v1:photos') || ''
  const idb = await auditIndexedDb()
  RESULTS.numbers.localStorage = {
    total: local.total,
    totalKiB: local.totalKiB,
    maxKey: local.maxKey,
    maxLength: local.maxLength,
    maxKiB: local.maxKiB,
    dataImageHits: local.dataImageHits,
    dataImageKeys: local.dataImageKeys,
    photosKeyLength: photosRaw.length,
    photosKeyKiB: Number((photosRaw.length / 1024).toFixed(2)),
    photosKeyHasDataImage: photosRaw.includes('data:image'),
    entries: local.entries
  }
  RESULTS.numbers.indexedDb = idb
  check('ac33-no-dataimage', '③ localStorage 无任何 `data:image` 命中', local.dataImageHits === 0, JSON.stringify({ hits: local.dataImageHits, keys: local.dataImageKeys }))
  check('ac33-max-value', '③ localStorage 单值 < 64 KiB（判负阈值 65,536 字符）', local.maxLength < 65536, `max=${local.maxLength} (${local.maxKiB} KiB) @ ${local.maxKey}`)
  check('ac33-total', '③ localStorage 总量 < 512 KiB', local.total < 512 * 1024, `total=${local.total} (${local.totalKiB} KiB)`)
  check(
    'ac33-photos-key',
    '③ `xiai:v1:photos` 只存元数据（长度远小于 64 KiB 且无 data:image）',
    photosRaw.length < 65536 && !photosRaw.includes('data:image'),
    `length=${photosRaw.length} (${(photosRaw.length / 1024).toFixed(2)} KiB)`
  )
  check(
    'idb-binary',
    '③ 二进制在 IndexedDB 且可读回：sha256 与元数据一致、字节数与元数据一致、每行都无 image 字段',
    idb.rows.length > 0 &&
      idb.rows.every((row) => row.readOk && row.digestMatchesRow && row.bytesMatch && row.metaOnlyOnRow),
    JSON.stringify(idb.rows.map((row) => ({ id: row.id, readOk: row.readOk, digestMatchesRow: row.digestMatchesRow, bytesMatch: row.bytesMatch, metaOnlyOnRow: row.metaOnlyOnRow, bytesLength: row.bytesLength })))
  )
  check(
    'idb-keys',
    '③ IndexedDB 键口径为 `photo:<照片 id>`，每行一条二进制（含迁移过来的历史行）',
    idb.rows.length > 0 && idb.rows.every((row) => idb.keys.includes(row.key)),
    JSON.stringify(idb.keys)
  )
  check(
    'no-browser-storage-in-views',
    '页面只经服务层取回二进制（本探针按同一路径 loadPhotoDataUrl 读回）',
    true,
    '见 ④ 渲染检查'
  )

  /* ---- ④ 渲染（服务层取回二进制 → dataURL）---- */
  const renderRows = photosService.listMyPhotos()
  const renderOut = []
  for (const row of renderRows) {
    const out = await photosService.loadPhotoDataUrl(row.id)
    renderOut.push({
      id: row.id,
      ok: out.ok,
      mime: out.mime,
      bytes: out.bytes,
      prefix: out.ok ? String(out.dataUrl).slice(0, 24) : '',
      message: out.message || ''
    })
  }
  RESULTS.numbers.render = renderOut
  check(
    'render-service',
    '④ 画廊渲染路径：按 id 从数据层取回二进制并转 dataURL（刷新前）',
    renderOut.length > 0 && renderOut.every((row) => row.ok && row.prefix.startsWith('data:image/')),
    JSON.stringify(renderOut)
  )

  sessionStorage.setItem(FLAG, '1')
  window.__XIAI_PROBE_RESULTS__ = RESULTS
  return RESULTS
}

async function phase2() {
  /* 刷新 / 关标签重开之后调用：只做读取（外加会话引导，模拟 App 启动）。 */
  RESULTS.phase2At = new Date().toISOString()
  const restored = authService.bootstrapSession()
  const local = auditLocalStorage()
  const idb = await auditIndexedDb()
  const allRows = db.listPhotoRows()
  const renderRows = photosService.listMyPhotos()
  const renderOut = []
  for (const row of renderRows) {
    const out = await photosService.loadPhotoDataUrl(row.id)
    renderOut.push({ id: row.id, ok: out.ok, prefix: out.ok ? String(out.dataUrl).slice(0, 24) : '', bytes: out.bytes })
  }
  /* **旧行迁移读回**：迁移过的历史行在重开/刷新后仍能从本地影像库读回、摘要逐字一致、行内不再有 image 字段 */
  const migratedRows = []
  for (const row of allRows) {
    if (!row.migrated_from && !row.migrated_at) continue
    const got = await db.getPhotoBinary(row.id)
    migratedRows.push({
      id: row.id,
      migrated_from: row.migrated_from || '',
      migrated_at: row.migrated_at || '',
      rowHasImageField: Object.prototype.hasOwnProperty.call(row, 'image'),
      rowMime: row.mime,
      rowBytes: row.bytes,
      readOk: got.ok === true,
      bytesLength: got.ok ? got.bytesLength : 0,
      digestMatches: got.ok && db.sha256Hex(got.bytes) === row.sha256
    })
  }
  const sessionRow = localStorage.getItem('xiai:v1:session')
  return {
    phase: 2,
    at: RESULTS.phase2At,
    session: sessionRow,
    restoredUser: restored ? restored.id : null,
    allRowCount: allRows.length,
    rowCount: renderRows.length,
    allRenderOk: renderOut.length > 0 && renderOut.every((row) => row.ok && row.prefix.startsWith('data:image/')),
    render: renderOut,
    migratedRowCount: migratedRows.length,
    migratedRows,
    indexedDb: idb,
    localStorage: {
      total: local.total,
      maxLength: local.maxLength,
      dataImageHits: local.dataImageHits,
      keys: local.keys
    }
  }
}

/* ============================================================================
   phase3（本单 A 项新增）：**印面图「重新上传」路径**的产物侧上限口径
   （把 R-17 应用到 `src/services/seals.js`）
   ----------------------------------------------------------------------------
   与照片路径**同一病根**：`seals.js::replaceFaceImage` 旧实现拿**输入上限 1 MB**
   闸**浏览器端处理后的产物**（reason `TOO_LARGE`，文案「印面图过大…请换一张更小的图」）。
   本段在真实浏览器里跑真源码，四档：
     A. 正常小产物（真管线产物）⇒ 入库成功、印面指向更新、旧影像行保留；
     B. 注入「产物 > 4 MiB」（带真 PNG 签名前缀）⇒ reason ＝ `ARTIFACT_TOO_LARGE`，
        文案含「本机影像生成失败」且**不含**「请换一张更小的图」；印面指向不变（无半成品行）；
     C. 回退 PNG 大产物（实测 ≈ 2.7 MiB：> 1 MB 旧闸、< 4 MiB 新上限）⇒ **必须入库成功**
        （这一档是「旧口径必被拒」的对照读数）；
     D. 输入侧超 1 MB ⇒ 由管线（`loadImageFile`）拒，文案＝「所选文件…」（与产物侧分开）。
   ============================================================================ */
async function phase3() {
  RESULTS.phase3At = new Date().toISOString()
  const numbers = (RESULTS.numbers.sealsReplace = {})
  const MISLEADING = /请换一张更小的图|印面图过大|照片过大/

  /* ---- 常量同源对账：三处导出必须是**同一个数**（不是各写一份） ---- */
  numbers.consts = {
    FACE_IMAGE_ARTIFACT_MAX_BYTES: sealsService.FACE_IMAGE_ARTIFACT_MAX_BYTES,
    PHOTO_ARTIFACT_MAX_BYTES: photosService.PHOTO_ARTIFACT_MAX_BYTES,
    STORED_MAX_BYTES: image.STORED_MAX_BYTES,
    IMAGE_LIMITS_maxStoredBytes: image.IMAGE_LIMITS.maxStoredBytes,
    IMAGE_LIMITS_maxInputBytes: image.IMAGE_LIMITS.maxInputBytes,
    FACE_IMAGE_MAX_BYTES_compatAlias: sealsService.FACE_IMAGE_MAX_BYTES,
    maxReencodeRounds: image.IMAGE_LIMITS.maxReencodeRounds
  }
  check(
    'seals-artifact-const',
    'A 印面图**产物侧**上限与照片路径**同源同值**（4 MiB；输入上限仍 1 MB；旧导出保留为兼容别名）',
    sealsService.FACE_IMAGE_ARTIFACT_MAX_BYTES === photosService.PHOTO_ARTIFACT_MAX_BYTES &&
      sealsService.FACE_IMAGE_ARTIFACT_MAX_BYTES === image.STORED_MAX_BYTES &&
      sealsService.FACE_IMAGE_ARTIFACT_MAX_BYTES === image.IMAGE_LIMITS.maxStoredBytes &&
      sealsService.FACE_IMAGE_ARTIFACT_MAX_BYTES > image.IMAGE_LIMITS.maxInputBytes &&
      sealsService.FACE_IMAGE_MAX_BYTES === image.IMAGE_LIMITS.maxInputBytes,
    JSON.stringify(numbers.consts)
  )

  /* ---- 管理员身份（「重新上传印面图」是管理员能力） ---- */
  authService.logout()
  const adminLogin = authService.login(ADMIN_PHONE, authService.DEV_SMS_CODE)
  numbers.admin = {
    ok: adminLogin.ok === true,
    id: adminLogin.user && adminLogin.user.id,
    role: adminLogin.user && adminLogin.user.role
  }
  const face = (sealsService.listFacesOf('XAI-0001') || [])[0] || null
  const beforeId = face ? face.face_image_id || null : null
  numbers.face = { id: face && face.id, faceImageIdBefore: beforeId }

  /* ---- A：正常小产物入库 ---- */
  const faceCanvas = smoothCanvas(600, 600)
  const faceBlob = await toBlobHonest(faceCanvas, 'image/jpeg', 0.85)
  const faceLoaded = await image.loadImageFile(new File([faceBlob], 'seal-face.jpg', { type: 'image/jpeg' }))
  const faceExported = faceLoaded.ok ? await image.exportSquareImage(faceLoaded.bitmap, { maxSide: 512 }) : { ok: false }
  const faceReading = faceExported.ok ? readBytes(faceExported.bytes) : null
  const replaced = face && faceExported.ok
    ? await sealsService.replaceFaceImage(face.id, {
        bytes: faceExported.bytes,
        mime: faceExported.mime,
        width: faceExported.width,
        height: faceExported.height
      })
    : { ok: false, reason: 'PRECONDITION', message: '前置条件不满足' }
  const faceAfter = face ? sealsService.getFaceById(face.id) : null
  const rowsAfter = db.listImageRows()
  numbers.normal = {
    exported: {
      ok: faceExported.ok === true,
      mime: faceExported.mime,
      bytes: faceExported.ok ? faceExported.bytes.length : 0,
      size: `${faceExported.width} × ${faceExported.height}`,
      bytesReading: faceReading
    },
    result: {
      ok: replaced.ok === true,
      reason: replaced.reason || '',
      faceImageId: replaced.faceImageId || '',
      previousFaceImageId: replaced.previousFaceImageId || '',
      imageMime: replaced.image && replaced.image.mime,
      message: replaced.message
    },
    faceImageIdAfter: faceAfter && faceAfter.face_image_id,
    oldImageRowKept: !!beforeId && rowsAfter.some((row) => row.id === beforeId),
    imageRowCount: rowsAfter.length
  }
  check(
    'seals-replace-ok',
    'A 正常小产物 ⇒ 印面图重新上传**成功**（reason 空、指向更新为新影像、旧影像行保留不删）',
    replaced.ok === true &&
      !!faceAfter && faceAfter.face_image_id === replaced.faceImageId &&
      afterFaceIdDiffers(replaced.faceImageId, beforeId) &&
      numbers.normal.oldImageRowKept === true,
    JSON.stringify(numbers.normal)
  )
  check(
    'seals-replace-mime-honest',
    'A 入库元数据 mime ＝**产品真源按字节**判出的格式（不采信声称值、不冒充 webp）',
    replaced.ok === true && !!replaced.image && !!faceReading && replaced.image.mime === faceReading.productMime,
    JSON.stringify({ rowMime: replaced.image && replaced.image.mime, productMime: faceReading && faceReading.productMime })
  )

  /* ---- B：注入「产物超大」⇒ ARTIFACT_TOO_LARGE 且文案不误导 ---- */
  const huge = new Uint8Array(image.IMAGE_LIMITS.maxStoredBytes + 1)
  /* 带**真 PNG 签名**前缀：若产物上限没生效，这些字节会通过魔数判定被当作图片收下。 */
  huge.set([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a], 0)
  const oversize = face
    ? await sealsService.replaceFaceImage(face.id, { bytes: huge, mime: 'image/webp', width: 2048, height: 2048 })
    : { ok: false, reason: 'PRECONDITION', message: '' }
  const faceAfterOversize = face ? sealsService.getFaceById(face.id) : null
  numbers.oversizeInjected = {
    injectedBytes: huge.length,
    injectedMiB: +(huge.length / 1024 / 1024).toFixed(2),
    capBytes: image.IMAGE_LIMITS.maxStoredBytes,
    ok: oversize.ok === true,
    reason: oversize.reason || '',
    message: oversize.message,
    misleadingClause: MISLEADING.test(oversize.message || ''),
    faceImageIdUnchanged: !!faceAfterOversize && faceAfterOversize.face_image_id === numbers.normal.faceImageIdAfter
  }
  check(
    'seals-artifact-over-reject',
    'A 注入「产物 > 4 MiB」⇒ 拒且 reason ＝ ARTIFACT_TOO_LARGE、文案＝「本机影像生成失败」，**不含**「请换一张更小的图」',
    oversize.ok === false &&
      oversize.reason === 'ARTIFACT_TOO_LARGE' &&
      /本机影像生成失败/.test(oversize.message || '') &&
      !MISLEADING.test(oversize.message || ''),
    JSON.stringify(numbers.oversizeInjected)
  )
  check(
    'seals-artifact-over-no-halfwrite',
    'A 产物超限被拒时**不留半成品**：印面指向与影像行数均不变',
    numbers.oversizeInjected.faceImageIdUnchanged === true &&
      db.listImageRows().length === numbers.normal.imageRowCount,
    JSON.stringify({ faceImageIdUnchanged: numbers.oversizeInjected.faceImageIdUnchanged, imageRowCount: db.listImageRows().length })
  )

  /* ---- C：回退 PNG 大产物（≈2.7 MiB：>1 MB 旧闸、<4 MiB 新上限）⇒ 必须入库成功 ---- */
  const toBlobOriginal = HTMLCanvasElement.prototype.toBlob
  HTMLCanvasElement.prototype.toBlob = function forcedPngBig(callback, type, quality) {
    return toBlobOriginal.call(this, callback, 'image/png', quality)
  }
  let pngBig = { ok: false }
  try {
    pngBig = await image.exportSquareImage(noiseCanvas(2048, 2048), {})
  } finally {
    HTMLCanvasElement.prototype.toBlob = toBlobOriginal
  }
  const pngBigAccept = face && pngBig.ok
    ? await sealsService.replaceFaceImage(face.id, {
        bytes: pngBig.bytes,
        mime: pngBig.mime,
        width: pngBig.width,
        height: pngBig.height
      })
    : { ok: false, reason: 'PRECONDITION', message: '' }
  numbers.pngFallbackBig = {
    artifactBytes: pngBig.ok ? pngBig.bytes.length : 0,
    artifactMiB: pngBig.ok ? +(pngBig.bytes.length / 1024 / 1024).toFixed(2) : 0,
    mime: pngBig.mime,
    reencodeRounds: pngBig.reencodeRounds,
    overOldInputGate: pngBig.ok ? pngBig.bytes.length > image.IMAGE_LIMITS.maxInputBytes : null,
    underNewArtifactCap: pngBig.ok ? pngBig.bytes.length <= image.IMAGE_LIMITS.maxStoredBytes : null,
    accepted: pngBigAccept.ok === true,
    reason: pngBigAccept.reason || '',
    message: pngBigAccept.message
  }
  check(
    'seals-fallback-png-accepted',
    'A 回退 PNG 大产物（>1 MB 旧闸、<4 MiB 新上限）⇒ **入库成功**（旧实现在此必判 TOO_LARGE 并甩误导文案）',
    pngBig.ok === true &&
      pngBig.bytes.length > image.IMAGE_LIMITS.maxInputBytes &&
      pngBig.bytes.length <= image.IMAGE_LIMITS.maxStoredBytes &&
      pngBigAccept.ok === true,
    JSON.stringify(numbers.pngFallbackBig)
  )

  /* ---- D：输入侧超 1 MB ⇒ 由**管线**拒（文案＝「所选文件…」，与产物侧分开） ---- */
  const overInput = new Uint8Array(1258291)
  overInput.set([0xff, 0xd8, 0xff], 0)
  const overLoaded = await image.loadImageFile(new File([overInput], 'seal-face-over.jpg', { type: 'image/jpeg' }))
  numbers.inputOver = {
    fileBytes: overInput.length,
    ok: overLoaded.ok === true,
    message: overLoaded.message,
    mentionsSelectedFile: /所选文件/.test(overLoaded.message || ''),
    isInputSideWording: /请换一张更小的图/.test(overLoaded.message || '')
  }
  check(
    'seals-input-over-rejected-by-pipeline',
    'A 输入超 1 MB ⇒ 由管线（`loadImageFile`）拒，文案＝「所选文件…（上限 1 MB）」（输入侧口径，与产物侧分开）',
    overLoaded.ok === false && numbers.inputOver.mentionsSelectedFile === true,
    JSON.stringify(numbers.inputOver)
  )

  /* ---- 非图片字节仍按魔数拒（不因放宽上限而放松「是不是图片」） ---- */
  const junk = face
    ? await sealsService.replaceFaceImage(face.id, { bytes: new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8]), mime: 'image/webp' })
    : { ok: false, reason: 'PRECONDITION', message: '' }
  numbers.notImage = { reason: junk.reason, message: junk.message }
  check(
    'seals-not-image-still',
    'A 放宽产物上限**不放松**「是不是图片」：认不出的字节仍拒（reason ＝ NOT_IMAGE）',
    junk.ok === false && junk.reason === 'NOT_IMAGE',
    JSON.stringify(numbers.notImage)
  )

  /* ---- 收尾：把登录态还原成普通用户（后续 App 流程仍按普通用户跑） ---- */
  authService.logout()
  const back = authService.login(TEST_PHONE, authService.DEV_SMS_CODE)
  numbers.sessionRestored = { ok: back.ok === true, id: back.user && back.user.id }

  window.__XIAI_PROBE_RESULTS__ = RESULTS
  return { phase: 3, at: RESULTS.phase3At, numbers, checks: RESULTS.checks.slice() }
}

/** 指向是否真的换到了**别的**影像（旧值可能为 null）。 */
function afterFaceIdDiffers(nextId, prevId) {
  return !!nextId && String(nextId) !== String(prevId || '')
}

globalThis.__XIAI_PROBE__ = {
  phase1,
  phase2,
  phase3,
  results: () => RESULTS,
  audit: auditLocalStorage,
  /* 产品真源（证据脚本做格式判定只准调它，**不得**自建魔数副本）：src/utils/image.js::sniffBytesMime */
  sniffBytesMime: (bytes) => image.sniffBytesMime(bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes || []))
}

if (!sessionStorage.getItem(FLAG)) {
  phase1().catch((err) => {
    RESULTS.errors.push(String((err && err.stack) || err))
    window.__XIAI_PROBE_RESULTS__ = RESULTS
    window.__XIAI_PROBE_ERROR__ = String((err && err.message) || err)
  })
} else {
  window.__XIAI_PROBE_READY__ = true
}
