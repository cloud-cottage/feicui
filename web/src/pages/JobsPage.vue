<script setup>
// 印谱解析：① 新建 job（E1 POST /api/jobs）② job 列表
// 约束：同书重复建 ⇒ 后端 409 + 既有 job_id **原样展示，不得吞**；
//       列表接口 spec §3 未定义（README §4 G-2）⇒ 「后端尚未提供该接口」+ 另列本机记录。
import { onMounted, computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { createJob, extractExistingJobId, inboxGc, inboxSummary, listJobs } from '@/api/jobs'
import { describeFailure } from '@/api/client'
import { uploadPdf } from '@/api/upload'
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
  if (!form.pdf_path.trim()) errs.push('pdf_path 必填：请拖入 PDF 上传，或展开「高级」手输服务器路径')
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

// ─────────────────────────────────────────────────────────────────────────────
// 拖曳上传（**additive** POST /api/jobs/upload）—— 浏览器事实：拖入 / 选中的 File
// **不带本地路径** ⇒ 必须先上传到服务器拿服务器侧路径，再把该路径填进表单喂 E1。
// 本段**不动** E1 的调用与 409 处理：提交仍走原 `createJob`。
// ─────────────────────────────────────────────────────────────────────────────
const dragged = ref(false)
const fileInputEl = ref(null)
const uploadState = ref({ kind: 'idle' }) // idle | uploading | ok | error
const uploadPercent = ref(0)
const uploadFile = ref(null) // {name,size}
const uploadError = ref('')
const uploaded = ref(null) // 服务器响应（含 pdf_path / sha256 / idempotent / dedup_suffix）

function fmtBytes(n) {
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

function pickFile() {
  if (uploadState.value.kind === 'uploading') return
  if (fileInputEl.value) fileInputEl.value.click()
}

function onFileInput(e) {
  const f = e.target.files && e.target.files[0]
  if (f) handleFile(f)
  e.target.value = '' // 允许再次选同一个文件
}

function onDragOver() {
  dragged.value = true
}

function onDragLeave() {
  dragged.value = false
}

function onDrop(e) {
  dragged.value = false
  const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]
  if (f) handleFile(f)
}

function clearUpload() {
  uploaded.value = null
  uploadFile.value = null
  uploadState.value = { kind: 'idle' }
  uploadPercent.value = 0
  uploadError.value = ''
  form.pdf_path = ''
}

async function handleFile(file) {
  uploadError.value = ''
  uploaded.value = null
  uploadPercent.value = 0
  uploadFile.value = { name: file.name || '（无文件名）', size: file.size }
  // ① 先看扩展名。**不是**后端判据的替代品：服务器仍按 `%PDF-` 魔数复核，
  //    可能回 400 NOT_A_PDF（下方「上传被拒」分支会把错误码原样显示）。
  if (!/\.pdf$/i.test(file.name || '')) {
    uploadState.value = { kind: 'error' }
    uploadError.value = `只接受 .pdf 文件（选中的是「${file.name || '无文件名'}」）——未发出上传请求。`
    return
  }
  // ② 上传未落定前先清空表单值：宁可空，也不让上一次的路径被误提交
  form.pdf_path = ''
  uploadState.value = { kind: 'uploading' }
  try {
    const res = await uploadPdf(file, {
      onProgress: (loaded, total) => {
        uploadPercent.value = total ? Math.min(100, Math.round((loaded / total) * 100)) : 0
      },
    })
    if (!res.ok || !res.body || !res.body.pdf_path) {
      uploadState.value = { kind: 'error' }
      const code = res.body && (res.body.error || res.body.detail)
      uploadError.value = `上传被拒：HTTP ${res.status}${code ? ` · ${code}` : ''}${
        res.raw ? ` · ${res.raw.slice(0, 300)}` : ''
      }`
      return
    }
    uploaded.value = res.body
    form.pdf_path = res.body.pdf_path // ← 填进表单；提交仍走原 E1（契约一字未改）
    uploadState.value = { kind: 'ok' }
  } catch (e) {
    const f = describeFailure(e)
    uploadState.value = { kind: 'error' }
    if (f.kind === 'backend-down') {
      markBackendDown(f.detail)
      uploadError.value = `后端未启动 / 未连接：上传未能发出（${f.detail || '—'}）`
    } else {
      uploadError.value = `上传失败：${f.message}`
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// inbox 用量 / 清理（**additive**，R41）—— 口径：**默认 dry-run**、两段式、**永不自动删**；
// 执行清理前**二次确认**并明示将删多少 GiB。色值只走 token，不新造图标。
// ─────────────────────────────────────────────────────────────────────────────
const inbox = ref({ kind: 'loading', data: null, error: '' })     // kind: loading|ok|error|backend-down
const inboxAction = ref({ kind: 'idle', message: '' })            // idle|busy|ok|error

function fmtGiB(n) {
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—'
  return (n / 1024 ** 3).toFixed(2)
}

const inboxReclaimable = computed(() => {
  const d = inbox.value.data
  if (!d) return { files: 0, bytes: 0 }
  return { files: d.collect_files || 0, bytes: d.collect_bytes || 0 }
})

function inboxErrText(res) {
  const code = res.body && (res.body.error || res.body.detail)
  return `HTTP ${res.status}${code ? ` · ${code}` : ''}${res.raw ? ` · ${String(res.raw).slice(0, 260)}` : ''}`
}

async function loadInbox() {
  inbox.value = { kind: 'loading', data: null, error: '' }
  try {
    const res = await inboxSummary()
    if (res.status === 200 && res.body && res.body.usage) {
      inbox.value = { kind: 'ok', data: res.body, error: '' }
    } else {
      inbox.value = { kind: 'error', data: null, error: inboxErrText(res) }
    }
  } catch (e) {
    const f = describeFailure(e)
    if (f.kind === 'backend-down') {
      markBackendDown(f.detail)
      inbox.value = { kind: 'backend-down', data: null, error: f.detail || '' }
    } else {
      inbox.value = { kind: 'error', data: null, error: f.message }
    }
  }
}

// 预览清理：**dry-run**（POST apply:false），只列清单、绝不改盘
async function previewClean() {
  inboxAction.value = { kind: 'busy', message: '正在预览（dry-run）…' }
  try {
    const res = await inboxGc(false)
    if (res.status === 200 && res.body && res.body.usage) {
      inbox.value = { kind: 'ok', data: res.body, error: '' }
      const d = res.body
      inboxAction.value = {
        kind: 'ok',
        message: `预览完成（dry-run，未改盘）：将回收 ${d.collect_files} 文件 / ${fmtGiB(d.collect_bytes)} GiB；豁免 ${d.exempt_files} 文件`,
      }
    } else {
      inboxAction.value = { kind: 'error', message: `预览失败：${inboxErrText(res)}` }
    }
  } catch (e) {
    const f = describeFailure(e)
    if (f.kind === 'backend-down') {
      markBackendDown(f.detail)
      inboxAction.value = { kind: 'error', message: `后端未启动 / 未连接：预览未能发出（${f.detail || '—'}）` }
    } else {
      inboxAction.value = { kind: 'error', message: `预览失败：${f.message}` }
    }
  }
}

// 执行清理：**二次确认**（明示将删多少 GiB）⇒ 才真移入 inbox/.trash/
async function executeClean() {
  const d = inbox.value.data
  const files = d ? d.collect_files || 0 : 0
  const gib = d ? fmtGiB(d.collect_bytes) : '—'
  const hardFiles = d ? d.hard_delete_files || 0 : 0
  const hardGib = d ? fmtGiB(d.hard_delete_bytes) : '0.00'
  const lines = [
    '确认执行 inbox 清理？',
    '',
    `· 将把 ${files} 个文件（约 ${gib} GiB）移入 inbox/.trash/<yyyymmdd>/（**可回滚**）。`,
  ]
  if (hardFiles > 0) lines.push(`· 另有 trash 内 ${hardFiles} 个已过宽限期的文件（约 ${hardGib} GiB）将被**硬删**（不可回滚）。`)
  lines.push('', '被活跃 job 引用的文件永不回收；系统永不自动删——此操作由你显式触发。')
  if (!window.confirm(lines.join('\n'))) return

  inboxAction.value = { kind: 'busy', message: '正在执行清理…' }
  try {
    const res = await inboxGc(true)
    if (res.status === 200 && res.body && res.body.usage) {
      inbox.value = { kind: 'ok', data: res.body, error: '' }
      const a = res.body
      inboxAction.value = {
        kind: 'ok',
        message: `清理完成：已移入 trash ${a.moved_files} 文件 / ${fmtGiB(a.moved_bytes)} GiB（回滚点 ${a.trash_dir}）` +
          (a.hard_deleted_files ? `；硬删 ${a.hard_deleted_files} 文件 / ${fmtGiB(a.hard_deleted_bytes)} GiB` : '') +
          (a.errors && a.errors.length ? `；⚠ ${a.errors.length} 条错误（见报告）` : ''),
      }
    } else {
      inboxAction.value = { kind: 'error', message: `清理失败：${inboxErrText(res)}` }
    }
  } catch (e) {
    const f = describeFailure(e)
    if (f.kind === 'backend-down') {
      markBackendDown(f.detail)
      inboxAction.value = { kind: 'error', message: `后端未启动 / 未连接：清理未能发出（${f.detail || '—'}）` }
    } else {
      inboxAction.value = { kind: 'error', message: `清理失败：${f.message}` }
    }
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
  loadInbox()
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
        <div class="field">
          <span class="field__label">书路径 pdf_path <em>*</em>（拖入 PDF 上传）</span>
          <div
            class="dropzone"
            :class="{ 'dropzone--over': dragged, 'dropzone--busy': uploadState.kind === 'uploading' }"
            role="button"
            tabindex="0"
            title="拖入 .pdf 文件，或点击选择文件"
            @click="pickFile"
            @keydown.enter.prevent="pickFile"
            @keydown.space.prevent="pickFile"
            @dragover.prevent="onDragOver"
            @dragenter.prevent="onDragOver"
            @dragleave.prevent="onDragLeave"
            @drop.prevent="onDrop"
          >
            <p class="dropzone__title">
              {{ uploadState.kind === 'uploading' ? '上传中…' : '拖入 PDF 文件，或点击此处选择文件' }}
            </p>
            <p class="dropzone__hint">
              上传后自动落盘到 <code>inbox/&lt;yyyymmdd&gt;/&lt;原文件名&gt;.pdf</code>，并把服务器侧路径自动填进表单（无需手输路径）。
            </p>
            <input
              ref="fileInputEl"
              class="dropzone__file"
              type="file"
              accept="application/pdf,.pdf"
              @change="onFileInput"
            />
          </div>
        </div>

        <!-- 上传进度：372 MB 必须有反馈（fetch 给不了上传进度 ⇒ api/upload.js 用 XHR） -->
        <div v-if="uploadState.kind === 'uploading'" class="uploadbox">
          <div class="progress"><div class="progress__bar" :style="{ width: uploadPercent + '%' }"></div></div>
          <p class="muted">
            上传中 {{ uploadPercent }}% ·
            <code>{{ uploadFile && uploadFile.name }}</code>（{{ fmtBytes(uploadFile && uploadFile.size) }}）
          </p>
        </div>

        <!-- 上传成功：只读回显服务器侧 pdf_path ＋ 源文件名 / 体积 / 已就绪 -->
        <div v-else-if="uploadState.kind === 'ok'" class="uploadbox uploadbox--ok">
          <p>
            <strong>已就绪</strong>：源文件 <code>{{ uploadFile && uploadFile.name }}</code>
            （{{ fmtBytes(uploadFile && uploadFile.size) }}）已落盘到服务器。
          </p>
          <p>
            服务器侧落点（只读）<code>{{ uploaded && uploaded.pdf_path }}</code>
            ｜ 提交 E1 用的 <code>pdf_path</code> ＝ <code>{{ form.pdf_path || '（空）' }}</code>
            <span class="muted">（若在下方「高级」里手改，以表单值为准）</span>
          </p>
          <p class="muted">
            sha256 <code>{{ uploaded && uploaded.sha256 }}</code> ·
            {{ uploaded && uploaded.bytes }} B ·
            {{ uploaded && uploaded.idempotent ? '幂等：同名同内容，未重写' : '新写入' }}
            <template v-if="uploaded && uploaded.dedup_suffix">· 同名异内容 ⇒ 已落 <code>-&lt;sha8&gt;</code> 后缀（原文件未被覆盖）</template>
          </p>
          <button class="ghost" type="button" @click="clearUpload">清除，重新选择</button>
        </div>

        <!-- 上传失败：**可见**错误文案（不得静默） -->
        <div v-else-if="uploadState.kind === 'error'" class="uploadbox uploadbox--err">
          <p><strong>上传未成功</strong>：{{ uploadError }}</p>
          <p class="muted">
            本端不是判据：扩展名 / 体积上限 / <code>%PDF-</code> 魔数一律以服务器复核为准
            （<code>400 EMPTY_BODY</code> / <code>400 NOT_A_PDF</code> / <code>413 PAYLOAD_TOO_LARGE</code>）。
          </p>
        </div>

        <!-- 折叠：高级手输服务器路径（**默认收起**，兼容既有流程）。
             ⚠ 标题按 §3.19.5 / AC-70 **逐字**「高级：手输服务器路径」——不得加后缀。 -->
        <details class="advanced">
          <summary>高级：手输服务器路径</summary>
          <label class="field">
            <span class="field__label">书路径 pdf_path（绝对或相对 feicui/；供服务器上已有路径直接输入）</span>
            <input v-model="form.pdf_path" type="text" placeholder="/绝对或相对路径/xxx.pdf" />
          </label>
        </details>
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
          <button type="submit" :disabled="submitting || uploadState.kind === 'uploading'">{{ submitting ? '提交中…' : '建 job' }}</button>
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

    <!-- ── inbox 用量 / 清理（**additive**，R41）─────────────────────────────
         口径真源 docs/inbox-gc-draft-v0.1.md：**默认 dry-run**、两段式（先入 .trash 可回滚）、
         **永不自动删**（真删只能由人显式触发）。色值只走 token，不新造图标。 -->
    <div class="card">
      <div class="card__head">
        <h3>inbox 用量 / 清理（R41）</h3>
        <button class="ghost" type="button" @click="loadInbox">刷新</button>
      </div>
      <p class="muted">
        【预览清理】＝ dry-run（只列清单，**不改盘**）；【执行清理】前**二次确认**，确认框内**明示将删多少 GiB**。
        被**活跃 job**（QUEUED/RUNNING/PAUSED）引用的文件**永不回收**；先移入
        <code>inbox/.trash/&lt;yyyymmdd&gt;/</code>（可回滚），trash 内再满 7 天才硬删。系统**永不自动删**。
      </p>

      <StateNotice v-if="inbox.kind === 'loading'" kind="loading" title="正在读取 inbox 用量 …" />
      <StateNotice
        v-else-if="inbox.kind === 'backend-down'"
        kind="backend-down"
        title="后端未启动 / 未连接：inbox 用量无法获取"
        :detail="inbox.error || '—'"
      />
      <StateNotice
        v-else-if="inbox.kind === 'error'"
        kind="error"
        title="inbox 用量读取失败（原样展示）"
        :detail="inbox.error || '响应形状不符合预期'"
      />

      <template v-else-if="inbox.kind === 'ok' && inbox.data">
        <table class="kv">
          <tbody>
            <tr>
              <th>inbox 用量</th>
              <td>
                <code>{{ inbox.data.usage.files }}</code> 文件 / {{ fmtBytes(inbox.data.usage.bytes) }}
                <span class="muted">（{{ fmtGiB(inbox.data.usage.bytes) }} GiB）</span>
              </td>
            </tr>
            <tr>
              <th>可回收</th>
              <td>
                <code>{{ inbox.data.collect_files }}</code> 文件 /
                {{ fmtBytes(inbox.data.collect_bytes) }}
                <span class="muted">（{{ fmtGiB(inbox.data.collect_bytes) }} GiB）</span>
              </td>
            </tr>
            <tr>
              <th>豁免</th>
              <td>
                <code>{{ inbox.data.exempt_files }}</code> 文件 /
                {{ fmtBytes(inbox.data.exempt_bytes) }}
                <span class="muted">（活跃 job 引用 或 保留期未到）</span>
              </td>
            </tr>
            <tr>
              <th>常量</th>
              <td class="muted">
                保留期 {{ inbox.data.constants.retention_days }} 天 ·
                容量闸 {{ fmtGiB(inbox.data.constants.capacity_max_bytes) }} GiB →
                {{ fmtGiB(inbox.data.constants.capacity_target_bytes) }} GiB
                <template v-if="inbox.data.capacity_gate_triggered">（**已触发**）</template> ·
                trash 宽限 {{ inbox.data.constants.trash_retention_days }} 天
              </td>
            </tr>
            <tr v-if="inbox.data.hard_delete_files">
              <th>trash 到期硬删</th>
              <td>
                <code>{{ inbox.data.hard_delete_files }}</code> 文件 /
                {{ fmtGiB(inbox.data.hard_delete_bytes) }} GiB
              </td>
            </tr>
          </tbody>
        </table>

        <div class="actions">
          <button class="ghost" type="button" :disabled="inboxAction.kind === 'busy'" @click="previewClean">
            预览清理
          </button>
          <button
            type="button"
            :disabled="inboxAction.kind === 'busy' || (!inboxReclaimable.files && !inbox.data.hard_delete_files)"
            @click="executeClean"
          >
            执行清理
          </button>
          <button class="ghost" type="button" :disabled="inboxAction.kind === 'busy'" @click="loadInbox">
            刷新用量
          </button>
        </div>

        <!-- 操作结果：成功 / 失败**可见**（不得静默） -->
        <div
          v-if="inboxAction.message"
          class="uploadbox"
          :class="inboxAction.kind === 'error' ? 'uploadbox--err' : (inboxAction.kind === 'ok' ? 'uploadbox--ok' : '')"
        >
          <p>{{ inboxAction.message }}</p>
        </div>

        <details class="advanced">
          <summary>清单明细：将回收 {{ inbox.data.collect_files }} · 豁免 {{ inbox.data.exempt_files }}</summary>
          <p v-if="inbox.data.collect.length" class="muted">将回收（dry-run 视图；apply 后移入 inbox/.trash/）：</p>
          <table v-if="inbox.data.collect.length" class="table">
            <thead>
              <tr><th>rel_path</th><th>体积</th><th>原因</th><th>来源</th><th>末次引用</th></tr>
            </thead>
            <tbody>
              <tr v-for="c in inbox.data.collect" :key="c.rel_path">
                <td>{{ c.rel_path }}</td>
                <td>{{ fmtBytes(c.bytes) }}</td>
                <td><code>{{ c.reason }}</code></td>
                <td class="muted">{{ c.reference_source || '—' }}</td>
                <td class="muted">{{ c.last_referenced_at || '—' }}</td>
              </tr>
            </tbody>
          </table>
          <StateNotice v-else kind="empty" title="无可回收项" />

          <p class="muted">豁免清单（含原因）：</p>
          <table class="table">
            <thead>
              <tr><th>rel_path</th><th>体积</th><th>原因</th><th>job</th></tr>
            </thead>
            <tbody>
              <tr v-for="e in inbox.data.exempt" :key="e.rel_path">
                <td>{{ e.rel_path }}</td>
                <td>{{ fmtBytes(e.bytes) }}</td>
                <td><code>{{ e.reason }}</code></td>
                <td class="muted">{{ e.job_id ? `${e.job_id}（${e.state}）` : '—' }}</td>
              </tr>
            </tbody>
          </table>
        </details>
      </template>
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
