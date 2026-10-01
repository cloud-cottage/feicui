<script setup>
// 任务详情页：E2 GET /api/jobs/{job_id} 轮询展示**真实进度**。
//
// ★ S-1（spec §3.2）纪律，页内明文标注：
//   进度条宽度 = 后端返回的 done_pages / total_pages（**库内复算值**）；
//   前端**没有任何**计时器 / 估算 / 插值在推进进度；定时器只负责「重新取数」。
//   total_pages 缺失或 ≤0 ⇒ 不画进度，显示 `—`。
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { checkE2Shape, getJob } from '@/api/jobs'
import { describeFailure } from '@/api/client'
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
          <RouterLink to="/">返回任务页</RouterLink>
        </p>
      </div>
    </template>
  </section>
</template>
