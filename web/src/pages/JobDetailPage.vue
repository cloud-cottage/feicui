<script setup>
// 任务详情页：E2 GET /api/jobs/{job_id} 轮询展示**真实进度**。
//
// ★ S-1（spec §3.2）纪律，页内明文标注：
//   进度条宽度 = 后端返回的 done_pages / total_pages（**库内复算值**）；
//   前端**没有任何**计时器 / 估算 / 插值在推进进度；定时器只负责「重新取数」。
//   total_pages 缺失或 ≤0 ⇒ 不画进度，显示 `—`。
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { checkE2Shape, getJob } from '@/api/jobs'
import { describeFailure } from '@/api/client'
// 文档预览（E9 整页渲染 ＋ E10 检测框）：路径常量与形状解析全在 `@/api/jobsPreview`（一处收口）
import {
  PREVIEW_DPI_DEFAULT,
  PREVIEW_DPI_WHITELIST,
  UNMARKED_BOOK_NOTE_PREFIX,
  boxPercentStyle,
  fetchPreviewBoxes,
  previewErrorText,
  previewPngUrl,
  probePreviewPng,
  templateSourceBadge,
} from '@/api/jobsPreview'
import { ACTIVE_STATES, E2_CURSOR_KEYS, STATE_LABELS } from '@/config/constants'
import { useBackendStatus } from '@/composables/useBackendStatus'
import { usePolling } from '@/composables/usePolling'
import { isNil, nilDash, nowStamp, rawBodyText } from '@/utils/format'
import StateNotice from '@/components/StateNotice.vue'
import CountersTable from '@/components/CountersTable.vue'

const route = useRoute()
const { markBackendDown, markBackendUp } = useBackendStatus()

const jobId = computed(() => String(route.params.job_id || ''))
const snapshot = ref(null) // 最近一次成功的 E2 响应体（**后端原值**）
const snapshotAt = ref(null) // 该快照的取数时点
const status = ref({ kind: 'loading', statusCode: '', raw: '', detail: '' })
const shapeNotes = ref([])
const stale = ref(false)

const { start, stop, tick, lastRunAt, runCount } = usePolling(fetchOnce, { interval: 2000 })

async function fetchOnce() {
  if (!jobId.value) return
  try {
    const res = await getJob(jobId.value)
    if (res.status === 200 && res.body) {
      snapshot.value = res.body
      snapshotAt.value = nowStamp()
      stale.value = false
      markBackendUp()
      shapeNotes.value = checkE2Shape(res.body).notes
      status.value = { kind: 'ok', statusCode: 200, raw: res.raw, detail: '' }
      const st = res.body.state
      if (!ACTIVE_STATES.includes(st)) stop() // 终态不再轮询（DONE / FAILED_PARTIAL）
    } else if ([404, 405, 501].includes(res.status)) {
      status.value = {
        kind: 'not-implemented',
        statusCode: res.status,
        raw: res.raw,
        detail: 'E2 端点未实现（spec §3.1 E2 已定义该端点；此处为后端未就绪）',
      }
      stop()
    } else {
      status.value = {
        kind: 'error',
        statusCode: res.status,
        raw: res.raw || rawBodyText(res.body),
        detail: 'E2 返回非 200（原样展示）',
      }
    }
  } catch (e) {
    const f = describeFailure(e)
    if (f.kind === 'backend-down') {
      markBackendDown(f.detail)
      stale.value = !!snapshot.value
      status.value = { kind: 'backend-down', statusCode: '', raw: '', detail: f.detail }
      // 后端挂掉 ⇒ 停止轮询（避免无意义请求），保留最后一次快照并标「已过期」
      stop()
    } else {
      status.value = { kind: 'error', statusCode: '', raw: '', detail: f.message }
    }
  }
}

// 进度：**只**由后端两个字段算出（S-1）
const progress = computed(() => {
  const j = snapshot.value
  if (!j) return null
  const total = Number(j.total_pages)
  const done = Number(j.done_pages)
  if (!Number.isFinite(total) || total <= 0 || !Number.isFinite(done)) return null
  const pct = Math.max(0, Math.min(100, (done / total) * 100))
  return { done, total, pct }
})

const failedPages = computed(() => {
  const j = snapshot.value
  if (!j || !Array.isArray(j.failed_pages)) return null
  return j.failed_pages
})

// 如实指出 S-2 判定冲突（前端只上报现象，不擅自改判后端状态）
const s2Violation = computed(
  () => snapshot.value && snapshot.value.state === 'DONE' && failedPages.value && failedPages.value.length > 0
)

const cursorRows = computed(() => {
  const j = snapshot.value
  const c = j && j.cursor
  return E2_CURSOR_KEYS.map((k) => ({ key: k, value: c && !isNil(c[k]) ? c[k] : '—' }))
})

watch(
  jobId,
  () => {
    snapshot.value = null
    snapshotAt.value = null
    status.value = { kind: 'loading', statusCode: '', raw: '', detail: '' }
    stale.value = false
    start()
  },
  { immediate: true }
)

// ═══════════════════════════════════════════════════════════════════════════════
// 文档预览卡（印谱解析线内 · E9 整页渲染 ＋ E10 检测框叠加）
//   口径真源：feicui/docs/page-preview-draft-v0.1.md §2.4（**不新增页签 ⇒ 不动 AC-23**）。
//   纪律：框走**绝对定位百分比覆盖层**（不烧进图）；loading / 失败**必须可见**、
//         **不得**用占位图冒充；色值一律走既有 token；零外链资源。
// ═══════════════════════════════════════════════════════════════════════════════
const previewPage = ref(1) // 1-based（↔ stamps.page）；首次拿到 E10 的 job_page_range 后按 §2.4 取 from
const previewDpi = ref(PREVIEW_DPI_DEFAULT)
const previewBody = ref(null) // 最近一次成功的 E10 响应体（**后端原值**）
const previewAt = ref(null)
const previewStatus = ref({ kind: 'idle', statusCode: '', code: '', detail: '', raw: '' })
const previewImg = ref({ state: 'idle', naturalWidth: null, naturalHeight: null, url: '' })
const rangeAdopted = ref(false) // 「页码默认取 job 的 page_range.from」只自动落一次，不抢用户的选择

const previewRender = computed(() => (previewBody.value && previewBody.value.render) || null)
const previewTemplateSource = computed(
  () => (previewBody.value && previewBody.value.template_source) || ''
)
const previewBadge = computed(() => templateSourceBadge(previewTemplateSource.value))
const previewBoxes = computed(() => {
  const b = previewBody.value
  return b && Array.isArray(b.boxes) ? b.boxes : []
})
const previewCounts = computed(() => {
  const c = previewBody.value && previewBody.value.counts
  return c && typeof c === 'object' ? c : { stamp: null, edge: null }
})
const previewNotes = computed(() => {
  const n = previewBody.value && previewBody.value.notes
  return Array.isArray(n) ? n : []
})
const previewPdfPageCount = computed(() => {
  const n = Number(previewBody.value && previewBody.value.pdf_page_count)
  return Number.isFinite(n) && n > 0 ? n : null
})
const previewRangeText = computed(() => {
  const r = previewBody.value && previewBody.value.job_page_range
  return r ? `${r.from}–${r.to}` : '—'
})
const previewStampRows = computed(() => {
  const d = previewBody.value && previewBody.value.db
  return d && d.stamp_rows !== undefined ? d.stamp_rows : null
})
const previewImgUrl = computed(() =>
  jobId.value && previewPage.value
    ? previewPngUrl(jobId.value, previewPage.value, previewDpi.value)
    : ''
)
const previewRenderText = computed(() => {
  const r = previewRender.value
  return r ? `${r.dpi}dpi · ${r.width}×${r.height}px` : '—'
})
// PP-3 几何自洽：页面上量的 naturalWidth/Height 必须等于 E10 的 render.width/height
const previewImgAligned = computed(() => {
  const r = previewRender.value
  const i = previewImg.value
  if (!r || i.state !== 'ok') return null
  return Number(i.naturalWidth) === Number(r.width) && Number(i.naturalHeight) === Number(r.height)
})
const previewBoxStyle = (box) => boxPercentStyle(box, previewRender.value)
const previewCanPrev = computed(() => Number(previewPage.value) > 1)
const previewCanNext = computed(() => {
  const n = previewPdfPageCount.value
  return n === null ? true : Number(previewPage.value) < n
})

async function loadPreviewBoxes() {
  if (!jobId.value || !previewPage.value) return
  previewStatus.value = { kind: 'loading', statusCode: '', code: '', detail: '', raw: '' }
  const res = await fetchPreviewBoxes(jobId.value, previewPage.value, previewDpi.value)
  if (res.state === 'ok') {
    previewBody.value = res.body
    previewAt.value = nowStamp()
    previewStatus.value = { kind: 'ok', statusCode: 200, code: '', detail: '', raw: res.raw }
    adoptRangeFrom()
  } else {
    previewBody.value = null
    previewStatus.value = {
      kind: res.state === 'unknown' ? 'backend-down' : 'error',
      statusCode: res.status || '',
      code: res.code || '',
      detail: res.detail || '',
      raw: res.raw || '',
    }
  }
}

/** §2.4：页码默认取 job 的 page_range.from（无则 1）—— 首份 E10 响应到手后落一次 */
function adoptRangeFrom() {
  if (rangeAdopted.value) return
  rangeAdopted.value = true
  const r = previewBody.value && previewBody.value.job_page_range
  const from = Number(r && r.from)
  if (Number.isFinite(from) && from >= 1 && from !== Number(previewPage.value)) {
    previewPage.value = from
  }
}

function normalizePage() {
  const n = Math.floor(Number(previewPage.value))
  previewPage.value = Number.isFinite(n) && n >= 1 ? n : 1
}

function gotoPreviewPage(p) {
  const n = Math.floor(Number(p))
  previewPage.value = Number.isFinite(n) && n >= 1 ? n : 1
}

function previewFirst() {
  gotoPreviewPage(1)
}

function previewPrev() {
  if (previewCanPrev.value) gotoPreviewPage(previewPage.value - 1)
}

function previewNext() {
  if (previewCanNext.value) gotoPreviewPage(previewPage.value + 1)
}

function previewLast() {
  const n = previewPdfPageCount.value
  if (n !== null) gotoPreviewPage(n)
}

// job 切换：清空预览卡的本地态（页码回 1；「page_range.from 只自动落一次」的重置）。
// **必须在 load 那个 watch 之前注册** —— 同一批 flush 里两个 watcher 按注册顺序跑，
// 先归零再取数，避免拿旧页码去请求新 job。
watch(
  jobId,
  () => {
    previewBody.value = null
    previewAt.value = null
    previewStatus.value = { kind: 'idle', statusCode: '', code: '', detail: '', raw: '' }
    previewImg.value = { state: 'idle', naturalWidth: null, naturalHeight: null, url: '' }
    rangeAdopted.value = false
    previewPage.value = 1
  },
  { immediate: true }
)

// 换页 / 换 dpi / 换 job ⇒ 图与框都重取；`<img>` 的加载态由本页自己置位（loading 必须可见）。
// `immediate: true`：**首次挂载也要取一次**（否则卡片停在「尚未取框」而图已经加载）。
watch(
  [jobId, previewPage, previewDpi],
  () => {
    previewImg.value = { state: 'loading', naturalWidth: null, naturalHeight: null, url: previewImgUrl.value }
    loadPreviewBoxes()
  },
  { immediate: true }
)

function onPreviewImgLoad(e) {
  const el = e.target
  previewImg.value = {
    state: 'ok',
    naturalWidth: el.naturalWidth,
    naturalHeight: el.naturalHeight,
    url: el.currentSrc || el.src || previewImgUrl.value,
  }
}

async function onPreviewImgError() {
  // `<img>` 拿不到状态码 ⇒ 用一次 E9 请求取**真实原因码**（不猜、不用占位图冒充）
  const res = await probePreviewPng(jobId.value, previewPage.value, previewDpi.value)
  previewImg.value = {
    state: 'error',
    naturalWidth: null,
    naturalHeight: null,
    url: previewImgUrl.value,
    code: res.code || '',
    status: res.status || 0,
    detail: res.detail || '',
  }
}

// 键盘 ← / →（焦点在输入 / 下拉 / 可编辑元素内时不拦截，避免抢走光标移动）
function onPreviewKeydown(e) {
  if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
  const t = e.target
  const tag = t && t.tagName ? String(t.tagName).toLowerCase() : ''
  if (tag === 'input' || tag === 'textarea' || tag === 'select' || (t && t.isContentEditable)) return
  if (e.key === 'ArrowLeft') previewPrev()
  else previewNext()
}

onMounted(() => window.addEventListener('keydown', onPreviewKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onPreviewKeydown))
</script>

<template>
  <section class="page">
    <header class="page__head">
      <h2>任务详情（E2 真实进度）</h2>
      <p class="page__sub">
        job_id ＝ <code>{{ jobId }}</code>
        <button class="ghost" type="button" @click="tick">立即刷新</button>
        <span class="muted">轮询间隔 2s · 已完成取数 {{ runCount }} 次</span>
      </p>
    </header>

    <div class="card card--s1">
      <strong>S-1（spec §3.2）：进度来自后端库内复算。</strong>
      <p class="muted">
        本页进度条宽度**只**取自后端 E2 的 <code>done_pages / total_pages</code>；前端**没有**计时器 /
        估算 / 插值在推进进度。最近一次成功取数时点 ＝
        <code>{{ snapshotAt || '—' }}</code>（即「数据时点」）。
      </p>
    </div>

    <StateNotice
      v-if="status.kind === 'loading' && !snapshot"
      kind="loading"
      title="正在请求 E2 GET /api/jobs/{job_id} …"
    />
    <StateNotice
      v-if="status.kind === 'backend-down'"
      kind="backend-down"
      title="后端未启动 / 未连接：E2 无法获取"
      :detail="`判负细节 ${status.detail || '—'}；本页不展示任何示例或估算进度`"
    />
    <StateNotice
      v-else-if="status.kind === 'not-implemented'"
      kind="not-implemented"
      title="后端尚未提供该接口（E2）"
      :status-code="status.statusCode"
      :raw-text="status.raw"
    />
    <StateNotice
      v-else-if="status.kind === 'error'"
      kind="error"
      title="E2 请求失败（原样展示）"
      :status-code="status.statusCode"
      :raw-text="status.raw"
      :detail="status.detail"
    />

    <template v-if="snapshot">
      <div v-if="stale" class="notice notice--warn">
        后端已断开 ⇒ 以下为**最后一次成功取数**的快照（时点 {{ snapshotAt }}），**已过期**，不再更新。
      </div>

      <div class="card">
        <h3>进度（后端复算值，S-1）</h3>
        <div class="kv-row">
          <span>state</span>
          <strong><code>{{ snapshot.state || '—' }}</code></strong>
          <span class="muted">{{ STATE_LABELS[snapshot.state] || '（未在 spec §2.2 状态机内）' }}</span>
        </div>
        <div class="kv-row">
          <span>done_pages / total_pages</span>
          <strong>
            <template v-if="isNil(snapshot.done_pages) || isNil(snapshot.total_pages)">—（后端未给全）</template>
            <template v-else>{{ snapshot.done_pages }} / {{ snapshot.total_pages }}</template>
          </strong>
        </div>
        <div v-if="progress" class="progress" role="progressbar" :aria-valuenow="progress.done" :aria-valuemax="progress.total">
          <div class="progress__bar" :style="{ width: progress.pct + '%' }"></div>
        </div>
        <p v-if="progress" class="muted">
          {{ progress.pct.toFixed(2) }}% ＝ done_pages/total_pages（后端值原样换算，无本地推进）
        </p>
        <p v-else class="muted">不画进度：后端未给出可用的 total_pages / done_pages。</p>
      </div>

      <div class="card">
        <h3>failed_pages（可为空数组，**不得省略**）</h3>
        <p v-if="failedPages === null" class="muted">后端未返回 <code>failed_pages</code> 数组（形状提示见下）。</p>
        <template v-else-if="failedPages.length === 0">
          <p class="muted">空数组（0 页失败）</p>
        </template>
        <template v-else>
          <p><strong>{{ failedPages.length }}</strong> 页失败：</p>
          <ul>
            <li v-for="(p, i) in failedPages" :key="i"><code>{{ p }}</code></li>
          </ul>
        </template>
        <p v-if="s2Violation" class="warnline">
          ⚠ 与 spec §3.2 S-2 冲突：<code>failed_pages</code> 非空而 <code>state=DONE</code>（假完成判负形态）。
          本页只如实呈现后端返回值，不擅自改判。
        </p>
      </div>

      <div class="card">
        <h3>cursor（页级断点游标，spec §2.3）</h3>
        <table class="kv">
          <tbody>
            <tr v-for="r in cursorRows" :key="r.key">
              <th><code>cursor.{{ r.key }}</code></th>
              <td>{{ r.value }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card">
        <h3>counters（后端原值，缺失显示 `—`，不补 0）</h3>
        <CountersTable :counters="snapshot.counters" />
      </div>

      <!-- ═══════════════════════════════════════════════════════════════════════
           文档预览卡（E9 整页渲染 ＋ E10 检测框叠加）—— 口径件 §2.4：**不新增页签**（AC-23 未动）。
           框＝绝对定位百分比覆盖层（不烧进图）；loading / 失败必可见；零外链资源。
           ═══════════════════════════════════════════════════════════════════════ -->
      <div class="card card--preview">
        <div class="card__head">
          <h3>文档预览（整页渲染 ＋ 检测框叠加）</h3>
          <button class="ghost" type="button" @click="loadPreviewBoxes">刷新框</button>
        </div>
        <p class="muted">
          框＝<code>GET /api/jobs/{job_id}/pages/{page}/boxes</code>（**现场检测**，不来自 DB）·
          图＝<code>GET /api/jobs/{job_id}/pages/{page}/preview.png</code>；
          两者用**同一个 dpi**，故框与图在同一像素空间。
        </p>

        <div class="field-row">
          <label class="field field--sm">
            <span class="field__label">页码 page（1-based）</span>
            <input v-model.number="previewPage" type="number" min="1" @change="normalizePage" />
          </label>
          <label class="field field--sm">
            <span class="field__label">dpi（白名单）</span>
            <select v-model.number="previewDpi">
              <option v-for="d in PREVIEW_DPI_WHITELIST" :key="d" :value="d">{{ d }}</option>
            </select>
          </label>
          <button class="ghost" type="button" :disabled="!previewCanPrev" @click="previewFirst">⏮ 首页</button>
          <button class="ghost" type="button" :disabled="!previewCanPrev" @click="previewPrev">← 上一页</button>
          <button class="ghost" type="button" :disabled="!previewCanNext" @click="previewNext">下一页 →</button>
          <button class="ghost" type="button" :disabled="previewPdfPageCount === null" @click="previewLast">
            末页 ⏭
          </button>
        </div>
        <p class="muted">
          键盘 <code>←</code> / <code>→</code> 翻页（焦点在输入 / 下拉内时不拦截）。页码默认取 job 的
          <code>page_range.from</code>（无则 1）；job 的页区间**不是**硬边界 —— 可翻整本
          （超出 PDF 实际页数时后端如实回 <code>PAGE_OUT_OF_PDF</code>）。
        </p>

        <div class="pv-meta">
          <span class="pv-legend pv-legend--stamp">🔴 印章({{ previewCounts.stamp ?? '—' }})</span>
          <span class="pv-legend pv-legend--edge">🟢 边款({{ previewCounts.edge ?? '—' }})</span>
          <span class="muted">render ＝ {{ previewRenderText }}</span>
          <span class="muted">PDF 共 {{ previewPdfPageCount ?? '—' }} 页</span>
          <span class="muted">job 页区间 {{ previewRangeText }}</span>
          <span class="muted">
            db.stamp_rows（只读对照，**框不来自 DB**）＝ {{ previewStampRows ?? '—' }}
          </span>
        </div>
        <p v-if="previewTemplateSource" class="pv-src" :class="{ 'pv-src--warn': previewBadge.unmarked }">
          框参数来源：<code>{{ previewBadge.text }}</code>
        </p>
        <p v-if="previewBadge.unmarked" class="pv-src pv-src--warn">
          {{ UNMARKED_BOOK_NOTE_PREFIX }}：框由内建默认参数检出，可能不准
        </p>
        <ul v-if="previewNotes.length" class="pv-notes">
          <li v-for="n in previewNotes" :key="n">{{ n }}</li>
        </ul>

        <StateNotice
          v-if="previewStatus.kind === 'loading'"
          kind="loading"
          title="正在取检测框（E10）…"
        />
        <StateNotice
          v-else-if="previewStatus.kind === 'backend-down'"
          kind="backend-down"
          title="后端未启动 / 未连接：预览取不到框"
          :detail="previewStatus.detail"
        />
        <StateNotice
          v-else-if="previewStatus.kind === 'error'"
          kind="error"
          :title="`预览取框失败：${previewStatus.code || '（后端未给 error 码）'}`"
          :status-code="previewStatus.statusCode"
          :detail="`${previewErrorText(previewStatus.code)}${previewStatus.detail ? ' —— ' + previewStatus.detail : ''}`"
          :raw-text="previewStatus.raw"
        />
        <p v-else-if="previewStatus.kind === 'ok'" class="muted">
          框已取：{{ previewBoxes.length }} 个（印章 {{ previewCounts.stamp }} / 边款
          {{ previewCounts.edge }}）· 取数时点 {{ previewAt || '—' }}
        </p>
        <p v-else class="muted">尚未取框（等待 E10 响应）。</p>

        <div v-if="previewImgUrl" class="pv-stage">
          <img
            class="pv-img"
            :src="previewImgUrl"
            :alt="`第 ${previewPage} 页整页渲染（E9）`"
            @load="onPreviewImgLoad"
            @error="onPreviewImgError"
          />
          <div class="pv-overlay" aria-hidden="true">
            <div
              v-for="(b, i) in previewBoxes"
              :key="`${b.kind}-${i}`"
              class="pv-box"
              :class="b.kind === 'stamp' ? 'pv-box--stamp' : 'pv-box--edge'"
              :style="previewBoxStyle(b)"
              :title="`${b.kind} #${i} x1=${b.x1} y1=${b.y1} x2=${b.x2} y2=${b.y2}`"
            ></div>
          </div>
        </div>

        <p v-if="previewImg.state === 'loading'" class="pv-imgstate">
          整页图加载中…（E9；图未到之前**不显示占位图**）
        </p>
        <p v-else-if="previewImg.state === 'error'" class="pv-imgstate pv-imgstate--err">
          整页图取用失败：
          <strong>{{ previewErrorText(previewImg.code) || '（无法取得原因码）' }}</strong>
          <template v-if="previewImg.status"> （HTTP {{ previewImg.status }}）</template>
          <template v-if="previewImg.detail"> —— {{ previewImg.detail }}</template>
          <br />本卡**不显示占位图 / 示例图冒充**；URL＝<code>{{ previewImg.url }}</code>
        </p>
        <p v-else-if="previewImg.state === 'ok'" class="pv-imgstate muted">
          图已加载：<code>naturalWidth×naturalHeight = {{ previewImg.naturalWidth }}×{{ previewImg.naturalHeight }}</code>
          · render ＝ <code>{{ previewRenderText }}</code> ·
          <span v-if="previewImgAligned === true" class="pv-ok">
            几何自洽 ✓（naturalWidth ＝ render.width，两 origin 同口径）
          </span>
          <span v-else-if="previewImgAligned === false" class="pv-bad">
            几何**不自洽**：naturalWidth ≠ render.width（框会错位，如实上报）
          </span>
          <span v-else class="muted">（render 未知，暂不比对几何）</span>
        </p>

        <details v-if="previewStatus.kind === 'ok'">
          <summary>原始响应体（E10 全文，未改写）</summary>
          <pre>{{ previewStatus.raw }}</pre>
        </details>
      </div>

      <div class="card">
        <h3>其余字段（原样展示）</h3>
        <table class="kv">
          <tbody>
            <tr><th><code>job_id</code></th><td><code>{{ snapshot.job_id || '—' }}</code></td></tr>
            <tr><th><code>started_at</code></th><td>{{ nilDash(snapshot.started_at) }}</td></tr>
            <tr><th><code>updated_at</code></th><td>{{ nilDash(snapshot.updated_at) }}</td></tr>
            <tr><th>数据时点（本页取数）</th><td>{{ snapshotAt || '—' }}</td></tr>
          </tbody>
        </table>
        <details>
          <summary>原始响应体（E2 全文，未改写）</summary>
          <pre>{{ status.raw }}</pre>
        </details>
      </div>

      <div v-if="shapeNotes.length" class="card">
        <h3>形状提示（spec §3.1 E2 字段）</h3>
        <ul>
          <li v-for="n in shapeNotes" :key="n">{{ n }}</li>
        </ul>
      </div>

      <div class="card">
        <h3>相关页面</h3>
        <p>
          <RouterLink :to="`/jobs/${jobId}/results`">结果页（E3，预留）</RouterLink>
          ·
          <RouterLink :to="`/jobs/${jobId}/missing`">缺失清单（E5）</RouterLink>
          ·
          <RouterLink to="/">返回印谱解析</RouterLink>
        </p>
      </div>
    </template>
  </section>
</template>

<!-- 文档预览卡专用样式：**色值一律走既有 token**（styles/base.css 的 :root），零外链资源。
     框＝绝对定位百分比覆盖层（`boxPercentStyle` 给 left/top/width/height），**不烧进图**，
     故「显示/隐藏框」只是这一层的开关。 -->
<style scoped>
.pv-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: baseline;
  margin: 8px 0 4px;
}
.pv-legend {
  font-weight: 600;
}
.pv-legend--stamp {
  color: var(--danger);
}
.pv-legend--edge {
  color: var(--accent);
}
.pv-src {
  margin: 4px 0;
  font-size: 12.5px;
}
.pv-src--warn {
  color: var(--warn);
}
.pv-notes {
  margin: 4px 0;
  padding-left: 18px;
  color: var(--fg-dim);
  font-size: 12.5px;
}
.pv-stage {
  position: relative;
  margin: 10px 0 6px;
  max-width: 100%;
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-inset);
}
.pv-img {
  display: block;
  width: 100%;
  height: auto;
}
.pv-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.pv-box {
  position: absolute;
  box-sizing: border-box;
  border: 2px solid transparent;
}
.pv-box--stamp {
  border-color: var(--danger);
}
.pv-box--edge {
  border-color: var(--accent);
}
.pv-imgstate {
  margin: 4px 0;
  font-size: 12.5px;
}
.pv-imgstate--err {
  color: var(--danger);
}
.pv-ok {
  color: var(--accent);
}
.pv-bad {
  color: var(--danger);
}
</style>
