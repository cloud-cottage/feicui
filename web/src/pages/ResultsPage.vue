<script setup>
// 结果页（**预留**）：E3 GET /api/jobs/{job_id}/stamps?page=&limit=&cursor=
// 严格按 spec §3.1 / §3.2 S-3 的 **6 字段信封**：
//   {items[], page, limit, total, has_more, next_cursor}
//   - items 为实体数组（不得裸数组）、page 1-based、limit ↔ 平台 pageSize、
//     has_more 布尔、next_cursor 无下一页时 **null**
// 后端未提供该接口 ⇒ 显示「后端尚未提供该接口」，**不空白、不造假**。
//
// 裁图取用 = **E6 正式契约**（spec v1.3 §3.5）：GET /api/jobs/{job_id}/stamps/{page}/{idx}/image
//   - **3 段**路径（page 与 idx 都必给）；路径常量集中在 `@/api/stampsImage`（一处收口）；
//   - 锚点 (page, idx) 取自 items：`sourcePageNo`（§3.12 #8 冻结）+ `feicui.stampIdx`（形状真源）；
//   - 取不到 ⇒ 显示「裁图不可用」+ **真实原因码**，**绝不用占位图冒充**。
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { checkE3Envelope, listStamps } from '@/api/jobs'
import { describeFailure } from '@/api/client'
import { E3_ENVELOPE_KEYS } from '@/config/constants'
import { useBackendStatus } from '@/composables/useBackendStatus'
import {
  E6_REASON_TEXT,
  STAMP_IMAGE_CONTRACT_NOTE,
  STAMP_IMAGE_PATH_TEMPLATE,
  decodeHeaderValue,
  probeStampImage,
  stampAnchorOf,
} from '@/api/stampsImage'
import { isNil, nilDash, nowStamp, rawBodyText } from '@/utils/format'
import StateNotice from '@/components/StateNotice.vue'

const route = useRoute()
const { markBackendDown } = useBackendStatus()

const jobId = computed(() => String(route.params.job_id || ''))
const page = ref(1)
const limit = ref(20)
const cursor = ref('')
const envelope = ref(null)
const shape = ref({ ok: true, problems: [], extraKeys: [] })
const status = ref({ kind: 'loading', statusCode: '', raw: '', detail: '' })
const fetchedAt = ref(null)

// E6 取图状态：key = itemKey(it, i) → {state, url, status?, code?, note?}
const imageState = ref({})

// items 元素 → E6 锚点（缺锚点即如实报缺，不猜、不用废止的 2 段路径兜底）
function itemAnchor(it) {
  return stampAnchorOf(it)
}

function itemKey(it, i) {
  const a = itemAnchor(it)
  return a.ok ? `${a.page}-${a.idx}` : `row-${i}`
}

async function tryLoadImage(it, i) {
  const key = itemKey(it, i)
  const a = itemAnchor(it)
  if (!a.ok) {
    imageState.value = { ...imageState.value, [key]: { state: 'no-anchor', note: a.note } }
    return
  }
  imageState.value = { ...imageState.value, [key]: { state: 'loading' } }
  const r = await probeStampImage(jobId.value, a.page, a.idx)
  imageState.value = { ...imageState.value, [key]: r }
}

function reasonText(st) {
  if (!st) return ''
  if (st.code && E6_REASON_TEXT[st.code]) return `${st.code}—— ${E6_REASON_TEXT[st.code]}`
  return st.code || ''
}

async function fetchStamps() {
  status.value = { kind: 'loading', statusCode: '', raw: '', detail: '' }
  try {
    const res = await listStamps(jobId.value, {
      page: page.value,
      limit: limit.value,
      cursor: cursor.value || undefined,
    })
    fetchedAt.value = nowStamp()
    if (res.status === 200) {
      envelope.value = res.body
      shape.value = checkE3Envelope(res.body)
      status.value = { kind: 'ok', statusCode: 200, raw: res.raw, detail: '' }
    } else if ([404, 405, 501].includes(res.status)) {
      envelope.value = null
      status.value = {
        kind: 'not-implemented',
        statusCode: res.status,
        raw: res.raw,
        detail: '后端尚未实现 E3（spec §3.1 已定义该端点）',
      }
    } else {
      envelope.value = null
      status.value = {
        kind: 'error',
        statusCode: res.status,
        raw: res.raw || rawBodyText(res.body),
        detail: 'E3 返回非 200（原样展示）',
      }
    }
  } catch (e) {
    const f = describeFailure(e)
    if (f.kind === 'backend-down') {
      markBackendDown(f.detail)
      envelope.value = null
      status.value = { kind: 'backend-down', statusCode: '', raw: '', detail: f.detail }
    } else {
      envelope.value = null
      status.value = { kind: 'error', statusCode: '', raw: '', detail: f.message }
    }
  }
}

watch([jobId, page, limit, cursor], fetchStamps, { immediate: true })

const items = computed(() => {
  const b = envelope.value
  return b && Array.isArray(b.items) ? b.items : []
})

// 分页控件：以信封字段为准（next_cursor 优先于页码）
const canNext = computed(() => {
  const b = envelope.value
  if (!b) return false
  return b.has_more === true
})

function nextPage() {
  const b = envelope.value
  if (!b) return
  if (b.next_cursor !== null && b.next_cursor !== undefined) {
    cursor.value = String(b.next_cursor)
  } else {
    page.value += 1
    cursor.value = ''
  }
}

function prevPage() {
  cursor.value = ''
  if (page.value > 1) page.value -= 1
}
</script>

<template>
  <section class="page">
    <header class="page__head">
      <h2>结果页（预留）· E3</h2>
      <p class="page__sub">
        job_id ＝ <code>{{ jobId }}</code> · 契约形状＝ 6 字段信封
        <code v-for="k in E3_ENVELOPE_KEYS" :key="k" class="chip">{{ k }}</code>
      </p>
    </header>

    <div class="card">
      <div class="card__head">
        <h3>分页参数</h3>
        <button class="ghost" type="button" @click="fetchStamps">刷新</button>
      </div>
      <div class="field-row">
        <label class="field field--sm">
          <span class="field__label">page（1-based）</span>
          <input v-model.number="page" type="number" min="1" />
        </label>
        <label class="field field--sm">
          <span class="field__label">limit</span>
          <select v-model.number="limit">
            <option :value="10">10</option>
            <option :value="20">20</option>
            <option :value="50">50</option>
            <option :value="100">100</option>
          </select>
        </label>
        <label class="field field--sm">
          <span class="field__label">cursor（可选，E3 游标）</span>
          <input v-model="cursor" type="text" placeholder="留空＝按 page 取" />
        </label>
      </div>
      <p class="muted">最近成功取数时点：{{ fetchedAt || '—' }}</p>
    </div>

    <StateNotice
      v-if="status.kind === 'loading'"
      kind="loading"
      title="正在请求 E3 GET /api/jobs/{job_id}/stamps …"
    />
    <StateNotice
      v-else-if="status.kind === 'backend-down'"
      kind="backend-down"
      title="后端未启动 / 未连接：E3 无法获取"
      :detail="`判负细节 ${status.detail || '—'}`"
    />
    <StateNotice
      v-else-if="status.kind === 'not-implemented'"
      kind="not-implemented"
      title="后端尚未提供该接口"
      :status-code="status.statusCode"
      :raw-text="status.raw"
      detail="E3（GET /api/jobs/{job_id}/stamps）在 spec §3.1 已定义，但后端当前未实现（404/405/501）。本页不展示任何示例数据。"
    />
    <StateNotice
      v-else-if="status.kind === 'error'"
      kind="error"
      title="E3 请求失败（原样展示）"
      :status-code="status.statusCode"
      :raw-text="status.raw"
      :detail="status.detail"
    />

    <template v-else-if="status.kind === 'ok'">
      <div v-if="!shape.ok" class="notice notice--warn">
        <strong>信封形状与 spec §3.2 S-3 不符（判负形态，如实上报）：</strong>
        <ul>
          <li v-for="p in shape.problems" :key="p">{{ p }}</li>
        </ul>
      </div>
      <div v-else-if="shape.extraKeys.length" class="notice notice--warn">
        信封含**未定义字段**（S-3 判负形态之一）：<code>{{ shape.extraKeys.join(', ') }}</code>
      </div>

      <div class="card">
        <h3>信封字段（后端原值）</h3>
        <table class="kv">
          <tbody>
            <tr v-for="k in E3_ENVELOPE_KEYS" :key="k">
              <th><code>{{ k }}</code></th>
              <td>
                <template v-if="k === 'items'">
                  {{ Array.isArray(envelope && envelope.items) ? `数组 · ${envelope.items.length} 条` : '（非数组）' }}
                </template>
                <template v-else-if="k === 'next_cursor'">
                  {{ envelope && envelope.next_cursor === null ? 'null（无下一页）' : nilDash(envelope && envelope.next_cursor) }}
                </template>
                <template v-else>{{ nilDash(envelope && envelope[k]) }}</template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card">
        <h3>items（{{ items.length }} 条）</h3>
        <StateNotice v-if="!items.length" kind="empty" title="本页 items 为空数组（total＝{{ nilDash(envelope && envelope.total) }}）" />
        <table v-else class="table">
          <thead>
            <tr>
              <th>pdf_name</th>
              <th>page<br /><span class="muted">sourcePageNo</span></th>
              <th>idx<br /><span class="muted">feicui.stampIdx</span></th>
              <th>text</th>
              <th>img_path</th>
              <th>bbox (x1,y1,x2,y2)</th>
              <th>裁图（E6）</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(it, i) in items" :key="i">
              <!-- 取值键路径（spec §3.12 / 形状真源 export.py::build_record）：本书名在 `feicui.pdfName`，
                   顶层并无 `pdf_name`（旧实现读顶层 ⇒ 整列显示 `—`，本单只改键路径，列名不动）。 -->
              <td>{{ (it.feicui && it.feicui.pdfName) || '—' }}</td>
              <td>{{ itemAnchor(it).page === null ? '—' : itemAnchor(it).page }}</td>
              <td>{{ itemAnchor(it).idx === null ? '—' : itemAnchor(it).idx }}</td>
              <td>{{ it.text === null || it.text === undefined || it.text === '' ? '（空）' : it.text }}</td>
              <!-- 源影像路径在 `assets[0].sourceImgPath`（顶层无 `img_path`；`assets[].imgPath` 是导出件路径，本轮不用）。
                   `assets[]` 为空 ⇒ 如实 `—`，不造值。 -->
              <td><code>{{ (it.assets && it.assets[0] && it.assets[0].sourceImgPath) || '—' }}</code></td>
              <!-- 坐标在顶层 `bbox` 对象（`bbox.x1..y2`）；bbox 缺失 ⇒ 如实 `—`，不造值。 -->
              <td>
                <code v-if="it.bbox && !isNil(it.bbox.x1)">{{ it.bbox.x1 }},{{ it.bbox.y1 }},{{ it.bbox.x2 }},{{ it.bbox.y2 }}</code>
                <span v-else>—</span>
              </td>
              <td>
                <button class="ghost" type="button" @click="tryLoadImage(it, i)">取裁图</button>
                <div v-if="imageState[itemKey(it, i)]" class="muted">
                  <template v-if="imageState[itemKey(it, i)].state === 'loading'">请求中…</template>
                  <template v-else-if="imageState[itemKey(it, i)].state === 'ok'">
                    <img class="stampimg" :src="imageState[itemKey(it, i)].url" alt="印面裁图" />
                    <div>
                      真实裁图 · {{ imageState[itemKey(it, i)].contentType || '（无 Content-Type）' }} ·
                      <code>{{ decodeHeaderValue(imageState[itemKey(it, i)].imgPath) || '（无 x-feicui-img-path）' }}</code>
                    </div>
                  </template>
                  <template v-else-if="imageState[itemKey(it, i)].state === 'unavailable'">
                    裁图不可用：{{ reasonText(imageState[itemKey(it, i)]) || 'HTTP ' + imageState[itemKey(it, i)].status }}
                    （本行不显示占位图）
                  </template>
                  <template v-else-if="imageState[itemKey(it, i)].state === 'bad-param'">
                    取图参数非法：{{ reasonText(imageState[itemKey(it, i)]) || 'HTTP 400' }}
                  </template>
                  <template v-else-if="imageState[itemKey(it, i)].state === 'no-anchor'">
                    裁图不可用：{{ imageState[itemKey(it, i)].note }}
                  </template>
                  <template v-else>
                    裁图取用失败（{{ imageState[itemKey(it, i)].state }}{{ imageState[itemKey(it, i)].status ? ' / HTTP ' + imageState[itemKey(it, i)].status : '' }}）。
                  </template>
                </div>
              </td>
            </tr>
          </tbody>
        </table>

        <div class="pager">
          <button class="ghost" type="button" :disabled="page <= 1 && !cursor" @click="prevPage">← 上一页</button>
          <span class="muted">
            page={{ nilDash(envelope && envelope.page) }} · limit={{ nilDash(envelope && envelope.limit) }} ·
            total={{ nilDash(envelope && envelope.total) }} · has_more={{ String(envelope && envelope.has_more) }} ·
            next_cursor={{ envelope && envelope.next_cursor === null ? 'null' : nilDash(envelope && envelope.next_cursor) }}
          </span>
          <button class="ghost" type="button" :disabled="!canNext" @click="nextPage">下一页 →</button>
        </div>
      </div>

      <div class="card card--gap">
        <h3>取图契约 · E6（**正式契约**，spec v1.3 §3.5）</h3>
        <p class="muted">
          <code>GET {{ STAMP_IMAGE_PATH_TEMPLATE }}</code> —— **3 段**路径，<code>{page}</code> 1-based、
          <code>{idx}</code> 0-based，**两者都必给**（行级唯一锚＝<code>(pdf_name,page,idx)</code>）。
          本页锚点取自 items 的 <code>sourcePageNo</code> 与 <code>feicui.stampIdx</code>；
          路径常量集中在 <code>src/api/stampsImage.js</code>（一处收口，页面不硬编码）。
        </p>
        <p class="muted">{{ STAMP_IMAGE_CONTRACT_NOTE }}</p>
        <p class="muted">
          取图失败一律**如实显示**「裁图不可用」+ 原因码，**不用占位图 / 示例图冒充**。
        </p>
      </div>

      <div class="card">
        <details>
          <summary>原始响应体（E3 全文，未改写）</summary>
          <pre>{{ status.raw }}</pre>
        </details>
      </div>
    </template>
  </section>
</template>
