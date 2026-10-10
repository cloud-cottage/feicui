<script setup>
// 印章采集页（批 1）：从复旦印藏（yin.fudan.edu.cn）取「印章」信息，落 feicui 独立库。
// 四区：① 采集区（触发同步 / 回执 / 批次列表）② 列表区（3679 枚 + 筛选 + 分页 + 缩略图）
//      ③ 详情区（含关联 sidecar + 影像台账）④ 就绪包区（xiai）。
// 纪律：界面文案简体；**源数据原样呈现（繁 / 简两版可见）**，本地不改写源数据；
//       后端不可达 ⇒ 沿用既有「未连接」横幅口径，绝不用假数据填充。
import { computed, onMounted, reactive, ref } from 'vue'
import { listSeals, getSeal, listBatches, syncSeals, buildSealPackage, sealImageUrl } from '@/api/seals'
import { describeFailure } from '@/api/client'
import { useBackendStatus } from '@/composables/useBackendStatus'
import StateNotice from '@/components/StateNotice.vue'
import { nowStamp, rawBodyText, nilDash } from '@/utils/format'

const { markBackendDown } = useBackendStatus()

// ── 采集区 ────────────────────────────────────────────────────────────────
const syncForm = reactive({ delay: '0.5', resume: true, limit: '', batch_id: '', with_detail: false, with_graph: false })
const syncing = ref(false)
const syncResult = ref(null)
const batchesState = ref({ kind: 'loading', items: null, detail: '', raw: '' })

// ── 列表区 ────────────────────────────────────────────────────────────────
const AUDIT_OPTIONS = [
  { value: '', label: '全部' },
  { value: '1', label: '已审（1）' },
  { value: '2', label: '已发布（2）' },
  { value: '0', label: '未审（0）' },
  { value: '9', label: '其它（9）' },
]
const filters = reactive({ audit_status: '', has_image: '', q: '' })
const listState = ref({ kind: 'loading', items: null, page: 1, limit: 50, total: 0, has_more: false,
  facets: { total: 0, with_image: 0, audit_status_distribution: {} }, detail: '', raw: '' })

// ── 详情区 ────────────────────────────────────────────────────────────────
const detailState = ref({ kind: 'idle', item: null, detail: '', raw: '' })

// ── 就绪包区（xiai）─────────────────────────────────────────────────────────
const pkgForm = reactive({ batch_id: '' })
const pkgState = ref({ kind: 'idle', at: '', result: null, raw: '', detail: '' })

async function triggerPackage() {
  pkgState.value = { kind: 'running', at: nowStamp(), result: null, raw: '', detail: '' }
  try {
    const res = await buildSealPackage(pkgForm.batch_id.trim() || undefined)
    if (res.status === 200 && res.body && res.body.package_dir) {
      pkgState.value = { kind: 'ok', at: nowStamp(), result: res.body, raw: res.raw, detail: '' }
      await loadBatches()
    } else {
      pkgState.value = { kind: 'error', at: nowStamp(), result: null,
        raw: res.raw || rawBodyText(res.body), detail: `HTTP ${res.status}` }
    }
  } catch (e) {
    const f = describeFailure(e)
    if (f.kind === 'backend-down') markBackendDown(f.detail)
    pkgState.value = { kind: f.kind === 'backend-down' ? 'backend-down' : 'error',
      at: nowStamp(), result: null, raw: '', detail: f.message }
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
    const res = await listSeals({
      page,
      limit: listState.value.limit,
      audit_status: filters.audit_status || undefined,
      has_image: filters.has_image || undefined,
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
        facets: res.body._facets || { total: 0, with_image: 0, audit_status_distribution: {} },
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

async function openDetail(seqid) {
  detailState.value = { kind: 'loading', item: null, detail: '', raw: '' }
  try {
    const res = await getSeal(seqid)
    if (res.status === 200 && res.body && res.body.source_seal_id) {
      detailState.value = { kind: 'ok', item: res.body, detail: '', raw: res.raw }
    } else if (res.status === 404) {
      detailState.value = { kind: 'error', item: null, detail: '404 印章不存在', raw: res.raw }
    } else {
      detailState.value = { kind: 'error', item: null, detail: `HTTP ${res.status}`, raw: res.raw }
    }
  } catch (e) {
    const f = describeFailure(e)
    if (f.kind === 'backend-down') markBackendDown(f.detail)
    detailState.value = { kind: f.kind === 'backend-down' ? 'backend-down' : 'error', item: null, detail: f.message, raw: '' }
  }
}

async function triggerSync() {
  syncing.value = true
  syncResult.value = { kind: 'running', startedAt: nowStamp() }
  const payload = { resume: syncForm.resume, with_detail: syncForm.with_detail, with_graph: syncForm.with_graph }
  const d = parseFloat(syncForm.delay)
  if (!Number.isNaN(d)) payload.delay = d
  const lim = parseInt(syncForm.limit, 10)
  if (!Number.isNaN(lim)) payload.limit = lim
  if (syncForm.batch_id.trim()) payload.batch_id = syncForm.batch_id.trim()
  try {
    const res = await syncSeals(payload)
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

function applyFilters() { loadList(1) }
function resetFilters() {
  filters.audit_status = ''
  filters.has_image = ''
  filters.q = ''
  loadList(1)
}

function onThumbError(ev) {
  // 本地无图（未下载 / 源侧无图）⇒ 隐藏 broken 图标，不假数据
  ev.target.style.visibility = 'hidden'
}

onMounted(() => {
  loadBatches()
  loadList(1)
})

const totalPages = computed(() => {
  const l = listState.value.limit || 50
  return Math.max(1, Math.ceil((listState.value.total || 0) / l))
})

const detail = computed(() => detailState.value.item)
const detailLinks = computed(() => (detail.value ? detail.value.links || [] : []))
const detailImages = computed(() => (detail.value ? detail.value.images || [] : []))
function miscPairs(m) {
  if (!m || typeof m !== 'object') return []
  return Object.entries(m).filter(([, v]) => v !== null && v !== undefined && v !== '')
}
function fmtKinds (dist) {
  if (!dist || typeof dist !== 'object') return '—'
  return Object.entries(dist).map(([k, v]) => `${k}=${v}`).join(' · ')
}
</script>

<template>
  <section class="page">
    <header class="page__head">
      <h2>印章采集</h2>
      <p class="page__sub">
        数据源：复旦印藏（<code>https://yin.fudan.edu.cn</code>）「印章」。采集由 feicui 服务端
        <code>POST /api/seals/sync</code> 执行（列表 1 次取全 3679 枚 → 行内字段构建关联 → 归一化 → 落独立库 → 就绪包）。
        影像（IIIF 裁切图）转 TIFF 无损容器入包。联网只发生在 feicui 服务端且只读，不上传任何数据。
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
          <input v-model="syncForm.delay" type="text" inputmode="decimal" placeholder="0.5" />
        </label>
        <label class="field field--sm">
          <span class="field__label">本轮最多新增 limit（留空＝全量；分片续跑用）</span>
          <input v-model="syncForm.limit" type="text" inputmode="numeric" placeholder="如 300" />
        </label>
        <label class="field field--sm">
          <span class="field__label">复用批次号 batch_id（同批次重跑 ⇒ 幂等；留空＝新开）</span>
          <input v-model="syncForm.batch_id" type="text" placeholder="如 seal_20261010_01" />
        </label>
        <label class="field field--check">
          <input v-model="syncForm.resume" type="checkbox" />
          <span>resume 断点续跑（已入库者跳过网络取数）</span>
        </label>
        <label class="field field--check">
          <input v-model="syncForm.with_detail" type="checkbox" />
          <span>with_detail 逐枚补 detail（best-effort，默认关）</span>
        </label>
        <label class="field field--check">
          <input v-model="syncForm.with_graph" type="checkbox" />
          <span>with_graph 逐枚取 graph/seal（best-effort，默认关）</span>
        </label>
      </div>

      <div class="actions">
        <button type="button" :disabled="syncing" @click="triggerSync">
          {{ syncing ? '采集中…（全量约十数秒，请勿关页）' : '触发同步（拉全量）' }}
        </button>
        <span class="muted">全量 3679 枚 ＝ 1 请求（列表一次取全）＋ 本地构建关联；形製标签由码表本地派生。</span>
      </div>

      <StateNotice v-if="syncResult && syncResult.kind === 'running'" kind="loading"
        :title="`正在请求 POST /api/seals/sync …（${syncResult.startedAt}）`"
        detail="服务端取数并限速，全量约十数秒；完成后本区显示回执读数。" />

      <StateNotice v-else-if="syncResult && syncResult.kind === 'ok'" kind="info"
        title="200 采集完成（回执读数）" :status-code="syncResult.status" :raw-text="syncResult.raw"
        :detail="`响应时点 ${syncResult.at}`">
        <p>
          batch_id ＝ <code>{{ syncResult.body.batch_id }}</code>
          · 源 total ＝ <code>{{ syncResult.body.source_total }}</code>
          · 落库 seals ＝ <code>{{ syncResult.body.seals_ok }}</code>
          · 关联 ＝ <code>{{ syncResult.body.links_ok }}</code>
          · 剩余 ＝ <code>{{ syncResult.body.remaining }}</code>
          · 失败 ＝ <code>{{ syncResult.body.failed_count }}</code>
          · 耗时 ＝ <code>{{ syncResult.body.elapsed_s }}s</code>
        </p>
        <p>内容指纹 ＝ <code>{{ syncResult.body.content_fingerprint }}</code></p>
        <p>就绪包 ＝ <code>{{ syncResult.body.package_dir }}</code></p>
      </StateNotice>

      <StateNotice v-else-if="syncResult && syncResult.kind === 'backend-down'" kind="backend-down"
        title="后端未启动 / 未连接：同步未能发出" :detail="`${syncResult.detail || '—'}；时点 ${syncResult.at}`" />
      <StateNotice v-else-if="syncResult && syncResult.kind === 'error'" kind="error"
        title="同步请求失败（原样展示）" :status-code="syncResult.status || ''" :raw-text="syncResult.raw"
        :detail="`${syncResult.detail || ''}；时点 ${syncResult.at}`" />

      <!-- 批次列表 -->
      <h4>批次列表</h4>
      <StateNotice v-if="batchesState.kind === 'loading'" kind="loading" title="正在请求 GET /api/seals/batches …" />
      <StateNotice v-else-if="batchesState.kind === 'backend-down'" kind="backend-down"
        title="后端未启动 / 未连接：批次无法获取" :detail="batchesState.detail || '—'" />
      <StateNotice v-else-if="batchesState.kind === 'error'" kind="error"
        title="批次接口报错（原样展示）" :raw-text="batchesState.raw" :detail="batchesState.detail" />
      <template v-else-if="batchesState.kind === 'ok'">
        <p class="muted">
          计数口径：<b>seals／关联</b> ＝ <b>采集 run</b> 的真实读数（取自库内实测计数）；
          <b>最近 run</b> 列另显最近一次运行（幂等重放时「请求＝0、跳过＝全部」属正常）。影像列显示 ok / failed / 源侧无图。
        </p>
        <table v-if="batchesState.items.length" class="table">
          <thead>
            <tr>
              <th>batch_id</th><th>状态</th><th>源 total</th>
              <th>seals<br><span class="muted">（库内）</span></th>
              <th>关联<br><span class="muted">（库内）</span></th>
              <th>影像<br><span class="muted">ok/失败/无图</span></th>
              <th>耗时(s)</th>
              <th>最近 run</th>
              <th>内容指纹</th><th>时点</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="b in batchesState.items" :key="b.batch_id">
              <td><code>{{ b.batch_id }}</code></td>
              <td><code>{{ b.status }}</code></td>
              <td>{{ nilDash(b.source_total) }}</td>
              <td>{{ nilDash(b.seals_ok) }}</td>
              <td>{{ nilDash(b.links_ok) }}</td>
              <td>
                <span>{{ nilDash(b.images_ok) }}</span> / <span>{{ nilDash(b.images_failed) }}</span> /
                <span>{{ nilDash(b.images_no_source) }}</span>
              </td>
              <td>{{ nilDash(b.elapsed_s) }}</td>
              <td>
                <code>{{ b.last_run_kind || '—' }}</code>
                <span class="muted">· 请求 {{ nilDash(b.last_run_fetched) }} · 跳过 {{ nilDash(b.last_run_skipped) }}</span>
              </td>
              <td><code>{{ (b.content_fingerprint || '').slice(0, 12) }}…</code></td>
              <td>{{ b.updated_at || b.created_at }}</td>
            </tr>
          </tbody>
        </table>
        <StateNotice v-else kind="empty" title="本机暂无批次记录" detail="尚未执行过采集。" />
      </template>
    </div>

    <!-- ── ④ 就绪包（xiai）─────────────────────────────────────────── -->
    <div class="card">
      <div class="card__head"><h3>就绪包（xiai）</h3></div>
      <p class="page__sub">
        从 feicui 本库重建 <b>xiai 就绪包</b>，落到 <code>exports/seal_import_&lt;batch_id&gt;/</code>：
        <code>seals.jsonl</code>（候选键面，未裁剪）＋ <code>seal_links.jsonl</code>（sidecar）＋
        <code>images/&lt;sha256[:2]&gt;/&lt;sha256&gt;.tiff</code>（**内容寻址 TIFF 树**，镜像 xiai 影像库）＋
        <code>images_manifest.jsonl</code>（唯一索引）＋ <code>manifest.json</code>
        （字段字典 / 形製码表＋标定证据 / audit 分布 / <code>image_policy</code> / <code>key_face_status: pending_xiai</code>）。
        <b>从本库重建、不联网采集；不写 xiai 任何文件</b>（提交与审核在玺爱侧）。
      </p>

      <div class="field-row">
        <label class="field field--sm">
          <span class="field__label">源批次号 batch_id（留空＝库内最新批次）</span>
          <input v-model="pkgForm.batch_id" type="text" placeholder="如 seal_20261010_01" />
        </label>
        <div class="actions">
          <button type="button" :disabled="pkgState.kind === 'running'" @click="triggerPackage">
            {{ pkgState.kind === 'running' ? '生成中…' : '生成 xiai 就绪包' }}
          </button>
        </div>
      </div>

      <StateNotice v-if="pkgState.kind === 'running'" kind="loading"
        title="正在请求 POST /api/seals/package …"
        :detail="`服务端从本库重建（不联网）；响应时点 ${pkgState.at}`" />
      <StateNotice v-else-if="pkgState.kind === 'backend-down'" kind="backend-down"
        title="后端未启动 / 未连接：就绪包未能生成" :detail="`${pkgState.detail || '—'}；时点 ${pkgState.at}`" />
      <StateNotice v-else-if="pkgState.kind === 'error'" kind="error"
        title="生成就绪包失败（原样展示，不假数据）" :raw-text="pkgState.raw"
        :detail="`${pkgState.detail || ''}；时点 ${pkgState.at}`" />

      <template v-else-if="pkgState.kind === 'ok'">
        <table class="kv"><tbody>
          <tr><th>包目录</th><td><code>{{ pkgState.result.package_dir }}</code></td></tr>
          <tr><th>行数</th><td>
            <b>seals {{ pkgState.result.rows }}</b> 行 · sidecar <b>{{ pkgState.result.links_rows }}</b> 行
            · 影像 <b>{{ nilDash(pkgState.result.images_rows) }}</b> 张
            · 源 total <code>{{ pkgState.result.source_total }}</code>
            · 源批次 <code>{{ pkgState.result.batch_id }}</code> · 生成时点 {{ pkgState.result.generated_at }}
          </td></tr>
          <tr><th>键面状态</th><td>
            <code>key_face_status = {{ pkgState.result.key_face_status }}</code>
          </td></tr>
          <tr><th>形製码表</th><td>
            码表 <b>{{ Object.keys(pkgState.result.seal_ys_lookup.table).length }}</b> 项 ——
            <code>{{ Object.entries(pkgState.result.seal_ys_lookup.table).map(([k, v]) => `${k}=${v}`).join('、') }}</code><br>
            <span class="muted">源侧原文写作「异性」（逐字照登）；标定：每码 2 枚 × 20 次 × 0 冲突</span>
          </td></tr>
          <tr><th>audit 分布</th><td>
            <code>{{ fmtKinds(pkgState.result.audit_status_distribution) }}</code>
          </td></tr>
          <tr><th>字段字典</th><td>
            seals 本体 <b>{{ pkgState.result.field_dict.length }}</b> 键 ·
            sidecar <b>{{ pkgState.result.field_dict_links.length }}</b> 键
          </td></tr>
          <tr><th>幂等键</th><td>
            <code>source_seal_id</code> 非空 / 唯一 / 总 ＝
            <code>{{ pkgState.result.idempotency.non_null }} / {{ pkgState.result.idempotency.unique }} / {{ pkgState.result.idempotency.total }}</code>
          </td></tr>
          <tr><th>image_policy</th><td>
            容器 <code>{{ pkgState.result.image_policy.container }}</code> ·
            路径 <code>{{ pkgState.result.image_policy.path_shape }}</code> ·
            状态 <code>{{ fmtKinds(pkgState.result.image_policy.status_counts) }}</code><br>
            <span class="muted">{{ pkgState.result.image_policy.conversion_note }}</span>
          </td></tr>
          <tr><th>内容指纹</th><td><code>{{ pkgState.result.content_fingerprint }}</code></td></tr>
        </tbody></table>
        <details class="notice__raw">
          <summary>原始响应体（POST /api/seals/package，原样展示，未改写）</summary>
          <pre>{{ pkgState.raw }}</pre>
        </details>
      </template>
    </div>

    <!-- ── ② 列表区 ─────────────────────────────────────────────── -->
    <div class="card">
      <div class="card__head"><h3>印章列表</h3>
        <button class="ghost" type="button" @click="loadList(listState.page)">刷新</button>
      </div>

      <div class="field-row">
        <label class="field field--sm">
          <span class="field__label">审核状态</span>
          <select v-model="filters.audit_status">
            <option v-for="o in AUDIT_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
        </label>
        <label class="field field--sm">
          <span class="field__label">有无影像</span>
          <select v-model="filters.has_image">
            <option value="">全部</option><option value="true">有影像</option><option value="false">无影像</option>
          </select>
        </label>
        <label class="field field--sm">
          <span class="field__label">印文 / 印谱名 / 源 id</span>
          <input v-model="filters.q" type="text" placeholder="模糊" @keyup.enter="applyFilters" />
        </label>
        <div class="actions">
          <button type="button" @click="applyFilters">筛选</button>
          <button class="ghost" type="button" @click="resetFilters">重置</button>
        </div>
      </div>

      <StateNotice v-if="listState.kind === 'loading'" kind="loading" title="正在请求 GET /api/seals …" />
      <StateNotice v-else-if="listState.kind === 'backend-down'" kind="backend-down"
        title="后端未启动 / 未连接：列表无法获取" :detail="`判负细节 ${listState.detail || '—'}`" />
      <StateNotice v-else-if="listState.kind === 'error'" kind="error"
        title="列表接口报错（原样展示）" :raw-text="listState.raw" :detail="listState.detail" />
      <template v-else-if="listState.kind === 'ok'">
        <p class="muted">
          共 {{ listState.total }} 枚 · 第 {{ listState.page }} / {{ totalPages }} 页 · 每页 {{ listState.limit }}
          （库内全量 {{ listState.facets.total }}：有影像 {{ listState.facets.with_image }}；
          audit 分布 {{ fmtKinds(listState.facets.audit_status_distribution) }}）
          · 源原文呈现：繁体为正字段，简体入 *_chs 副字段
        </p>
        <table v-if="listState.items.length" class="table">
          <thead>
            <tr>
              <th>缩略图</th><th>印文（繁）</th><th>形製</th><th>所属印谱</th>
              <th>印主 / 篆者</th><th>source_seal_id</th><th>audit</th><th>关联数</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="it in listState.items" :key="it.source_seal_id">
              <td>
                <img v-if="it.seal_yt_url" class="thumb" :src="sealImageUrl(it.source_seal_id, 'yt')"
                  alt="印面缩略图" loading="lazy" @error="onThumbError" />
                <span v-else class="muted">—</span>
              </td>
              <td>{{ it.seal_wen || '—' }}<span v-if="it.seal_wen_chs" class="muted"> / {{ it.seal_wen_chs }}</span></td>
              <td>{{ nilDash(it.seal_ys_label) }}<span class="muted">（{{ nilDash(it.seal_ys_xz) }}）</span></td>
              <td>{{ it.related_book || '—' }}<span class="muted">（{{ nilDash(it.as_book_id) }}）</span></td>
              <td>{{ it.seal_yz_person_name || '—' }}<span class="muted"> / {{ it.seal_yzzkz || '—' }}</span></td>
              <td><code>{{ it.source_seal_id }}</code></td>
              <td><code>{{ nilDash(it.audit_status) }}</code></td>
              <td>{{ nilDash(it.link_count) }}</td>
              <td>
                <button class="linkish" type="button" @click="openDetail(it.source_seal_id)">详情</button>
              </td>
            </tr>
          </tbody>
        </table>
        <StateNotice v-else kind="empty" title="无匹配印章" detail="请调整筛选条件。" />

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
      <div class="card__head"><h3>印章详情</h3>
        <button v-if="detailState.kind === 'ok'" class="ghost" type="button"
          @click="detailState = { kind: 'idle', item: null, detail: '', raw: '' }">关闭</button>
      </div>

      <StateNotice v-if="detailState.kind === 'idle'" kind="empty" title="未选择印章"
        detail="在列表区点「详情」查看单枚（含关联 sidecar 与影像台账）。" />
      <StateNotice v-else-if="detailState.kind === 'loading'" kind="loading" title="正在请求 GET /api/seals/{seqid} …" />
      <StateNotice v-else-if="detailState.kind === 'backend-down'" kind="backend-down"
        title="后端未启动 / 未连接：详情无法获取" :detail="detailState.detail || '—'" />
      <StateNotice v-else-if="detailState.kind === 'error'" kind="error"
        title="详情接口报错（原样展示）" :raw-text="detailState.raw" :detail="detailState.detail" />

      <template v-else-if="detailState.kind === 'ok'">
        <table class="kv">
          <tbody>
            <tr><th>source_seal_id（源键 / 幂等键）</th><td><code>{{ detail.source_seal_id }}</code>
              <span class="muted"> · seal_uri=<code>{{ nilDash(detail.seal_uri) }}</code></span></td></tr>
            <tr><th>分类 / audit</th><td>{{ detail.category || '—' }} / <code>{{ nilDash(detail.audit_status) }}</code></td></tr>
            <tr><th>印文（繁 / 简）</th><td>{{ detail.seal_wen || '—' }}
              <span class="muted"> / {{ detail.seal_wen_chs || '—' }}</span></td></tr>
            <tr><th>形製（码 / 可读值）</th><td>{{ nilDash(detail.seal_ys_xz) }} / <b>{{ nilDash(detail.seal_ys_label) }}</b></td></tr>
            <tr><th>印主（繁 / 简）</th><td>{{ nilDash(detail.seal_yz_person_name) }}
              <span class="muted"> / {{ nilDash(detail.seal_yz_person_name_chs) }} · id <code>{{ nilDash(detail.seal_yz) }}</code></span></td></tr>
            <tr><th>篆者（繁 / 简 / id）</th><td>{{ nilDash(detail.seal_yzzkz) }}
              <span class="muted"> / {{ nilDash(detail.seal_yzzkz_chs) }} · <code>{{ nilDash(detail.seal_yzzkz_id) }}</code></span></td></tr>
            <tr><th>边款</th><td><div class="bio">{{ detail.seal_bk || '—' }}</div></td></tr>
            <tr><th>边款篆者</th><td>{{ nilDash(detail.seal_bkzkz) }} <span class="muted">· <code>{{ nilDash(detail.seal_bkzkz_id) }}</code></span></td></tr>
            <tr><th>所属印谱</th><td>{{ nilDash(detail.related_book) }} <span class="muted">· as_book_id <code>{{ nilDash(detail.as_book_id) }}</code></span></td></tr>
            <tr><th>影像 ref</th><td>
              印面=<code>{{ nilDash(detail.seal_yt_url) }}</code> /
              释文=<code>{{ nilDash(detail.seal_ytsw_url) }}</code> /
              边款=<code>{{ nilDash(detail.seal_yzbk_url) }}</code>
            </td></tr>
            <tr v-if="miscPairs(detail.misc).length"><th>misc（低频 / 审计元字段）</th><td>
              <span v-for="([k, v], i) in miscPairs(detail.misc)" :key="k">{{ i ? ' · ' : '' }}{{ k }}={{ v }}</span></td></tr>
          </tbody>
        </table>

        <div class="thumbs">
          <figure v-if="detail.seal_yt_url">
            <img class="thumb-lg" :src="sealImageUrl(detail.source_seal_id, 'yt')" alt="印面图" @error="onThumbError" />
            <figcaption class="muted">印面（yt）</figcaption>
          </figure>
          <figure v-if="detail.seal_ytsw_url">
            <img class="thumb-lg" :src="sealImageUrl(detail.source_seal_id, 'ytsw')" alt="印体释文图" @error="onThumbError" />
            <figcaption class="muted">释文（ytsw）</figcaption>
          </figure>
          <figure v-if="detail.seal_yzbk_url">
            <img class="thumb-lg" :src="sealImageUrl(detail.source_seal_id, 'yzbk')" alt="边款图" @error="onThumbError" />
            <figcaption class="muted">边款（yzbk）</figcaption>
          </figure>
        </div>

        <h4>关联 sidecar（印章↔印谱↔印人，{{ detailLinks.length }}）</h4>
        <table v-if="detailLinks.length" class="table">
          <thead><tr><th>link_kind</th><th>ref_name</th><th>ref_id</th><th>bridge_item_id</th><th>来源面</th><th>seq</th></tr></thead>
          <tbody>
            <tr v-for="l in detailLinks" :key="`${l.link_kind}-${l.ref_id}-${l.source_face}-${l.seq}`">
              <td><code>{{ l.link_kind }}</code></td>
              <td>{{ l.ref_name || '—' }}</td>
              <td><code>{{ nilDash(l.ref_id) }}</code></td>
              <td><code>{{ nilDash(l.bridge_item_id) }}</code></td>
              <td><code>{{ l.source_face }}</code></td>
              <td>{{ l.seq }}</td>
            </tr>
          </tbody>
        </table>
        <StateNotice v-else kind="empty" title="无关联" />

        <h4>影像台账（{{ detailImages.length }}）</h4>
        <table v-if="detailImages.length" class="table">
          <thead><tr><th>kind</th><th>status</th><th>source_ref</th><th>bytes</th><th>sha256</th><th>error</th></tr></thead>
          <tbody>
            <tr v-for="im in detailImages" :key="`${im.seqid}-${im.kind}`">
              <td><code>{{ im.kind }}</code></td>
              <td><code>{{ im.status }}</code></td>
              <td><code>{{ nilDash(im.source_ref) }}</code></td>
              <td>{{ nilDash(im.bytes) }}</td>
              <td><code>{{ (im.sha256 || '').slice(0, 12) }}…</code></td>
              <td class="muted">{{ im.error || '' }}</td>
            </tr>
          </tbody>
        </table>
        <StateNotice v-else kind="empty" title="无影像台账" />

        <details class="notice__raw">
          <summary>原始响应体（GET /api/seals/{seqid}，原样展示，未改写）</summary>
          <pre>{{ detailState.raw }}</pre>
        </details>
      </template>
    </div>
  </section>
</template>

<style scoped>
.bio { max-height: 220px; overflow: auto; white-space: pre-wrap; word-break: break-word; }
h4 { margin: 14px 0 4px; font-size: 13.5px; color: var(--accent-line); }
.thumb { width: 44px; height: 44px; object-fit: cover; border: 1px solid var(--line); border-radius: 4px; }
.thumbs { display: flex; gap: 14px; margin: 10px 0; flex-wrap: wrap; }
.thumbs figure { margin: 0; text-align: center; }
.thumb-lg { width: 120px; height: 120px; object-fit: contain; border: 1px solid var(--line); border-radius: 4px; background: var(--bg-inset); }
</style>
