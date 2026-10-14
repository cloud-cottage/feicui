<script setup>
// PDF 资料页：var/pdf_registry.db 的 web 视图（output 四总目录落地单，2026-10-14）。
// GET /api/pdf-records 列表 ＋ 行内编辑（朝代下拉＝15 枚举、作者/备注文本）→ PATCH 保存。
// 纪律：本页只展示后端返回值、只发显式 PATCH，**不**本地复算/编造任何字段。
import { onMounted, reactive, ref } from 'vue'
import { listPdfRecords, patchPdfRecord } from '@/api/pdfRecords'
import { describeFailure } from '@/api/client'

// 朝代值域真源＝xiai VALUE_DOMAINS.DYNASTY_OPTIONS（15 值逐字同值；后端 PATCH 同口径校验）。
const DYNASTY_OPTIONS = [
  '春秋', '戰國', '秦', '漢', '魏晉', '隋唐', '宋元', '明早中期', '晚明',
  '清初', '清中期', '晚清', '民國', '新中國', '當代',
]

const STATUS_LABELS = { present: '在册', missing: '未寻获' }

const records = ref([])
const total = ref(0)
const status = ref({ kind: 'loading', detail: '' })
const filterStatus = ref('')
const filterQ = ref('')

// 行编辑态：{[id]: {dynasty, author, notes, dirty, saving, message}}
const edits = reactive({})

function fmtBytes(n) {
  if (n === null || n === undefined) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let v = Number(n)
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i += 1
  }
  return `${v.toFixed(v >= 100 || i === 0 ? 0 : 1)}${units[i]}`
}

function sha8(row) {
  return row.sha256 ? row.sha256.slice(0, 8) : '—'
}

function startEdit(row) {
  edits[row.id] = {
    dynasty: row.dynasty ?? '',
    author: row.author ?? '',
    notes: row.notes ?? '',
    dirty: false,
    saving: false,
    message: '',
  }
}

function onEdit(row, key, ev) {
  const e = edits[row.id]
  if (!e) return
  e[key] = ev.target.value
  e.dirty =
    e.dynasty !== (row.dynasty ?? '') ||
    e.author !== (row.author ?? '') ||
    e.notes !== (row.notes ?? '')
}

async function save(row) {
  const e = edits[row.id]
  if (!e || e.saving || !e.dirty) return
  e.saving = true
  e.message = ''
  // 只发**改动过的键**（缺省键＝不改，与 API 契约一致）
  const payload = {}
  if (e.dynasty !== (row.dynasty ?? '')) payload.dynasty = e.dynasty === '' ? null : e.dynasty
  if (e.author !== (row.author ?? '')) payload.author = e.author === '' ? null : e.author
  if (e.notes !== (row.notes ?? '')) payload.notes = e.notes === '' ? null : e.notes
  try {
    const res = await patchPdfRecord(row.id, payload)
    if (res.status === 200 && res.body?.record) {
      Object.assign(row, res.body.record)
      e.dirty = false
      e.message = `已保存 ${res.body.record.updated_at || ''}`
    } else {
      const err = res.body?.detail
      e.message = `保存失败（${res.status}）${typeof err === 'string' ? err : err?.error || err?.detail || ''}`
    }
  } catch (err) {
    e.message = `保存失败：${describeFailure(err).message}`
  } finally {
    e.saving = false
  }
}

async function fetchRecords() {
  status.value = { kind: 'loading', detail: '' }
  try {
    const res = await listPdfRecords({
      page: 1,
      limit: 200,
      status: filterStatus.value || undefined,
      q: filterQ.value || undefined,
    })
    if (res.status === 200 && res.body?.records) {
      records.value = res.body.records
      total.value = res.body.total ?? res.body.records.length
      for (const row of res.body.records) startEdit(row)
      status.value = { kind: 'ok', detail: '' }
    } else {
      status.value = { kind: 'error', detail: `GET /api/pdf-records → ${res.status}（原样展示）` }
    }
  } catch (e) {
    status.value = { kind: 'backend-down', detail: describeFailure(e).message }
  }
}

onMounted(fetchRecords)
</script>

<template>
  <section class="pdfrecords">
    <header class="pdfrecords__head">
      <h2>PDF 资料</h2>
      <p class="pdfrecords__hint">
        登记库 <code>var/pdf_registry.db</code>（幂等键＝sha256）。朝代/作者/备注由人工补填，保存即写
        <code>updated_at</code>；扫描口径见 <code>docs/output-layout-v0.1.md</code>。
      </p>
      <div class="pdfrecords__filters">
        <select v-model="filterStatus" @change="fetchRecords">
          <option value="">全部状态</option>
          <option value="present">在册</option>
          <option value="missing">未寻获</option>
        </select>
        <input v-model="filterQ" placeholder="搜文件名/作者/备注…" @keyup.enter="fetchRecords" />
        <button type="button" @click="fetchRecords">刷新</button>
        <span v-if="status.kind === 'ok'" class="pdfrecords__count">共 {{ total }} 条</span>
      </div>
    </header>

    <p v-if="status.kind === 'loading'">加载中…</p>
    <p v-else-if="status.kind === 'backend-down'" class="pdfrecords__error">{{ status.detail }}</p>
    <p v-else-if="status.kind === 'error'" class="pdfrecords__error">{{ status.detail }}</p>

    <div v-else class="pdfrecords__tablewrap">
      <table class="pdfrecords__table">
        <thead>
          <tr>
            <th>#</th>
            <th>文件名</th>
            <th>sha8</th>
            <th>页数</th>
            <th>页面 (mm)</th>
            <th>大小</th>
            <th>DPI</th>
            <th>朝代</th>
            <th>作者</th>
            <th>备注</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in records" :key="row.id">
            <td>{{ row.id }}</td>
            <td class="pdfrecords__name" :title="row.rel_path || '（未寻获）'">{{ row.filename }}</td>
            <td><code>{{ sha8(row) }}</code></td>
            <td>{{ row.page_count ?? '—' }}</td>
            <td>{{ row.page_mm ?? '—' }}</td>
            <td>{{ fmtBytes(row.size_bytes) }}</td>
            <td>{{ row.scan_dpi ?? '—' }}</td>
            <td>
              <select :value="edits[row.id]?.dynasty" @change="onEdit(row, 'dynasty', $event)">
                <option value="">（未填）</option>
                <option v-for="d in DYNASTY_OPTIONS" :key="d" :value="d">{{ d }}</option>
              </select>
            </td>
            <td><input :value="edits[row.id]?.author" placeholder="作者" @input="onEdit(row, 'author', $event)" /></td>
            <td><input :value="edits[row.id]?.notes" placeholder="备注" @input="onEdit(row, 'notes', $event)" /></td>
            <td>
              <span :class="`pdfrecords__status pdfrecords__status--${row.status}`">
                {{ STATUS_LABELS[row.status] || row.status }}
              </span>
            </td>
            <td class="pdfrecords__actions">
              <button
                type="button"
                :disabled="!edits[row.id]?.dirty || edits[row.id]?.saving"
                @click="save(row)"
              >
                {{ edits[row.id]?.saving ? '保存中…' : '保存' }}
              </button>
              <div v-if="edits[row.id]?.message" class="pdfrecords__msg">{{ edits[row.id].message }}</div>
            </td>
          </tr>
          <tr v-if="!records.length">
            <td colspan="12">登记库为空（先跑 ops/pdf-registry/scan_pdf_registry.py）。</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.pdfrecords__head h2 {
  margin: 0 0 4px;
}
.pdfrecords__hint {
  margin: 0 0 8px;
  color: #666;
  font-size: 12px;
}
.pdfrecords__filters {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}
.pdfrecords__filters input {
  width: 240px;
}
.pdfrecords__count {
  color: #888;
  font-size: 12px;
}
.pdfrecords__error {
  color: #b00020;
}
.pdfrecords__tablewrap {
  overflow-x: auto;
}
.pdfrecords__table {
  border-collapse: collapse;
  font-size: 13px;
  width: 100%;
}
.pdfrecords__table th,
.pdfrecords__table td {
  border: 1px solid #ddd;
  padding: 4px 6px;
  text-align: left;
  vertical-align: top;
  white-space: nowrap;
}
.pdfrecords__name {
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pdfrecords__table input,
.pdfrecords__table select {
  width: 130px;
  font-size: 12px;
}
.pdfrecords__status--missing {
  color: #b00020;
}
.pdfrecords__msg {
  font-size: 11px;
  color: #555;
  white-space: normal;
  max-width: 160px;
}
</style>
