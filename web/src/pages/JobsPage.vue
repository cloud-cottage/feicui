<script setup>
// 印谱解析：① 新建 job（E1 POST /api/jobs）② job 列表
// 约束：同书重复建 ⇒ 后端 409 + 既有 job_id **原样展示，不得吞**；
//       列表接口 spec §3 未定义（README §4 G-2）⇒ 「后端尚未提供该接口」+ 另列本机记录。
import { onMounted, computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { createJob, extractExistingJobId, listJobs } from '@/api/jobs'
import { describeFailure } from '@/api/client'
import { useBackendStatus } from '@/composables/useBackendStatus'
import {
  clearLocalJobs,
  forgetLocalJob,
  readLocalJobs,
  rememberLocalJob,
} from '@/api/localJobs'
import StateNotice from '@/components/StateNotice.vue'
import { NOT_IMPLEMENTED_STATUSES } from '@/config/constants'
import { nowStamp, rawBodyText } from '@/utils/format'

const router = useRouter()
const { markBackendDown } = useBackendStatus()

const form = reactive({ pdf_path: '', page_from: '', page_to: '', chunk_size: '', rerun: false })
const formErrors = ref([])
const submitting = ref(false)
const createResult = ref(null) // {kind:'ok'|'conflict'|'backend-down'|'error', ...}
const locals = ref([])

const jobsState = ref({ kind: 'loading', items: null, notes: [], status: null, raw: '', detail: '' })

function loadLocals() {
  locals.value = readLocalJobs()
}

function toInt(v) {
  const s = String(v).trim()
  if (s === '') return null
  if (!/^\d+$/.test(s)) return NaN
  return Number(s)
}

// 前端本地校验（**不是**后端 400 的替代品；后端仍会自己校验并可能回 400/422）
function validate() {
  const errs = []
  if (!form.pdf_path.trim()) errs.push('pdf_path 必填（书路径）')
  const from = toInt(form.page_from)
  const to = toInt(form.page_to)
  if (Number.isNaN(from) || Number.isNaN(to)) errs.push('页范围必须是正整数')
  if ((from === null) !== (to === null)) errs.push('页范围需同时给出 from 与 to（或都不填）')
  if (from !== null && to !== null && !Number.isNaN(from) && !Number.isNaN(to) && from > to) {
    errs.push('页范围 from 不得大于 to')
  }
  const cs = toInt(form.chunk_size)
  if (Number.isNaN(cs)) errs.push('chunk_size 必须是正整数')
  if (cs !== null && !Number.isNaN(cs) && cs <= 0) errs.push('chunk_size 必须大于 0')
  return errs
}

function buildPayload() {
  const from = toInt(form.page_from)
  const to = toInt(form.page_to)
  const cs = toInt(form.chunk_size)
  const payload = { pdf_path: form.pdf_path.trim() }
  if (from !== null && to !== null) payload.page_range = [from, to]
  if (cs !== null) payload.chunk_size = cs
  if (form.rerun) payload.rerun = true
  return payload
}

const lastPayload = ref(null)

async function submit() {
  formErrors.value = validate()
  if (formErrors.value.length) {
    createResult.value = null
    return
  }
  submitting.value = true
  createResult.value = null
  const payload = buildPayload()
  lastPayload.value = payload
  try {
    const res = await createJob(payload)
    if (res.status === 201 || (res.ok && res.body && res.body.job_id)) {
      createResult.value = {
        kind: 'ok',
        status: res.status,
        body: res.body,
        raw: res.raw || rawBodyText(res.body),
        at: nowStamp(),
      }
      if (res.body && res.body.job_id) {
        rememberLocalJob({
          job_id: res.body.job_id,
          pdf_path: payload.pdf_path,
          state: res.body.state,
          created_at: res.body.created_at,
        })
        loadLocals()
      }
    } else if (res.status === 409) {
      // **不得吞**：状态码、既有 job_id（启发式抽取）、原始 body 全部展示
      const existing = extractExistingJobId(res.body)
      createResult.value = {
        kind: 'conflict',
        status: 409,
        existingJobId: existing,
        body: res.body,
        raw: res.raw || rawBodyText(res.body),
        at: nowStamp(),
      }
    } else {
      createResult.value = {
        kind: 'error',
        status: res.status,
        body: res.body,
        raw: res.raw || rawBodyText(res.body),
        at: nowStamp(),
      }
    }
  } catch (e) {
    const f = describeFailure(e)
    if (f.kind === 'backend-down') {
      markBackendDown(f.detail)
      createResult.value = { kind: 'backend-down', detail: f.detail, at: nowStamp() }
    } else {
      createResult.value = { kind: 'error', detail: f.message, at: nowStamp() }
    }
  } finally {
    submitting.value = false
  }
}

async function loadJobs() {
  jobsState.value = { kind: 'loading', items: null, notes: [], status: null, raw: '', detail: '' }
  try {
    const res = await listJobs()
    if (res.status === 200) {
      const body = res.body
      if (body && Array.isArray(body.items)) {
        jobsState.value = {
          kind: 'ok',
          items: body.items,
          notes: ['来源＝后端 GET /api/jobs（spec §3 未定义该端点，形状未定；此处按 items[] 读取）'],
          status: 200,
          raw: res.raw,
          detail: '',
        }
      } else if (Array.isArray(body)) {
        jobsState.value = {
          kind: 'ok',
          items: body,
          notes: ['来源＝后端 GET /api/jobs，返回**裸数组**（形状未定，原样展示）'],
          status: 200,
          raw: res.raw,
          detail: '',
        }
      } else {
        jobsState.value = {
          kind: 'error',
          items: null,
          notes: [],
          status: 200,
          raw: res.raw,
          detail: '200 但响应体既不是数组、也没有 items 数组',
        }
      }
    } else if (NOT_IMPLEMENTED_STATUSES.includes(res.status)) {
      jobsState.value = {
        kind: 'not-implemented',
        items: null,
        notes: [],
        status: res.status,
        raw: res.raw,
        detail: '',
      }
    } else {
      jobsState.value = {
        kind: 'error',
        items: null,
        notes: [],
        status: res.status,
        raw: res.raw,
        detail: '',
      }
    }
  } catch (e) {
    const f = describeFailure(e)
    if (f.kind === 'backend-down') {
      markBackendDown(f.detail)
      jobsState.value = { kind: 'backend-down', items: null, notes: [], detail: f.detail }
    } else {
      jobsState.value = { kind: 'error', items: null, notes: [], detail: f.message }
    }
  }
}

onMounted(() => {
  loadLocals()
  loadJobs()
})

const conflictLinkId = computed(() =>
  createResult.value && createResult.value.kind === 'conflict' ? createResult.value.existingJobId : null
)
</script>

<template>
  <section class="page">
    <header class="page__head">
      <h2>印谱解析</h2>
      <p class="page__sub">
        新建 job 走 <code>E1 POST /api/jobs</code>；job 列表见下方两栏（后端接口 / 本机记录，来源分开标注）。
      </p>
    </header>

    <!-- ── 新建 job ─────────────────────────────────────────────── -->
    <div class="card">
      <h3>新建 job（E1）</h3>
      <form class="form" @submit.prevent="submit">
        <label class="field">
          <span class="field__label">书路径 pdf_path <em>*</em></span>
          <input v-model="form.pdf_path" type="text" placeholder="/绝对或相对路径/xxx.pdf" />
        </label>
        <div class="field-row">
          <label class="field">
            <span class="field__label">页范围 from（可选）</span>
            <input v-model="form.page_from" type="text" inputmode="numeric" placeholder="如 1" />
          </label>
          <label class="field">
            <span class="field__label">页范围 to（可选）</span>
            <input v-model="form.page_to" type="text" inputmode="numeric" placeholder="如 544" />
          </label>
          <label class="field">
            <span class="field__label">chunk_size（可选）</span>
            <input v-model="form.chunk_size" type="text" inputmode="numeric" placeholder="如 32" />
          </label>
          <label class="field field--check">
            <input v-model="form.rerun" type="checkbox" />
            <span>rerun（同书重跑，spec §2.4 幂等）</span>
          </label>
        </div>

        <ul v-if="formErrors.length" class="errlist">
          <li v-for="e in formErrors" :key="e">{{ e }}</li>
        </ul>

        <div class="actions">
          <button type="submit" :disabled="submitting">{{ submitting ? '提交中…' : '建 job' }}</button>
          <span v-if="lastPayload" class="muted">
            上次请求体：<code>{{ JSON.stringify(lastPayload) }}</code>
          </span>
        </div>
      </form>

      <!-- 201 成功 -->
      <StateNotice
        v-if="createResult && createResult.kind === 'ok'"
        kind="info"
        title="201 已建 job"
        :status-code="createResult.status"
        :raw-text="createResult.raw"
        :detail="`响应时点 ${createResult.at}`"
      >
        <p>
          job_id ＝ <code>{{ createResult.body && createResult.body.job_id }}</code>
          · state ＝ <code>{{ createResult.body && createResult.body.state }}</code>
          · total_pages ＝ <code>{{ createResult.body && createResult.body.total_pages }}</code>
          · created_at ＝ <code>{{ createResult.body && createResult.body.created_at }}</code>
        </p>
        <p>
          <RouterLink
            v-if="createResult.body && createResult.body.job_id"
            :to="`/jobs/${createResult.body.job_id}`"
            >→ 打开任务详情（E2 真实进度）</RouterLink
          >
        </p>
      </StateNotice>

      <!-- 409 冲突：**不吞** -->
      <StateNotice
        v-if="createResult && createResult.kind === 'conflict'"
        kind="conflict"
        title="409 冲突：同一 pdf_path 已存在活跃 job —— 后端拒绝再起第二个同书 job（spec §3.2 S-5）"
        :status-code="createResult.status"
        :raw-text="createResult.raw"
        :detail="`响应时点 ${createResult.at}；既有 job_id 的抽取为启发式（spec 未定 409 的 body 形状，见 README §4 G-3）`"
      >
        <p v-if="conflictLinkId">
          后端给出的既有 job_id ＝ <code>{{ conflictLinkId }}</code>
          · <RouterLink :to="`/jobs/${conflictLinkId}`">→ 打开该既有 job</RouterLink>
        </p>
        <p v-else>
          <strong>未能从响应体中认出既有 job_id</strong>（原始 body 见下方折叠区，未做任何猜测）。
        </p>
      </StateNotice>

      <StateNotice
        v-if="createResult && createResult.kind === 'backend-down'"
        kind="backend-down"
        title="后端未启动 / 未连接：E1 未能发出"
        :detail="`判负细节 ${createResult.detail || '—'}；时点 ${createResult.at}`"
      />

      <StateNotice
        v-if="createResult && createResult.kind === 'error' && !createResult.status"
        kind="error"
        title="请求失败"
        :detail="`${createResult.detail || ''}；时点 ${createResult.at}`"
      />

      <StateNotice
        v-if="createResult && createResult.kind === 'error' && createResult.status"
        kind="error"
        title="后端返回错误（原样展示）"
        :status-code="createResult.status"
        :raw-text="createResult.raw"
        :detail="`响应时点 ${createResult.at}`"
      />
    </div>

    <!-- ── job 列表：后端 ────────────────────────────────────────── -->
    <div class="card">
      <div class="card__head">
        <h3>job 列表（后端）</h3>
        <button class="ghost" type="button" @click="loadJobs">刷新</button>
      </div>

      <StateNotice
        v-if="jobsState.kind === 'loading'"
        kind="loading"
        title="正在请求后端 GET /api/jobs …"
      />
      <StateNotice
        v-else-if="jobsState.kind === 'backend-down'"
        kind="backend-down"
        title="后端未启动 / 未连接：列表无法获取"
        :detail="`判负细节 ${jobsState.detail || '—'}`"
      />
      <StateNotice
        v-else-if="jobsState.kind === 'not-implemented'"
        kind="not-implemented"
        title="后端尚未提供该接口"
        :status-code="jobsState.status"
        :raw-text="jobsState.raw"
        detail="spec §3.1 只定义了 E1（POST /api/jobs）等 5 个端点，未定义「列 job」端点；本页不发明契约，列表一栏留空并另列本机记录。"
      />
      <StateNotice
        v-else-if="jobsState.kind === 'error'"
        kind="error"
        title="列表接口报错（原样展示）"
        :status-code="jobsState.status || ''"
        :raw-text="jobsState.raw"
        :detail="jobsState.detail || '响应形状不符合预期'"
      />
      <template v-else-if="jobsState.kind === 'ok'">
        <p v-for="n in jobsState.notes" :key="n" class="muted">{{ n }}</p>
        <table v-if="jobsState.items.length" class="table">
          <thead>
            <tr>
              <th>job_id</th>
              <th>state</th>
              <th>total_pages</th>
              <th>created_at</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="j in jobsState.items" :key="j.job_id">
              <td><code>{{ j.job_id }}</code></td>
              <td><code>{{ j.state || '—' }}</code></td>
              <td>{{ j.total_pages === undefined ? '—' : j.total_pages }}</td>
              <td>{{ j.created_at || '—' }}</td>
              <td>
                <RouterLink :to="`/jobs/${j.job_id}`">详情</RouterLink>
                ·
                <RouterLink :to="`/jobs/${j.job_id}/results`">结果</RouterLink>
                ·
                <RouterLink :to="`/jobs/${j.job_id}/missing`">缺失清单</RouterLink>
              </td>
            </tr>
          </tbody>
        </table>
        <StateNotice v-else kind="empty" title="后端列表为空（0 条 job）" />
      </template>
    </div>

    <!-- ── job 列表：本机记录（来源明确标注） ────────────────────── -->
    <div class="card card--local">
      <div class="card__head">
        <h3>本浏览器本地记录（localStorage）</h3>
        <button class="ghost" type="button" @click="locals = clearLocalJobs()">清空</button>
      </div>
      <p class="muted">
        **不是后端真值**：仅记录本机 E1 建 job 成功时拿到的
        <code>{job_id, state, total_pages, created_at}</code>，用于在「后端列表接口尚未提供」时仍有入口。
        与上面一栏严格分开，不得混用。
      </p>
      <table v-if="locals.length" class="table">
        <thead>
          <tr>
            <th>job_id</th>
            <th>pdf_path（请求体）</th>
            <th>state</th>
            <th>created_at</th>
            <th>记录时点</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="j in locals" :key="j.job_id">
            <td><code>{{ j.job_id }}</code></td>
            <td>{{ j.pdf_path || '—' }}</td>
            <td>{{ j.state || '—' }}</td>
            <td>{{ j.created_at || '—' }}</td>
            <td>{{ j.recorded_at || '—' }}</td>
            <td>
              <RouterLink :to="`/jobs/${j.job_id}`">详情</RouterLink>
              ·
              <button class="linkish" type="button" @click="locals = forgetLocalJob(j.job_id)">移除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <StateNotice v-else kind="empty" title="本机暂无记录" detail="尚未在本浏览器成功建过 job。" />
    </div>
  </section>
</template>
