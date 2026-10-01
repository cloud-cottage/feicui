<script setup>
// 缺失清单页：E5 GET /api/jobs/{job_id}/missing?kind=image|text
// 出参形状（spec §3.1 E5）：{kind, count, items[{pdf_name,page,idx,img_path?,reason}]}
// 纪律：本页只展示后端返回值，**不**自行复算 count（AC-06 / AC-07 的复算属验收侧动作）。
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { checkE5Shape, listMissing } from '@/api/jobs'
import { describeFailure } from '@/api/client'
import { MISSING_KINDS } from '@/config/constants'
import { useBackendStatus } from '@/composables/useBackendStatus'
import { nowStamp, rawBodyText } from '@/utils/format'
import StateNotice from '@/components/StateNotice.vue'

const route = useRoute()
const { markBackendDown } = useBackendStatus()

const jobId = computed(() => String(route.params.job_id || ''))
const kind = ref('image')
const body = ref(null)
const shapeNotes = ref([])
const fetchedAt = ref(null)
const status = ref({ kind: 'loading', statusCode: '', raw: '', detail: '' })

async function fetchMissing() {
  status.value = { kind: 'loading', statusCode: '', raw: '', detail: '' }
  try {
    const res = await listMissing(jobId.value, kind.value)
    fetchedAt.value = nowStamp()
    if (res.status === 200) {
      body.value = res.body
      shapeNotes.value = checkE5Shape(res.body).notes
      status.value = { kind: 'ok', statusCode: 200, raw: res.raw, detail: '' }
    } else if ([404, 405, 501].includes(res.status)) {
      body.value = null
      status.value = {
        kind: 'not-implemented',
        statusCode: res.status,
        raw: res.raw,
        detail: '后端尚未实现 E5（spec §3.1 已定义该端点）',
      }
    } else {
      body.value = null
      status.value = {
        kind: 'error',
        statusCode: res.status,
        raw: res.raw || rawBodyText(res.body),
        detail: 'E5 返回非 200（原样展示）',
      }
    }
  } catch (e) {
    const f = describeFailure(e)
    if (f.kind === 'backend-down') {
      markBackendDown(f.detail)
      body.value = null
      status.value = { kind: 'backend-down', statusCode: '', raw: '', detail: f.detail }
    } else {
      body.value = null
      status.value = { kind: 'error', statusCode: '', raw: '', detail: f.message }
    }
  }
}

watch([jobId, kind], fetchMissing, { immediate: true })

const items = computed(() => (body.value && Array.isArray(body.value.items) ? body.value.items : []))
</script>

<template>
  <section class="page">
    <header class="page__head">
      <h2>缺失清单 · E5</h2>
      <p class="page__sub">job_id ＝ <code>{{ jobId }}</code></p>
    </header>

    <div class="card">
      <div class="card__head">
        <h3>类型</h3>
        <button class="ghost" type="button" @click="fetchMissing">刷新</button>
      </div>
      <div class="field-row">
        <label v-for="k in MISSING_KINDS" :key="k.value" class="field field--check">
          <input v-model="kind" type="radio" :value="k.value" />
          <span>{{ k.label }}</span>
        </label>
      </div>
      <p class="muted">
        最近成功取数时点：{{ fetchedAt || '—' }} · 契约：
        <code>{kind, count, items[{pdf_name,page,idx,img_path?,reason}]}</code>
      </p>
    </div>

    <StateNotice
      v-if="status.kind === 'loading'"
      kind="loading"
      title="正在请求 E5 GET /api/jobs/{job_id}/missing …"
    />
    <StateNotice
      v-else-if="status.kind === 'backend-down'"
      kind="backend-down"
      title="后端未启动 / 未连接：E5 无法获取"
      :detail="`判负细节 ${status.detail || '—'}`"
    />
    <StateNotice
      v-else-if="status.kind === 'not-implemented'"
      kind="not-implemented"
      title="后端尚未提供该接口"
      :status-code="status.statusCode"
      :raw-text="status.raw"
      detail="E5（GET /api/jobs/{job_id}/missing）在 spec §3.1 已定义，但后端当前未实现（404/405/501）。本页不展示任何示例数据。"
    />
    <StateNotice
      v-else-if="status.kind === 'error'"
      kind="error"
      title="E5 请求失败（原样展示）"
      :status-code="status.statusCode"
      :raw-text="status.raw"
      :detail="status.detail"
    />

    <template v-else-if="status.kind === 'ok'">
      <div class="card">
        <h3>统计（后端原值）</h3>
        <div class="kv-row">
          <span>kind</span>
          <strong><code>{{ body && body.kind }}</code></strong>
        </div>
        <div class="kv-row">
          <span>count</span>
          <strong>{{ body && body.count }}</strong>
          <span class="muted">
            本页只展示后端返回值；<code>count</code> 与独立复算的一致性属 AC-06 / AC-07 的验收侧动作，本页不做替代复算。
          </span>
        </div>
        <ul v-if="shapeNotes.length" class="errlist">
          <li v-for="n in shapeNotes" :key="n">形状提示：{{ n }}</li>
        </ul>
      </div>

      <div class="card">
        <h3>缺失项（{{ items.length }} 条）</h3>
        <StateNotice v-if="!items.length" kind="empty" title="后端返回 0 条缺失项" />
        <table v-else class="table">
          <thead>
            <tr>
              <th>pdf_name</th>
              <th>page</th>
              <th>idx</th>
              <th>img_path</th>
              <th>reason</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(it, i) in items" :key="i">
              <td>{{ it.pdf_name || '—' }}</td>
              <td>{{ it.page === undefined ? '—' : it.page }}</td>
              <td>{{ it.idx === undefined ? '—' : it.idx }}</td>
              <td><code>{{ it.img_path === undefined || it.img_path === null ? '—' : it.img_path }}</code></td>
              <td>{{ it.reason || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card">
        <details>
          <summary>原始响应体（E5 全文，未改写）</summary>
          <pre>{{ status.raw }}</pre>
        </details>
      </div>
    </template>
  </section>
</template>
