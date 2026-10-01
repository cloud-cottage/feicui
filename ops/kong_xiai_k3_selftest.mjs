/**
 * 玺爱 · 本单自测（Kong）：① 编号 XA+9 位 ② 印文可空/佚名/防重键 ③ 必填仍生效 ④ 防重 ⑤ 侧栏登录态
 *
 * 跑法：cd /Users/kevin/bistro/xiai && node feicui/ops/kong_xiai_k3_selftest.mjs
 * 载入方式：Vite SSR 载入器直接执行工程内真实模块（data / services / utils / components / views），
 * 并以 SSR 真实渲染组件与页面取 DOM 文本；浏览器存储用替身（localStorage 内存表 + 最小 IndexedDB 实现），
 * 数据层「唯一碰存储」的纪律不变（`storage.js` / `blobstore.js` 仍是唯一入口）。
 * 所有循环有硬上界；退出码 0 = 全部通过。
 */
import { createServer } from 'vite'
import { createSSRApp, h } from 'vue'
import { createRouter, createMemoryHistory, RouterView } from 'vue-router'
import { renderToString } from '@vue/server-renderer'
import fs from 'node:fs'

const PROJECT = '/Users/kevin/bistro/xiai'
const OUT_JSON = `${PROJECT}/feicui/ops/kong_xiai_k3_selftest_raw.json`
const OUT_TXT = `${PROJECT}/feicui/ops/kong_xiai_k3_selftest_raw.txt`

/* ------------------------------ 断言收集 ------------------------------ */
const checks = []
function check(name, pass, detail) {
  checks.push({ name, pass: !!pass, detail: String(detail === undefined ? '' : detail) })
}

/* --------------------- 浏览器存储替身（localStorage） --------------------- */
const NS = 'xiai:v1:'
const mem = new Map()
globalThis.window = {
  localStorage: {
    getItem: (k) => (mem.has(k) ? mem.get(k) : null),
    setItem: (k, v) => mem.set(k, String(v)),
    removeItem: (k) => mem.delete(k)
  }
}

/* --------------- 浏览器存储替身（最小 IndexedDB：blobstore 用到的面） --------------- */
const idbStores = new Map()
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
const px = `data:image/png;base64,${PX_BODY}`
const px2 = 'data:image/png;base64,' + Buffer.concat([Buffer.from(PX_BODY, 'base64'), Buffer.from([1, 2, 3, 4])]).toString('base64')
const px3 = 'data:image/png;base64,' + Buffer.concat([Buffer.from(PX_BODY, 'base64'), Buffer.from([9, 9, 9, 9])]).toString('base64')

const plain = (html) => String(html).replace(/<!--[\s\S]*?-->/g, '')
const has = (html, needle) => plain(html).includes(needle)
const h1Of = (html) => (plain(html).match(/<h1[^>]*>([^<]*)<\/h1>/) || [])[1]

let ssr = null
let exitCode = 1
const report = {}

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
  const file = await load('/src/utils/file.js')
  const sealService = await load('/src/services/seals.js')

  /* ------------------------------ 0. 管理员登录 ------------------------------ */
  const login = services.auth.login('16601061656', '1234')
  const admin = login.user
  check('管理员登录（唯一管理员手机号）', login.ok && admin.role === 'admin', `role=${admin.role}`)

  /* --------------------------- 改前基线（逐字快照） --------------------------- */
  const legacyBefore = JSON.stringify(db.listSealRows())
  const legacyFaceIds = db.listFaceRows().filter((r) => r.sealId.startsWith('XAI-')).map((r) => r.id)
  const countOf = () => ({
    seals: db.listSealRows().length,
    faces: db.listFaceRows().length,
    images: db.listImageRows().length,
    blobs: db.listImageBinaryKeys().length
  })

  /* ============================ ① + ② 新增（印文留空） ============================ */
  const a = await services.seals.createSealWithFace(admin, {
    seal_name: '', // 印文留空
    dynasty: '清',
    type: '私印',
    faceImage: px
  })
  check(
    '② 印文留空 + 朝代/分类/印面图齐备 ⇒ 创建成功（不再返回 MISSING_REQUIRED）',
    a.ok === true && a.reason !== 'MISSING_REQUIRED',
    JSON.stringify({ ok: a.ok, reason: a.reason, missing: a.missing, message: a.message })
  )
  check('① 第 1 枚新印章编号 = XA000000001（9 位）', a.stampId === 'XA000000001', `stampId=${a.stampId}`)
  check('① 编号匹配 ^XA\\d{9}$', /^XA\d{9}$/.test(String(a.stampId)), String(a.stampId))
  check('① 编号串长 = 11（XA + 9 位数字）', String(a.stampId).length === 11, `len=${String(a.stampId).length}`)

  const b = await services.seals.createSealWithFace(admin, {
    seal_name: '测试印',
    dynasty: '明',
    type: '閒章',
    faceImage: px
  })
  check('① 第 2 枚递增为 XA000000002 且不与既有冲突', b.ok === true && b.stampId === 'XA000000002', `stampId=${b.stampId} ok=${b.ok} ${b.message || ''}`)
  check('② 印文非空时正常落盘（seal_name = 测试印）', b.seal && b.seal.seal_name === '测试印', JSON.stringify(b.seal && b.seal.seal_name))

  const rowsAfter = db.listSealRows()
  const newRows = rowsAfter.filter((r) => /^XA\d{9}$/.test(String(r.stamp_id || '')))
  check(
    '① 解析容错：旧 XAI-000x 不被当作序号（旧规则会得 0009，本单首枚仍为 000000001）',
    newRows.map((r) => r.stamp_id).join(',') === 'XA000000001,XA000000002',
    newRows.map((r) => r.stamp_id).join(',')
  )
  check(
    '① 既有 XAI-000x 8 行逐字未变（JSON 逐字比对）',
    JSON.stringify(rowsAfter.slice(0, 8)) === legacyBefore,
    `legacyBefore_md5=${Buffer.from(legacyBefore).toString('hex').slice(0, 16)}…`
  )
  check(
    '① 旧编号仍为 8 个、新编号 2 个，且新增动作未改写任何既有行',
    rowsAfter.filter((r) => /^XAI-\d+$/.test(String(r.stamp_id))).length === 8 &&
      rowsAfter.length === 10 &&
      JSON.stringify(db.listFaceRows().filter((r) => r.sealId.startsWith('XAI-')).map((r) => r.id)) === JSON.stringify(legacyFaceIds),
    `seals=${rowsAfter.length} legacy=${rowsAfter.filter((r) => /^XAI-\d+$/.test(String(r.stamp_id))).length}`
  )
  check(
    '① 新行实际值（贴全部新行）',
    newRows.length === 2,
    JSON.stringify(newRows.map((r) => ({ stamp_id: r.stamp_id, id: r.id, sealGroupId: r.sealGroupId, seal_name: r.seal_name, dynasty: r.dynasty, seal_type: r.seal_type, source: r.source })))
  )
  const faceIdsOfNew = db.listFaceRows().filter((r) => r.sealId === 'XA000000001').map((r) => r.id)
  const imgIdsOfNew = db.listImageRows().filter((r) => r.stamp_id === 'XA000000001').map((r) => r.id)
  check(
    '① 印面 id / 影像 id 模板不变（fc-<序号>-f1 / img-<序号>f，序号取 9 位）',
    faceIdsOfNew.length === 1 && /^fc-\d{9}-f1$/.test(faceIdsOfNew[0]) && imgIdsOfNew.length === 1 && /^img-\d{9}f$/.test(imgIdsOfNew[0]),
    JSON.stringify({ faceIds: faceIdsOfNew, imageIds: imgIdsOfNew })
  )

  /* ============================ ② 显示名与佚名回退 ============================ */
  const rowA = services.seals.getSealById('XA000000001')
  check('② 印文为空 ⇒ 落盘就是空串（不写占位词）', rowA.seal_name === '', JSON.stringify({ seal_name: rowA.seal_name, name: rowA.name }))

  const manifest = file.hdManifestText(rowA)
  const manifestLine = (manifest.match(/^印文：.*$/m) || ['<无该行>'])[0]
  check(
    '② 高清资料清单：标签改「印文：」且空则「佚名」（file.js:52）',
    manifest.includes('印文：佚名') && !manifest.includes('印章名称'),
    manifestLine
  )

  /* 显示取值顺序：优先 transcription_simplified（好读），再 seal_name，都空 ⇒ 佚名 */
  const c = await services.seals.createSealWithFace(admin, {
    seal_name: '',
    transcription_simplified: '長壽合文',
    dynasty: '漢',
    type: '吉語印',
    faceImage: px2
  })
  check('② 第 3 枚（仅简体印文）创建成功', c.ok === true, `${c.stampId} ${c.message || ''}`)
  check('② 第 3 枚编号递增为 XA000000003（不撞既有）', c.stampId === 'XA000000003', String(c.stampId))

  /* ------------------------- SSR 真实渲染：卡片 / 详情页 ------------------------- */
  const viewFiles = [
    ['square', '/', '/src/views/SquareView.vue'],
    ['seal-detail', '/seal/:id', '/src/views/SealDetailView.vue'],
    ['my-corrections', '/my/corrections', '/src/views/MyCorrectionsView.vue'],
    ['my-photos', '/my/photos', '/src/views/MyPhotosView.vue'],
    ['points', '/points', '/src/views/PointsView.vue'],
    ['login', '/login', '/src/views/LoginView.vue']
  ]
  const routes = []
  for (const [name, path, file_] of viewFiles) {
    const mod = await load(file_)
    routes.push({ name, path, component: mod.default || mod })
  }
  async function renderRoute(path) {
    const router = createRouter({ history: createMemoryHistory(), routes })
    const app = createSSRApp({ render: () => h(RouterView) })
    app.use(router)
    router.push(path)
    await router.isReady()
    return renderToString(app)
  }
  async function renderComp(component, props = null, path = '/') {
    const router = createRouter({ history: createMemoryHistory(), routes })
    const app = createSSRApp({ render: () => h(component, props || undefined) })
    app.use(router)
    router.push(path)
    await router.isReady()
    return renderToString(app)
  }

  const square = await renderRoute('/')
  check(
    '② 广场页（SSR 渲染）出现新印章且显示名回退为「佚名」',
    has(square, 'XA000000001') && has(square, '佚名'),
    `has_XA000000001=${has(square, 'XA000000001')} has_佚名=${has(square, '佚名')}`
  )
  const ddTexts = (plain(square).match(/<dd[^>]*>[^<]*<\/dd>/g) || []).slice(0, 60).map((t) => t.replace(/<[^>]*>/g, '')).join(' | ')
  check(
    '② 广场卡片读数（贴实际 DOM 文本片段）：「佚名」与「長壽合文」都在卡片读数里',
    ddTexts.includes('佚名') && ddTexts.includes('長壽合文'),
    ddTexts
  )
  check(
    '② 显示取值顺序保持现有逻辑（简体优先）：仅简体印文的印章卡片显示「長壽合文」',
    has(square, '長壽合文') && db.listSealRows().find((r) => r.stamp_id === 'XA000000003').seal_name === '',
    `has長壽合文=${has(square, '長壽合文')} seal_name=''`
  )
  check('② 广场页不再出现「待考」', !has(square, '待考'), `has待考=${has(square, '待考')}`)

  const detail = await renderRoute('/seal/XA000000001')
  check('② 详情页标题（h1）＝「佚名」', h1Of(detail) === '佚名', `h1=${JSON.stringify(h1Of(detail))}`)
  const faceName = (plain(detail).match(/face-block__name"[^>]*>([^<]*)</) || [])[1]
  check('② 详情页印面名（face-block__name）＝「佚名」', faceName === '佚名', `face-block__name=${JSON.stringify(faceName)}`)
  check('② 详情页不再出现「待考」', !has(detail, '待考'), `has待考=${has(detail, '待考')}`)

  const UploadSealDialog = (await load('/src/components/UploadSealDialog.vue')).default
  const uploadHtml = await renderComp(UploadSealDialog)
  const label = (plain(uploadHtml).match(/<label[^>]*for="upload-seal-name"[^>]*>([^<]*)<\/label>/) || [])[1]
  check('② 上传表单：印文字段标签＝「印文（选填）」', label === '印文（选填）', `label=${JSON.stringify(label)}`)
  check(
    '② 上传表单：说明文字只把朝代 / 分类 / 印面图列为必填，且不再出现「印章名称」',
    has(uploadHtml, '朝代、分类、印面图为必填项') && !has(uploadHtml, '印章名称'),
    `lede_ok=${has(uploadHtml, '朝代、分类、印面图为必填项')}`
  )

  const FaceFixedAttributesDialog = (await load('/src/components/FaceFixedAttributesDialog.vue')).default
  const faceDialogHtml = await renderComp(FaceFixedAttributesDialog, { face: { id: 'fc-000000001-f1', sealId: 'XA000000001', seal_name: '', face_image_id: null, material: '', edge_image_ids: [] } })
  check(
    '② 编辑固定属性弹窗对象名回退「佚名」（FaceFixedAttributesDialog.vue:111）',
    has(faceDialogHtml, '编辑对象：佚名'),
    (plain(faceDialogHtml).match(/编辑对象：[^<]*/) || [''])[0].trim()
  )

  check(
    '② 未把「印面归属待考」一并改掉（另一概念，seals.js:113）',
    sealService.faceLabelOf('__不存在__') === '印面归属待考',
    sealService.faceLabelOf('__不存在__')
  )

  /* ------------------------------ ③ 必填仍生效 ------------------------------ */
  const beforeRequired = countOf()
  const m1 = await services.seals.createSealWithFace(admin, { seal_name: '缺朝代', dynasty: '', type: '私印', faceImage: px3 })
  check('③ 缺朝代 ⇒ 拒（MISSING_REQUIRED 含「朝代」）', m1.ok === false && m1.reason === 'MISSING_REQUIRED' && m1.missing.includes('朝代'), JSON.stringify({ ok: m1.ok, reason: m1.reason, missing: m1.missing, message: m1.message }))
  const px4 = 'data:image/png;base64,' + Buffer.concat([Buffer.from(PX_BODY, 'base64'), Buffer.from([7, 7, 7])]).toString('base64')
  const m2 = await services.seals.createSealWithFace(admin, { seal_name: '缺分类', dynasty: '清', type: '', faceImage: px4 })
  check('③ 缺分类 ⇒ 拒（MISSING_REQUIRED 含「分类」）', m2.ok === false && m2.reason === 'MISSING_REQUIRED' && m2.missing.includes('分类'), JSON.stringify({ ok: m2.ok, reason: m2.reason, missing: m2.missing, message: m2.message }))
  const m3 = await services.seals.createSealWithFace(admin, { seal_name: '缺图', dynasty: '清', type: '私印' })
  check('③ 缺印面图 ⇒ 拒（MISSING_REQUIRED 含「印面图」）', m3.ok === false && m3.reason === 'MISSING_REQUIRED' && m3.missing.includes('印面图'), JSON.stringify({ ok: m3.ok, reason: m3.reason, missing: m3.missing, message: m3.message }))
  check(
    '③ 三次拒绝后集合计数与影像二进制数完全未变（无半成品）',
    JSON.stringify(countOf()) === JSON.stringify(beforeRequired),
    JSON.stringify({ before: beforeRequired, after: countOf() })
  )

  /* ------------------------------ ④ 防重仍生效 ------------------------------ */
  const beforeDedupe = countOf()
  const dupA = await services.seals.createSealWithFace(admin, { seal_name: '', dynasty: '清', type: '私印', faceImage: px })
  check(
    '④ 同一印章同图重复提交（印文留空）⇒ deduped',
    dupA.ok === true && dupA.deduped === true && dupA.stampId === 'XA000000001',
    JSON.stringify({ ok: dupA.ok, deduped: dupA.deduped, stampId: dupA.stampId, message: dupA.message })
  )
  const dupB = await services.seals.createSealWithFace(admin, { seal_name: '测试印', dynasty: '明', type: '閒章', faceImage: px })
  check(
    '④ 同一印章同图重复提交（印文非空）⇒ deduped',
    dupB.ok === true && dupB.deduped === true && dupB.stampId === 'XA000000002',
    JSON.stringify({ ok: dupB.ok, deduped: dupB.deduped, stampId: dupB.stampId })
  )
  check(
    '④ 两次 dedupe 未新增任何行 / 二进制（防重键 (印文,朝代,分类,sha256) 生效）',
    JSON.stringify(countOf()) === JSON.stringify(beforeDedupe),
    JSON.stringify({ before: beforeDedupe, after: countOf() })
  )

  /* ------------------------------ ⑤ 侧栏登录态（SSR 渲染） ------------------------------ */
  const AppSidebar = (await load('/src/components/AppSidebar.vue')).default
  services.auth.logout()
  const guestSide = await renderComp(AppSidebar)
  services.auth.login('16601061656', '1234')
  const loggedSide = await renderComp(AppSidebar)
  check('⑤ 侧栏・游客文案', has(guestSide, '游客可自由浏览印章与印面。'), (plain(guestSide).match(/<p>[^<]*<\/p>/g) || []).join(' '))
  check(
    '⑤ 侧栏・登录后文案真实变化（不再显示游客文案）',
    has(loggedSide, '登录后可提交勘误、上传实物照片。') && !has(loggedSide, '游客可自由浏览印章与印面。'),
    (plain(loggedSide).match(/<p>[^<]*<\/p>/g) || []).join(' ')
  )

  report.ok = checks.every((row) => row.pass)
  exitCode = report.ok ? 0 : 1
} catch (err) {
  check('自测脚本本身未抛异常', false, `${(err && err.stack) || err}`)
  exitCode = 1
} finally {
  report.generated_at = new Date().toISOString()
  report.checks = checks
  report.passed = checks.filter((row) => row.pass).length
  report.failed = checks.filter((row) => !row.pass).length
  report.ok = report.failed === 0
  exitCode = report.ok ? 0 : 1
  fs.writeFileSync(OUT_JSON, JSON.stringify(report, null, 2))
  const lines = checks.map((row, i) => `${row.pass ? 'PASS' : 'FAIL'}  ${String(i + 1).padStart(2, '0')}. ${row.name}\n        ${row.detail}`)
  fs.writeFileSync(OUT_TXT, `# 玺爱 · 本单自测（Kong）\n# ${report.generated_at}\n# passed=${report.passed} failed=${report.failed}\n\n${lines.join('\n')}\n`)
  for (const line of lines) console.log(line)
  console.log(`\n== passed=${report.passed} failed=${report.failed} ok=${report.ok} ==`)
  console.log(`raw: ${OUT_JSON}`)
  if (ssr) await ssr.close()
}

process.exit(exitCode)
