// editionSuffix() 纯函数断言（零依赖：node 内置 assert；`npm run test:edition`）
// 判据（spec §0.5.4 v1.41）：localhost / 127.0.0.1 / ::1 / *.local ⇒ 「 · 本地服务私有版」；
// 公网域名（如 yinyuan2026.vercel.app）⇒ ''（feicui-web 无后缀）。
import assert from 'node:assert/strict'
import { BASE_TITLE, EDITION_LOCAL_PRIVATE, editionSuffix } from '../src/composables/useEdition.js'

const CASES = [
  // ── 本地族 ⇒ 带后缀 ──
  ['localhost', EDITION_LOCAL_PRIVATE],
  ['LOCALHOST', EDITION_LOCAL_PRIVATE],
  ['127.0.0.1', EDITION_LOCAL_PRIVATE],
  ['::1', EDITION_LOCAL_PRIVATE],
  ['[::1]', EDITION_LOCAL_PRIVATE],
  ['mini.local', EDITION_LOCAL_PRIVATE],
  ['kevins-mbp.lan.local', EDITION_LOCAL_PRIVATE],
  ['book.local', EDITION_LOCAL_PRIVATE],
  // ── 公网族 ⇒ 无后缀 ──
  ['yinyuan2026.vercel.app', ''],
  ['feicui.vercel.app', ''],
  ['example.com', ''],
  ['feicui.example.org', ''],
  ['localhost.example.com', ''],
  ['127.0.0.1.evil.com', ''],
  // ── 边界 ⇒ 无后缀（容错，不抛错）──
  ['', ''],
  ['  ', ''],
  [undefined, ''],
  [null, ''],
  [42, ''],
]

let passed = 0
for (const [input, expected] of CASES) {
  const got = editionSuffix(input)
  assert.equal(got, expected, `editionSuffix(${JSON.stringify(input)}) ⇒ ${JSON.stringify(got)}, 期望 ${JSON.stringify(expected)}`)
  passed += 1
}

// 展示名全串形态断言（后缀拼接前后）
assert.equal(BASE_TITLE + editionSuffix('localhost'), '「斐萃」玺印解析任务台 · 本地服务私有版')
assert.equal(BASE_TITLE + editionSuffix('yinyuan2026.vercel.app'), '「斐萃」玺印解析任务台')
assert.equal(BASE_TITLE, '「斐萃」玺印解析任务台')
assert.equal(EDITION_LOCAL_PRIVATE, ' · 本地服务私有版')
passed += 4

console.log(`editionSuffix: PASS ${passed} / FAIL 0`)
