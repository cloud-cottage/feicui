<script setup>
// 印人采集页（批 1）：从复旦印藏（yin.fudan.edu.cn）取「印人」信息，落 feicui 独立库。
// 三区：① 采集区（触发同步 / 进度 / 上次结果 / 批次列表）② 列表区（570 条 + 筛选 + 分页）③ 详情区（含关联印谱/印章）。
// 纪律：界面文案简体；**源数据原样呈现（繁 / 简两版可见）**，本地不改写源数据；后端不可达 ⇒ 沿用既有「未连接」横幅口径，绝不用假数据填充。
import { computed, onMounted, reactive, ref } from 'vue'
import { listPersons, getPerson, listBatches, syncPersons, generateImportPackage, listImportPackages } from '@/api/persons'
import { describeFailure } from '@/api/client'
import { useBackendStatus } from '@/composables/useBackendStatus'
import StateNotice from '@/components/StateNotice.vue'
import { nowStamp, rawBodyText, nilDash } from '@/utils/format'

const { markBackendDown } = useBackendStatus()

// ── 采集区 ────────────────────────────────────────────────────────────────
const syncForm = reactive({ delay: '0.2', resume: true, batch_id: '' })
const syncing = ref(false)
const syncResult = ref(null) // {kind:'ok'|'backend-down'|'error', ...}

const batchesState = ref({ kind: 'loading', items: null, detail: '', raw: '' })

// ── 列表区 ────────────────────────────────────────────────────────────────
const filters = reactive({ initial: '', nationality: '', has_dates: '', has_relations: '', q: '' })
const listState = ref({ kind: 'loading', items: null, page: 1, limit: 50, total: 0, has_more: false,
  facets: { initials: [], nationalities: [] }, detail: '', raw: '' })

// ── 详情区 ────────────────────────────────────────────────────────────────
const detailState = ref({ kind: 'idle', person: null, detail: '', raw: '' })

// ── 导入包区（xiai 就绪导入包：从本库重建，**不联网采集**；**不写 xiai 任何文件**）──────
const importForm = reactive({ batch_id: '' })
const importState = ref({ kind: 'idle', result: null, detail: '', raw: '', at: '' })
const importListState = ref({ kind: 'idle', items: null, detail: '', raw: '' })

// 交付缝 §3.15.10：`/api/persons/{grbsm}` 的字/号/别名六字段现回**真数组**；
// 兼容历史「JSON 字符串」形态（两形态都吃）。
function parseJsonList(value) {
  if (!value) return []
  if (Array.isArray(value)) return value
  try {
    const v = JSON.parse(value)
    return Array.isArray(v) ? v : []
  } catch {
    return []
  }
}

async function loadBatches() {
  batchesState.value = { kind: 'loading', items: null, detail: '', raw: '' }
  try {
    const res = await listBatches()
    if (res.status === 200 && res.body && Array.isArray(res.body.items)) {
      batchesState.value = { kind: 'ok', items: res.body.items, detail: '', raw: res.raw }
    } else {
      batchesState.value = { kind: 'error', items: null, detail: '批次接口返回形状不符合预期', raw: res.raw }
    }
  } catch (e) {
    const f = describeFailure(e)
    if (f.kind === 'backend-down') markBackendDown(f.detail)
    batchesState.value = { kind: f.kind === 'backend-down' ? 'backend-down' : 'error', items: null, detail: f.message, raw: '' }
  }
}

async function loadList(page = 1) {
  listState.value = { ...listState.value, kind: 'loading', detail: '' }
  try {
    const res = await listPersons({
      page,
      limit: listState.value.limit,
      initial: filters.initial || undefined,
      nationality: filters.nationality || undefined,
      has_dates: filters.has_dates || undefined,
      has_relations: filters.has_relations || undefined,
      q: filters.q || undefined,
    })
    if (res.status === 200 && res.body && Array.isArray(res.body.items)) {
      listState.value = {
        kind: 'ok',
        items: res.body.items,
        page: res.body.page,
        limit: res.body.limit,
        total: res.body.total,
        has_more: res.body.has_more,
        facets: res.body._facets || { initials: [], nationalities: [] },
        detail: '',
        raw: res.raw,
      }
    } else {
      listState.value = { ...listState.value, kind: 'error', items: null, detail: '列表接口返回形状不符合预期', raw: res.raw }
    }
  } catch (e) {
    const f = describeFailure(e)
    if (f.kind === 'backend-down') markBackendDown(f.detail)
    listState.value = { ...listState.value, kind: f.kind === 'backend-down' ? 'backend-down' : 'error', items: null, detail: f.message }
  }
}

async function openDetail(grbsm) {
  detailState.value = { kind: 'loading', person: null, detail: '', raw: '' }
  try {
    const res = await getPerson(grbsm)
    if (res.status === 200 && res.body && res.body.source_person_id) {
      detailState.value = { kind: 'ok', person: res.body, detail: '', raw: res.raw }
    } else if (res.status === 404) {
      detailState.value = { kind: 'error', person: null, detail: '404 印人不存在', raw: res.raw }
    } else {
      detailState.value = { kind: 'error', person: null, detail: `HTTP ${res.status}`, raw: res.raw }
    }
  } catch (e) {
    const f = describeFailure(e)
    if (f.kind === 'backend-down') markBackendDown(f.detail)
    detailState.value = { kind: f.kind === 'backend-down' ? 'backend-down' : 'error', person: null, detail: f.message, raw: '' }
  }
}

async function triggerSync() {
  syncing.value = true
  syncResult.value = { kind: 'running', startedAt: nowStamp() }
  const payload = { resume: syncForm.resume }
  const d = parseFloat(syncForm.delay)
  if (!Number.isNaN(d)) payload.delay = d
  if (syncForm.batch_id.trim()) payload.batch_id = syncForm.batch_id.trim()
  try {
    const res = await syncPersons(payload)
    if (res.status === 200 && res.body && res.body.batch_id) {
      syncResult.value = { kind: 'ok', status: res.status, body: res.body, raw: res.raw, at: nowStamp() }
      await loadBatches()
      await loadList(1)
    } else {
      syncResult.value = { kind: 'error', status: res.status, raw: res.raw || rawBodyText(res.body), at: nowStamp() }
    }
  } catch (e) {
    const f = describeFailure(e)
    if (f.kind === 'backend-down') markBackendDown(f.detail)
    syncResult.value = { kind: f.kind === 'backend-down' ? 'backend-down' : 'error', detail: f.message, at: nowStamp() }
  } finally {
    syncing.value = false
  }
}

async function triggerImportPackage() {
  importState.value = { kind: 'running', result: null, detail: '', raw: '', at: nowStamp() }
  const batch_id = importForm.batch_id.trim() || undefined
  try {
    const res = await generateImportPackage({ batch_id })
    if (res.status === 200 && res.body && res.body.package_dir) {
      importState.value = { kind: 'ok', result: res.body, detail: '', raw: res.raw, at: nowStamp() }
      await loadImportPackages()
    } else {
      importState.value = { kind: 'error', result: null, detail: `HTTP ${res.status}`,
        raw: res.raw || rawBodyText(res.body), at: nowStamp() }
    }
  } catch (e) {
    const f = describeFailure(e)
    if (f.kind === 'backend-down') markBackendDown(f.detail)
    importState.value = { kind: f.kind === 'backend-down' ? 'backend-down' : 'error',
      result: null, detail: f.message, raw: '', at: nowStamp() }
  }
}

async function loadImportPackages() {
  importListState.value = { ...importListState.value, kind: 'loading', detail: '' }
  try {
    const res = await listImportPackages()
    if (res.status === 200 && res.body && Array.isArray(res.body.items)) {
      importListState.value = { kind: 'ok', items: res.body.items, detail: '', raw: res.raw }
    } else {
      importListState.value = { kind: 'error', items: null, detail: '导入包列表接口返回形状不符合预期', raw: res.raw }
    }
  } catch (e) {
    const f = describeFailure(e)
    if (f.kind === 'backend-down') markBackendDown(f.detail)
    importListState.value = { kind: f.kind === 'backend-down' ? 'backend-down' : 'error',
      items: null, detail: f.message, raw: '' }
  }
}

function applyFilters() {
  loadList(1)
}
function resetFilters() {
  filters.initial = ''
  filters.nationality = ''
  filters.has_dates = ''
  filters.has_relations = ''
  filters.q = ''
  loadList(1)
}

onMounted(() => {
  loadBatches()
  loadList(1)
  loadImportPackages()
})

const totalPages = computed(() => {
  const l = listState.value.limit || 50
  return Math.max(1, Math.ceil((listState.value.total || 0) / l))
})

const detail = computed(() => detailState.value.person)
const detailRelations = computed(() => (detail.value ? detail.value.relations || [] : []))
const sealbooks = computed(() => detailRelations.value.filter((r) => r.kind === '印谱'))
const seals = computed(() => detailRelations.value.filter((r) => r.kind === '印章'))

function relCount(p, kind) {
  return kind === '印谱' ? p.sealbook_count : p.seal_count
}
</script>

<template>
  <section class="page">
    <header class="page__head">
      <h2>印人采集</h2>
      <p class="page__sub">
        数据源：复旦印藏（<code>https://yin.fudan.edu.cn</code>）「印人」。采集由 feicui 服务端
        <code>POST /api/persons/sync</code> 执行（列表 → 逐人详情 → 关联图 → 归一化 → 落独立库 → 批次包）。
        联网只发生在 feicui 服务端且只读，不上传任何数据。
      </p>
    </header>

    <!-- ── ① 采集区 ─────────────────────────────────────────────── -->
    <div class="card">
      <div class="card__head"><h3>采集区</h3>
        <button class="ghost" type="button" @click="loadBatches">刷新批次</button>
      </div>

      <div class="field-row">
        <label class="field field--sm">
          <span class="field__label">请求间隔 delay（秒，礼貌限速）</span>
          <input v-model="syncForm.delay" type="text" inputmode="decimal" placeholder="0.2" />
        </label>
        <label class="field field--sm">
          <span class="field__label">复用批次号 batch_id（同批次重跑 ⇒ 幂等；留空＝新开）</span>
          <input v-model="syncForm.batch_id" type="text" placeholder="如 person_20261010_01" />
        </label>
        <label class="field field--check">
          <input v-model="syncForm.resume" type="checkbox" />
          <span>resume 断点续跑（已入库者跳过网络取数）</span>
        </label>
      </div>

      <div class="actions">
        <button type="button" :disabled="syncing" @click="triggerSync">
          {{ syncing ? '采集中…（全量约数分钟，请勿关页）' : '触发同步（拉全量）' }}
        </button>
        <span class="muted">全量 570 人 × (详情 + 关联) ≈ 1140 请求；串行 + 限速。</span>
      </div>

      <StateNotice v-if="syncResult && syncResult.kind === 'running'" kind="loading"
        :title="`正在请求 POST /api/persons/sync …（${syncResult.startedAt}）`"
        detail="服务端串行取数并限速，全量约数分钟；完成后本区显示回执读数。" />

      <StateNotice v-else-if="syncResult && syncResult.kind === 'ok'" kind="info"
        title="200 采集完成（回执读数）" :status-code="syncResult.status" :raw-text="syncResult.raw"
        :detail="`响应时点 ${syncResult.at}`">
        <p>
          batch_id ＝ <code>{{ syncResult.body.batch_id }}</code>
          · 源 total ＝ <code>{{ syncResult.body.source_total }}</code>
          · 落库 persons ＝ <code>{{ syncResult.body.persons_ok }}</code>
          · 关联 ＝ <code>{{ syncResult.body.relations_ok }}</code>
          · 失败 ＝ <code>{{ syncResult.body.failed_count }}</code>
          · 耗时 ＝ <code>{{ syncResult.body.elapsed_s }}s</code>
        </p>
        <p>内容指纹 ＝ <code>{{ syncResult.body.content_fingerprint }}</code></p>
        <p>批次包 ＝ <code>{{ syncResult.body.package_dir }}</code></p>
        <details v-if="syncResult.body.failures && syncResult.body.failures.length">
          <summary>失败清单（{{ syncResult.body.failures.length }} 条，不得静默跳过）</summary>
          <pre>{{ JSON.stringify(syncResult.body.failures, null, 2) }}</pre>
        </details>
      </StateNotice>

      <StateNotice v-else-if="syncResult && syncResult.kind === 'backend-down'" kind="backend-down"
        title="后端未启动 / 未连接：同步未能发出" :detail="`${syncResult.detail || '—'}；时点 ${syncResult.at}`" />
      <StateNotice v-else-if="syncResult && syncResult.kind === 'error'" kind="error"
        title="同步请求失败（原样展示）" :status-code="syncResult.status || ''" :raw-text="syncResult.raw"
        :detail="`${syncResult.detail || ''}；时点 ${syncResult.at}`" />

      <!-- 批次列表 -->
      <h4>批次列表</h4>
      <StateNotice v-if="batchesState.kind === 'loading'" kind="loading" title="正在请求 GET /api/persons/batches …" />
      <StateNotice v-else-if="batchesState.kind === 'backend-down'" kind="backend-down"
        title="后端未启动 / 未连接：批次无法获取" :detail="batchesState.detail || '—'" />
      <StateNotice v-else-if="batchesState.kind === 'error'" kind="error"
        title="批次接口报错（原样展示）" :raw-text="batchesState.raw" :detail="batchesState.detail" />
      <template v-else-if="batchesState.kind === 'ok'">
        <p class="muted">
          计数口径：<b>persons／关联／耗时(s)</b> ＝ <b>采集 run</b> 的真实读数（persons／关联 取自库内实测计数，非单次重放读数）；
          <b>最近 run</b> 列另显最近一次运行（幂等重放时「请求＝0、跳过＝全部」属正常，不代表未采集）。
        </p>
        <table v-if="batchesState.items.length" class="table">
          <thead>
            <tr>
              <th>batch_id</th><th>状态</th><th>源 total</th>
              <th>persons<br><span class="muted">（采集·库内）</span></th>
              <th>关联<br><span class="muted">（采集·库内）</span></th>
              <th>失败</th>
              <th>耗时(s)<br><span class="muted">（采集 run）</span></th>
              <th>最近 run<br><span class="muted">（含幂等重放）</span></th>
              <th>内容指纹</th><th>时点</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="b in batchesState.items" :key="b.batch_id">
              <td><code>{{ b.batch_id }}</code></td>
              <td><code>{{ b.status }}</code></td>
              <td>{{ nilDash(b.source_total) }}</td>
              <td>{{ nilDash(b.persons_ok) }}</td>
              <td>{{ nilDash(b.relations_ok) }}</td>
              <td>{{ nilDash(b.failed_count) }}</td>
              <td>{{ nilDash(b.elapsed_s) }}</td>
              <td>
                <code>{{ b.last_run_kind || '—' }}</code>
                <span class="muted">· 请求 {{ nilDash(b.last_run_fetched) }} · 跳过 {{ nilDash(b.last_run_skipped) }} · {{ nilDash(b.last_run_elapsed_s) }}s</span>
              </td>
              <td><code>{{ (b.content_fingerprint || '').slice(0, 12) }}…</code></td>
              <td>{{ b.updated_at || b.created_at }}</td>
            </tr>
          </tbody>
        </table>
        <StateNotice v-else kind="empty" title="本机暂无批次记录" detail="尚未执行过采集。" />
      </template>
    </div>

    <!-- ── ② 列表区 ─────────────────────────────────────────────── -->
    <div class="card">
      <div class="card__head"><h3>印人列表</h3>
        <button class="ghost" type="button" @click="loadList(listState.page)">刷新</button>
      </div>

      <div class="field-row">
        <label class="field field--sm">
          <span class="field__label">姓氏首字母</span>
          <select v-model="filters.initial">
            <option value="">全部</option>
            <option v-for="i in listState.facets.initials" :key="i" :value="i">{{ i }}</option>
          </select>
        </label>
        <label class="field field--sm">
          <span class="field__label">国籍</span>
          <select v-model="filters.nationality">
            <option value="">全部</option>
            <option v-for="n in listState.facets.nationalities" :key="n" :value="n">{{ n }}</option>
          </select>
        </label>
        <label class="field field--sm">
          <span class="field__label">有无生卒</span>
          <select v-model="filters.has_dates">
            <option value="">全部</option><option value="true">有生卒</option><option value="false">无生卒</option>
          </select>
        </label>
        <label class="field field--sm">
          <span class="field__label">有无关联</span>
          <select v-model="filters.has_relations">
            <option value="">全部</option><option value="true">有关联</option><option value="false">无关联</option>
          </select>
        </label>
        <label class="field field--sm">
          <span class="field__label">姓名 / 拼音 / 源 id</span>
          <input v-model="filters.q" type="text" placeholder="模糊" @keyup.enter="applyFilters" />
        </label>
        <div class="actions">
          <button type="button" @click="applyFilters">筛选</button>
          <button class="ghost" type="button" @click="resetFilters">重置</button>
        </div>
      </div>

      <StateNotice v-if="listState.kind === 'loading'" kind="loading" title="正在请求 GET /api/persons …" />
      <StateNotice v-else-if="listState.kind === 'backend-down'" kind="backend-down"
        title="后端未启动 / 未连接：列表无法获取" :detail="`判负细节 ${listState.detail || '—'}`" />
      <StateNotice v-else-if="listState.kind === 'error'" kind="error"
        title="列表接口报错（原样展示）" :raw-text="listState.raw" :detail="listState.detail" />
      <template v-else-if="listState.kind === 'ok'">
        <p class="muted">
          共 {{ listState.total }} 人 · 第 {{ listState.page }} / {{ totalPages }} 页 · 每页 {{ listState.limit }}
          （源原文呈现：繁体为正字段，简体入 *_chs 副字段）
        </p>
        <table v-if="listState.items.length" class="table">
          <thead>
            <tr>
              <th>姓名（繁）</th><th>source_person_id</th><th>姓 / 名（抽取）</th><th>生卒</th>
              <th>国籍</th><th>拼音</th><th>印谱</th><th>印章</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in listState.items" :key="p.source_person_id">
              <td>{{ p.name_full || '—' }}</td>
              <td><code>{{ p.source_person_id }}</code></td>
              <td>
                {{ p.family_name || '—' }} / {{ p.given_name || '—' }}
                <span class="muted">（rule-based）</span>
              </td>
              <td>{{ p.birth_death_text || `${nilDash(p.birth_year)}–${nilDash(p.death_year)}` }}</td>
              <td>{{ p.nationality || '—' }}<span class="muted"> / {{ p.nationality_chs || '—' }}</span></td>
              <td>{{ p.spell || '—' }}</td>
              <td>{{ relCount(p, '印谱') }}</td>
              <td>{{ relCount(p, '印章') }}</td>
              <td>
                <button class="linkish" type="button" @click="openDetail(p.source_person_id)">详情</button>
              </td>
            </tr>
          </tbody>
        </table>
        <StateNotice v-else kind="empty" title="无匹配印人" detail="请调整筛选条件。" />

        <div class="pager">
          <button class="ghost" type="button" :disabled="listState.page <= 1" @click="loadList(listState.page - 1)">
            ← 上一页
          </button>
          <span class="muted">第 {{ listState.page }} / {{ totalPages }} 页</span>
          <button class="ghost" type="button" :disabled="!listState.has_more" @click="loadList(listState.page + 1)">
            下一页 →
          </button>
        </div>
      </template>
    </div>

    <!-- ── ③ 详情区 ─────────────────────────────────────────────── -->
    <div class="card">
      <div class="card__head"><h3>印人详情</h3>
        <button v-if="detailState.kind === 'ok'" class="ghost" type="button"
          @click="detailState = { kind: 'idle', person: null, detail: '', raw: '' }">关闭</button>
      </div>

      <StateNotice v-if="detailState.kind === 'idle'" kind="empty" title="未选择印人"
        detail="在列表区点「详情」查看单人（含关联印谱 / 印章）。" />
      <StateNotice v-else-if="detailState.kind === 'loading'" kind="loading" title="正在请求 GET /api/persons/{grbsm} …" />
      <StateNotice v-else-if="detailState.kind === 'backend-down'" kind="backend-down"
        title="后端未启动 / 未连接：详情无法获取" :detail="detailState.detail || '—'" />
      <StateNotice v-else-if="detailState.kind === 'error'" kind="error"
        title="详情接口报错（原样展示）" :raw-text="detailState.raw" :detail="detailState.detail" />

      <template v-else-if="detailState.kind === 'ok'">
        <table class="kv">
          <tbody>
            <tr><th>source_person_id（源键）</th><td><code>{{ detail.source_person_id }}</code>
              <span class="muted"> · source_seqid={{ nilDash(detail.source_seqid) }} · dataSourceId=<code>{{ nilDash(detail.source_data_source_id) }}</code></span></td></tr>
            <tr><th>姓名（繁 / 源原文）</th><td>{{ detail.name_full || '—' }}</td></tr>
            <tr><th>姓 / 名（rule-based 抽取）</th><td>{{ detail.family_name || '—' }} / {{ detail.given_name || '—' }}
              <span class="muted">（extraction={{ detail.name_extraction }}，非权威分类）</span></td></tr>
            <tr><th>字（繁 / 简）</th><td>
              {{ parseJsonList(detail.courtesy_names).map((x) => x.value).join('、') || '—' }}
              <span class="muted"> / {{ parseJsonList(detail.courtesy_names_chs).map((x) => x.value).join('、') || '—' }}</span></td></tr>
            <tr><th>號（繁 / 简）</th><td>
              {{ parseJsonList(detail.art_names).map((x) => x.value).join('、') || '—' }}
              <span class="muted"> / {{ parseJsonList(detail.art_names_chs).map((x) => x.value).join('、') || '—' }}</span></td></tr>
            <tr><th>别名 / 抽不准（繁 / 简）</th><td>
              {{ parseJsonList(detail.alias_names).map((x) => x.value).join('、') || '—' }}
              <span class="muted"> / {{ parseJsonList(detail.alias_names_chs).map((x) => x.value).join('、') || '—' }}</span></td></tr>
            <tr><th>生 / 卒年</th><td>{{ nilDash(detail.birth_year) }} / {{ nilDash(detail.death_year) }}
              <span class="muted"> · 生卒串＝{{ nilDash(detail.birth_death_text) }}（'?' / 空 ⇒ null，不设特值）</span></td></tr>
            <tr><th>籍贯（繁 / 简）</th><td>{{ detail.native_place || '—' }}
              <span class="muted"> / {{ detail.native_place_chs || '—' }}</span></td></tr>
            <tr><th>国籍（繁 / 简）</th><td>{{ detail.nationality || '—' }}
              <span class="muted"> / {{ detail.nationality_chs || '—' }}</span> · code＝<code>{{ nilDash(detail.nationality_code) }}</code></td></tr>
            <tr><th>CBDB id</th><td>{{ nilDash(detail.cbdb_id) }}<span class="muted">（原样，不联网核验）</span></td></tr>
            <tr><th>来源 / 来源 id</th><td>{{ detail.source || '—' }} / <code>{{ nilDash(detail.source_id) }}</code></td></tr>
            <tr><th>拼音 / 首字母 / flag</th><td>{{ detail.spell || '—' }} · {{ detail.initial || '—' }} · {{ nilDash(detail.flag) }}</td></tr>
            <tr v-if="detail.notes"><th>生卒考订 / 按语（personGrfz）</th><td>{{ detail.notes }}</td></tr>
            <tr><th>小传（繁 / 源原文）</th><td><div class="bio">{{ detail.biography || '—' }}</div></td></tr>
            <tr><th>小传（简 / 源原文）</th><td><div class="bio">{{ detail.biography_chs || '—' }}</div></td></tr>
          </tbody>
        </table>

        <h4>关联印谱（{{ sealbooks.length }}）</h4>
        <table v-if="sealbooks.length" class="table">
          <thead><tr><th>名称</th><th>creatorType</th><th>asBookId</th><th>hasImage</th><th>ref_id</th></tr></thead>
          <tbody>
            <tr v-for="r in sealbooks" :key="`b-${r.ref_id}-${r.seq}`">
              <td>{{ r.name || '—' }}</td><td>{{ r.creator_type || '—' }}</td>
              <td><code>{{ nilDash(r.as_book_id) }}</code></td><td>{{ nilDash(r.has_image) }}</td>
              <td><code>{{ nilDash(r.ref_id) }}</code></td>
            </tr>
          </tbody>
        </table>
        <StateNotice v-else kind="empty" title="无关联印谱" />

        <h4>关联印章（{{ seals.length }}）</h4>
        <table v-if="seals.length" class="table">
          <thead><tr><th>印文 desc</th><th>creatorType</th><th>image_key</th><th>ref_id</th></tr></thead>
          <tbody>
            <tr v-for="r in seals" :key="`s-${r.ref_id}-${r.seq}`">
              <td>{{ (r.desc || '—').replace('\n', ' / ') }}</td><td>{{ r.creator_type || '—' }}</td>
              <td><code>{{ nilDash(r.image_key) }}</code></td><td><code>{{ nilDash(r.ref_id) }}</code></td>
            </tr>
          </tbody>
        </table>
        <StateNotice v-else kind="empty" title="无关联印章" />

        <details class="notice__raw">
          <summary>原始响应体（GET /api/persons/{grbsm}，原样展示，未改写）</summary>
          <pre>{{ detailState.raw }}</pre>
        </details>
      </template>
    </div>

    <!-- ── ④ 导入包区（xiai 就绪导入包：从本库重建，不联网采集）────────── -->
    <div class="card">
      <div class="card__head"><h3>导入包（xiai 就绪）</h3>
        <button class="ghost" type="button" @click="loadImportPackages">刷新已生成</button>
      </div>
      <p class="page__sub">
        生成 <b>按 xiai 键面裁剪好</b> 的导入载荷，落到 <code>exports/person_import_&lt;batch_id&gt;/</code>：
        主交付 <code>person_imports.jsonl</code>（<b>逐行恰 xiai 现行 18 键</b>，字/号/别名降为 <code>string[]</code>）
        ＋ sidecar <code>person_imports_extraction.jsonl</code>（extraction 标注，不含 <code>from</code>）
        ＋ <code>manifest.json</code>。从 feicui 本库重建，<b>不联网采集</b>；<b>不写 xiai 任何文件</b>。
        <b>提交与审核在玺爱侧</b>：导入先落 <code>xiai_person_imports</code>（PENDING），管理员批量采纳后方成正式印人。
      </p>

      <div class="field-row">
        <label class="field field--sm">
          <span class="field__label">源批次号 batch_id（留空＝库内最新批次）</span>
          <input v-model="importForm.batch_id" type="text" placeholder="如 person_20261010_01" />
        </label>
        <div class="actions">
          <button type="button" :disabled="importState.kind === 'running'" @click="triggerImportPackage">
            {{ importState.kind === 'running' ? '生成中…' : '生成 xiai 就绪导入包' }}
          </button>
        </div>
      </div>

      <StateNotice v-if="importState.kind === 'running'" kind="loading"
        title="正在请求 POST /api/persons/import-package …"
        :detail="`服务端从本库重建（不联网）；响应时点 ${importState.at}`" />
      <StateNotice v-else-if="importState.kind === 'backend-down'" kind="backend-down"
        title="后端未启动 / 未连接：导入包未能生成" :detail="`${importState.detail || '—'}；时点 ${importState.at}`" />
      <StateNotice v-else-if="importState.kind === 'error'" kind="error"
        title="生成导入包失败（原样展示，不假数据）" :raw-text="importState.raw"
        :detail="`${importState.detail || ''}；时点 ${importState.at}`" />

      <template v-else-if="importState.kind === 'ok'">
        <table class="kv"><tbody>
          <tr><th>包目录</th><td><code>{{ importState.result.package_dir }}</code></td></tr>
          <tr><th>行数（应 570）</th><td><b>{{ importState.result.rows }}</b> 行 · 源批次 <code>{{ importState.result.batch_id }}</code></td></tr>
          <tr><th>校验摘要</th><td>
            键面 diff ⇒ 多余键 <code>{{ importState.result.key_face.extra_count }}</code>（须 0）／
            缺失键 <code>{{ importState.result.key_face.missing_keys.length }}</code>（须 0）／
            xiai 允许键 <code>{{ importState.result.key_face.xiai_allowed_keys_count }}</code>；
            幂等键 <code>source_person_id</code> 非空 / 唯一 / 总行 ＝
            <code>{{ importState.result.idempotency.non_null }} / {{ importState.result.idempotency.unique }} / {{ importState.result.idempotency.total }}</code>；
            三桶均 <code>string[]</code> ⇒ <code>{{ importState.result.checks.three_buckets_all_string_arrays ? '是' : '否' }}</code>；
            sidecar 等长 ⇒ <code>{{ importState.result.checks.sidecar_lengths_match ? '是' : '否' }}</code>；
            无 BOM ⇒ <code>{{ importState.result.checks.main_no_bom && importState.result.checks.sidecar_no_bom ? '是' : '否' }}</code>
          </td></tr>
          <tr><th>sidecar</th><td><code>{{ importState.result.sidecar.file }}</code>（{{ importState.result.sidecar.keys.join('、') }}；<b>不含 from</b>）</td></tr>
          <tr><th>提交 / 审核</th><td>{{ importState.result.submission }}</td></tr>
        </tbody></table>
        <details class="notice__raw">
          <summary>原始响应体（POST /api/persons/import-package，原样展示，未改写）</summary>
          <pre>{{ importState.raw }}</pre>
        </details>
      </template>

      <h4>已生成导入包</h4>
      <StateNotice v-if="importListState.kind === 'loading'" kind="loading" title="正在请求 GET /api/persons/import-packages …" />
      <StateNotice v-else-if="importListState.kind === 'backend-down'" kind="backend-down"
        title="后端未启动 / 未连接：导入包列表无法获取" :detail="importListState.detail || '—'" />
      <StateNotice v-else-if="importListState.kind === 'error'" kind="error"
        title="导入包列表接口报错（原样展示）" :raw-text="importListState.raw" :detail="importListState.detail" />
      <template v-else-if="importListState.kind === 'ok'">
        <table v-if="importListState.items.length" class="table">
          <thead><tr><th>包目录</th><th>源批次</th><th>行数</th><th>多余键</th><th>幂等 唯一/总</th><th>生成时点</th></tr></thead>
          <tbody>
            <tr v-for="it in importListState.items" :key="it.package_dir">
              <td><code>{{ it.dir_name }}</code></td>
              <td><code>{{ it.source_batch || '—' }}</code></td>
              <td>{{ nilDash(it.rows) }}</td>
              <td>{{ it.key_face_diff ? it.key_face_diff.extra_count : '—' }}</td>
              <td>{{ it.idempotency ? `${it.idempotency.unique} / ${it.idempotency.total}` : '—' }}</td>
              <td>{{ it.generated_at || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <StateNotice v-else kind="empty" title="本机暂无导入包" detail="点上方按钮生成。" />
      </template>
    </div>
  </section>
</template>

<style scoped>
.bio { max-height: 220px; overflow: auto; white-space: pre-wrap; word-break: break-word; }
h4 { margin: 14px 0 4px; font-size: 13.5px; color: var(--accent-line); }
</style>
