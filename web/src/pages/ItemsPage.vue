<script setup>
// 印谱采集页（批 1）：从复旦印藏（yin.fudan.edu.cn）取「印谱」信息，落 feicui 独立库。
// 三区：① 采集区（触发同步 / 回执 / 批次列表）② 列表区（1742 条 + 筛选 + 分页）③ 详情区（含关联责任者）。
// 纪律：界面文案简体；**源数据原样呈现（繁 / 简两版可见）**，本地不改写源数据；后端不可达 ⇒ 沿用既有「未连接」横幅口径，绝不用假数据填充。
import { computed, onMounted, reactive, ref } from 'vue'
import { listItems, getItem, listBatches, syncItems, buildItemPackage } from '@/api/items'
import { describeFailure } from '@/api/client'
import { useBackendStatus } from '@/composables/useBackendStatus'
import StateNotice from '@/components/StateNotice.vue'
import { nowStamp, rawBodyText, nilDash } from '@/utils/format'

const { markBackendDown } = useBackendStatus()

// ── 采集区 ────────────────────────────────────────────────────────────────
const syncForm = reactive({ delay: '0.5', resume: true, limit: '', batch_id: '' })
const syncing = ref(false)
const syncResult = ref(null) // {kind:'ok'|'backend-down'|'error', ...}
const batchesState = ref({ kind: 'loading', items: null, detail: '', raw: '' })

// ── 列表区 ────────────────────────────────────────────────────────────────
const filters = reactive({ has_image: '', has_year: '', q: '' })
const listState = ref({ kind: 'loading', items: null, page: 1, limit: 50, total: 0, has_more: false,
  facets: { total: 0, with_image: 0, with_year: 0 }, detail: '', raw: '' })

// ── 详情区 ────────────────────────────────────────────────────────────────
const detailState = ref({ kind: 'idle', item: null, detail: '', raw: '' })

// ── 就绪包区（xiai）─────────────────────────────────────────────────────────
const pkgForm = reactive({ batch_id: '' })
const pkgState = ref({ kind: 'idle', at: '', result: null, raw: '', detail: '' })

async function triggerPackage() {
  pkgState.value = { kind: 'running', at: nowStamp(), result: null, raw: '', detail: '' }
  try {
    const res = await buildItemPackage(pkgForm.batch_id.trim() || undefined)
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
    const res = await listItems({
      page,
      limit: listState.value.limit,
      has_image: filters.has_image || undefined,
      has_year: filters.has_year || undefined,
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
        facets: res.body._facets || { total: 0, with_image: 0, with_year: 0 },
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
    const res = await getItem(seqid)
    if (res.status === 200 && res.body && res.body.source_item_id) {
      detailState.value = { kind: 'ok', item: res.body, detail: '', raw: res.raw }
    } else if (res.status === 404) {
      detailState.value = { kind: 'error', item: null, detail: '404 印谱不存在', raw: res.raw }
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
  const payload = { resume: syncForm.resume }
  const d = parseFloat(syncForm.delay)
  if (!Number.isNaN(d)) payload.delay = d
  const lim = parseInt(syncForm.limit, 10)
  if (!Number.isNaN(lim)) payload.limit = lim
  if (syncForm.batch_id.trim()) payload.batch_id = syncForm.batch_id.trim()
  try {
    const res = await syncItems(payload)
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

function applyFilters() {
  loadList(1)
}
function resetFilters() {
  filters.has_image = ''
  filters.has_year = ''
  filters.q = ''
  loadList(1)
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
const detailCreators = computed(() => (detail.value ? detail.value.creators || [] : []))
function miscPairs(m) {
  if (!m || typeof m !== 'object') return []
  return Object.entries(m).filter(([, v]) => v !== null && v !== undefined && v !== '')
}
</script>

<template>
  <section class="page">
    <header class="page__head">
      <h2>印谱采集</h2>
      <p class="page__sub">
        数据源：复旦印藏（<code>https://yin.fudan.edu.cn</code>）「印谱」。采集由 feicui 服务端
        <code>POST /api/items/sync</code> 执行（列表 1 次取全 1742 本 → 逐本 graph/book 取关联 → 归一化 → 落独立库 → 就绪包）。
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
          <input v-model="syncForm.delay" type="text" inputmode="decimal" placeholder="0.5" />
        </label>
        <label class="field field--sm">
          <span class="field__label">本轮最多新增 limit（留空＝全量；分片续跑用）</span>
          <input v-model="syncForm.limit" type="text" inputmode="numeric" placeholder="如 300" />
        </label>
        <label class="field field--sm">
          <span class="field__label">复用批次号 batch_id（同批次重跑 ⇒ 幂等；留空＝新开）</span>
          <input v-model="syncForm.batch_id" type="text" placeholder="如 item_20261010_01" />
        </label>
        <label class="field field--check">
          <input v-model="syncForm.resume" type="checkbox" />
          <span>resume 断点续跑（已入库者跳过网络取数）</span>
        </label>
      </div>

      <div class="actions">
        <button type="button" :disabled="syncing" @click="triggerSync">
          {{ syncing ? '采集中…（全量约二十分钟，请勿关页）' : '触发同步（拉全量）' }}
        </button>
        <span class="muted">全量 1742 本 ≈ 1743 请求（列表 1 ＋ 逐本 graph/book 1742）；串行 + 限速。</span>
      </div>

      <StateNotice v-if="syncResult && syncResult.kind === 'running'" kind="loading"
        :title="`正在请求 POST /api/items/sync …（${syncResult.startedAt}）`"
        detail="服务端串行取数并限速，全量约二十分钟；完成后本区显示回执读数。" />

      <StateNotice v-else-if="syncResult && syncResult.kind === 'ok'" kind="info"
        title="200 采集完成（回执读数）" :status-code="syncResult.status" :raw-text="syncResult.raw"
        :detail="`响应时点 ${syncResult.at}`">
        <p>
          batch_id ＝ <code>{{ syncResult.body.batch_id }}</code>
          · 源 total ＝ <code>{{ syncResult.body.source_total }}</code>
          · 落库 items ＝ <code>{{ syncResult.body.items_ok }}</code>
          · 责任者 ＝ <code>{{ syncResult.body.creators_ok }}</code>
          · 剩余 ＝ <code>{{ syncResult.body.remaining }}</code>
          · 失败 ＝ <code>{{ syncResult.body.failed_count }}</code>
          · 耗时 ＝ <code>{{ syncResult.body.elapsed_s }}s</code>
        </p>
        <p>内容指纹 ＝ <code>{{ syncResult.body.content_fingerprint }}</code></p>
        <p>就绪包 ＝ <code>{{ syncResult.body.package_dir }}</code></p>
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
      <StateNotice v-if="batchesState.kind === 'loading'" kind="loading" title="正在请求 GET /api/items/batches …" />
      <StateNotice v-else-if="batchesState.kind === 'backend-down'" kind="backend-down"
        title="后端未启动 / 未连接：批次无法获取" :detail="batchesState.detail || '—'" />
      <StateNotice v-else-if="batchesState.kind === 'error'" kind="error"
        title="批次接口报错（原样展示）" :raw-text="batchesState.raw" :detail="batchesState.detail" />
      <template v-else-if="batchesState.kind === 'ok'">
        <p class="muted">
          计数口径：<b>items／责任者／耗时(s)</b> ＝ <b>采集 run</b> 的真实读数（items／责任者 取自库内实测计数，非单次重放读数）；
          <b>最近 run</b> 列另显最近一次运行（幂等重放时「请求＝0、跳过＝全部」属正常，不代表未采集）。
        </p>
        <table v-if="batchesState.items.length" class="table">
          <thead>
            <tr>
              <th>batch_id</th><th>状态</th><th>源 total</th>
              <th>items<br><span class="muted">（采集·库内）</span></th>
              <th>责任者<br><span class="muted">（采集·库内）</span></th>
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
              <td>{{ nilDash(b.items_ok) }}</td>
              <td>{{ nilDash(b.creators_ok) }}</td>
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

    <!-- ── 就绪包（xiai）─────────────────────────────────────────── -->
    <div class="card">
      <div class="card__head"><h3>就绪包（xiai）</h3></div>
      <p class="page__sub">
        从 feicui 本库重建 <b>xiai 就绪包</b>，落到 <code>exports/item_import_&lt;batch_id&gt;/</code>：
        <code>items.jsonl</code>（候选键面，未裁剪）＋ <code>item_creators.jsonl</code>（sidecar）＋
        <code>manifest.json</code>（字段字典 / 行数 / 幂等键唯一计数 / 覆盖统计 /
        <code>key_face_status: pending_xiai</code> / <code>detail_policy</code>）。
        <b>从本库重建、不联网采集；不写 xiai 任何文件</b>（提交与审核在玺爱侧）。
      </p>

      <div class="field-row">
        <label class="field field--sm">
          <span class="field__label">源批次号 batch_id（留空＝库内最新批次）</span>
          <input v-model="pkgForm.batch_id" type="text" placeholder="如 item_20261010_01" />
        </label>
        <div class="actions">
          <button type="button" :disabled="pkgState.kind === 'running'" @click="triggerPackage">
            {{ pkgState.kind === 'running' ? '生成中…' : '生成 xiai 就绪包' }}
          </button>
        </div>
      </div>

      <StateNotice v-if="pkgState.kind === 'running'" kind="loading"
        title="正在请求 POST /api/items/package …"
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
            <b>items {{ pkgState.result.rows }}</b> 行 · sidecar <b>{{ pkgState.result.creators_rows }}</b> 行
            · 源 total <code>{{ pkgState.result.source_total }}</code>
            · 源批次 <code>{{ pkgState.result.batch_id }}</code> · 生成时点 {{ pkgState.result.generated_at }}
          </td></tr>
          <tr><th>键面状态</th><td>
            <code>key_face_status = {{ pkgState.result.key_face_status }}</code>
            （键面未定前不裁剪，由字段字典供 xiai 挑选）
          </td></tr>
          <tr><th>字段字典</th><td>
            item 本体 <b>{{ pkgState.result.field_dict.length }}</b> 键：<code>{{ pkgState.result.field_dict.map(f => f.name).join('、') }}</code><br>
            sidecar <b>{{ pkgState.result.field_dict_creators.length }}</b> 键：<code>{{ pkgState.result.field_dict_creators.map(f => f.name).join('、') }}</code>
          </td></tr>
          <tr><th>幂等键</th><td>
            <code>source_item_id</code> 非空 / 唯一 / 总 ＝
            <code>{{ pkgState.result.idempotency.non_null }} / {{ pkgState.result.idempotency.unique }} / {{ pkgState.result.idempotency.total }}</code>
          </td></tr>
          <tr><th>detail_policy</th><td>
            enabled ＝ <code>{{ pkgState.result.detail_policy.enabled }}</code>（默认 {{ pkgState.result.detail_policy.default }}）
            · 请求 <code>{{ pkgState.result.detail_policy.detail_requests }}</code>
            · 未确认 <code>{{ pkgState.result.detail_policy.detail_unconfirmed }}</code>
            · 缺三字段：<code>{{ pkgState.result.detail_policy.detail_only_fields.join('、') }}</code>
          </td></tr>
          <tr><th>内容指纹</th><td><code>{{ pkgState.result.content_fingerprint }}</code></td></tr>
        </tbody></table>
        <details class="notice__raw">
          <summary>原始响应体（POST /api/items/package，原样展示，未改写）</summary>
          <pre>{{ pkgState.raw }}</pre>
        </details>
      </template>
    </div>

    <!-- ── ② 列表区 ─────────────────────────────────────────────── -->
    <div class="card">
      <div class="card__head"><h3>印谱列表</h3>
        <button class="ghost" type="button" @click="loadList(listState.page)">刷新</button>
      </div>

      <div class="field-row">
        <label class="field field--sm">
          <span class="field__label">有无影像</span>
          <select v-model="filters.has_image">
            <option value="">全部</option><option value="true">有影像</option><option value="false">无影像</option>
          </select>
        </label>
        <label class="field field--sm">
          <span class="field__label">有无年份</span>
          <select v-model="filters.has_year">
            <option value="">全部</option><option value="true">有年份</option><option value="false">无年份</option>
          </select>
        </label>
        <label class="field field--sm">
          <span class="field__label">题名 / 源 id</span>
          <input v-model="filters.q" type="text" placeholder="模糊" @keyup.enter="applyFilters" />
        </label>
        <div class="actions">
          <button type="button" @click="applyFilters">筛选</button>
          <button class="ghost" type="button" @click="resetFilters">重置</button>
        </div>
      </div>

      <StateNotice v-if="listState.kind === 'loading'" kind="loading" title="正在请求 GET /api/items …" />
      <StateNotice v-else-if="listState.kind === 'backend-down'" kind="backend-down"
        title="后端未启动 / 未连接：列表无法获取" :detail="`判负细节 ${listState.detail || '—'}`" />
      <StateNotice v-else-if="listState.kind === 'error'" kind="error"
        title="列表接口报错（原样展示）" :raw-text="listState.raw" :detail="listState.detail" />
      <template v-else-if="listState.kind === 'ok'">
        <p class="muted">
          共 {{ listState.total }} 本 · 第 {{ listState.page }} / {{ totalPages }} 页 · 每页 {{ listState.limit }}
          （库内全量 {{ listState.facets.total }}：有影像 {{ listState.facets.with_image }}、有年份 {{ listState.facets.with_year }}）
          · 源原文呈现：繁体为正字段，简体入 *_chs 副字段
        </p>
        <table v-if="listState.items.length" class="table">
          <thead>
            <tr>
              <th>题名（繁）</th><th>source_item_id</th><th>as_book_id</th><th>卷册</th>
              <th>纪年 / 公元</th><th>出版者</th><th>责任者数</th><th>影像</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="it in listState.items" :key="it.source_item_id">
              <td>{{ it.title || '—' }}</td>
              <td><code>{{ it.source_item_id }}</code></td>
              <td><code>{{ nilDash(it.as_book_id) }}</code></td>
              <td>{{ nilDash(it.volume_count) }}</td>
              <td>{{ nilDash(it.date_text) }}<span class="muted"> / {{ nilDash(it.date_year) }}</span></td>
              <td>{{ it.publisher || '—' }}</td>
              <td>{{ nilDash(it.creator_count) }}</td>
              <td>{{ it.has_image ? '有' : '无' }}</td>
              <td>
                <button class="linkish" type="button" @click="openDetail(it.source_item_id)">详情</button>
              </td>
            </tr>
          </tbody>
        </table>
        <StateNotice v-else kind="empty" title="无匹配印谱" detail="请调整筛选条件。" />

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
      <div class="card__head"><h3>印谱详情</h3>
        <button v-if="detailState.kind === 'ok'" class="ghost" type="button"
          @click="detailState = { kind: 'idle', item: null, detail: '', raw: '' }">关闭</button>
      </div>

      <StateNotice v-if="detailState.kind === 'idle'" kind="empty" title="未选择印谱"
        detail="在列表区点「详情」查看单本（含关联责任者）。" />
      <StateNotice v-else-if="detailState.kind === 'loading'" kind="loading" title="正在请求 GET /api/items/{seqid} …" />
      <StateNotice v-else-if="detailState.kind === 'backend-down'" kind="backend-down"
        title="后端未启动 / 未连接：详情无法获取" :detail="detailState.detail || '—'" />
      <StateNotice v-else-if="detailState.kind === 'error'" kind="error"
        title="详情接口报错（原样展示）" :raw-text="detailState.raw" :detail="detailState.detail" />

      <template v-else-if="detailState.kind === 'ok'">
        <table class="kv">
          <tbody>
            <tr><th>source_item_id（源键 / 幂等键）</th><td><code>{{ detail.source_item_id }}</code>
              <span class="muted"> · as_book_id=<code>{{ nilDash(detail.as_book_id) }}</code> · as_id={{ nilDash(detail.as_id) }}</span></td></tr>
            <tr><th>分类</th><td>{{ detail.category || '—' }}</td></tr>
            <tr><th>题名（繁 / 简）</th><td>{{ detail.title || '—' }}
              <span class="muted"> / {{ detail.title_chs || '—' }}</span></td></tr>
            <tr><th>其他题名（繁 / 简）</th><td>{{ detail.title_other || '—' }}
              <span class="muted"> / {{ detail.title_other_chs || '—' }}</span></td></tr>
            <tr><th>卷册数</th><td>{{ nilDash(detail.volume_count) }}
              <span class="muted">（整数或 null，不设特值）</span></td></tr>
            <tr><th>成谱纪年（原文 / 公元）</th><td>{{ nilDash(detail.date_text) }} / {{ nilDash(detail.date_year) }}</td></tr>
            <tr><th>出版者 / 版本</th><td>{{ nilDash(detail.publisher) }} / {{ nilDash(detail.edition) }}</td></tr>
            <tr><th>藏家（bookDonor）</th><td>{{ nilDash(detail.donor) }}</td></tr>
            <tr><th>有无影像 / 释文</th><td>{{ detail.has_image ? '有影像' : '无影像' }} / {{ detail.has_annotation ? '有释文' : '无释文' }}</td></tr>
            <tr><th>语种</th><td>{{ nilDash(detail.language) }}</td></tr>
            <tr><th>题要名</th><td>{{ nilDash(detail.abstract_title) }}</td></tr>
            <tr v-if="miscPairs(detail.misc).length"><th>misc（低频字段）</th><td>
              <span v-for="([k, v], i) in miscPairs(detail.misc)" :key="k">{{ i ? ' · ' : '' }}{{ k }}={{ v }}</span></td></tr>
            <tr><th>题要（繁 / 源原文）</th><td><div class="bio">{{ detail.abstract || '—' }}</div></td></tr>
            <tr><th>题要（简 / 源原文）</th><td><div class="bio">{{ detail.abstract_chs || '—' }}</div></td></tr>
          </tbody>
        </table>

        <h4>关联责任者（item↔person，{{ detailCreators.length }}）</h4>
        <table v-if="detailCreators.length" class="table">
          <thead><tr><th>姓名</th><th>creator_type</th><th>role / relator</th><th>person_grbsm</th><th>来源面</th><th>seq</th></tr></thead>
          <tbody>
            <tr v-for="c in detailCreators" :key="`${c.source_face}-${c.person_grbsm}-${c.creator_type}-${c.seq}`">
              <td>{{ c.creator_name || '—' }}</td>
              <td>{{ c.creator_type || '—' }}</td>
              <td>{{ nilDash(c.creator_role) }} / {{ nilDash(c.creator_relator) }}</td>
              <td><code>{{ nilDash(c.person_grbsm) }}</code></td>
              <td><code>{{ c.source_face }}</code></td>
              <td>{{ c.seq }}</td>
            </tr>
          </tbody>
        </table>
        <StateNotice v-else kind="empty" title="无关联责任者" />

        <details class="notice__raw">
          <summary>原始响应体（GET /api/items/{seqid}，原样展示，未改写）</summary>
          <pre>{{ detailState.raw }}</pre>
        </details>
      </template>
    </div>
  </section>
</template>

<style scoped>
.bio { max-height: 220px; overflow: auto; white-space: pre-wrap; word-break: break-word; }
h4 { margin: 14px 0 4px; font-size: 13.5px; color: var(--accent-line); }
</style>
