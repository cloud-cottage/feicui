<script setup>
// 图片高清化（成品化）页：单张印章图 → `POST /api/tools/enhance` → 成品 PNG ＋ 读数。
//
// 口径（不得写反）：
//   * 后端用**既有唯一实现** `server/app/seal_canvas.py` 做「成品化」（换纸底 ＋ 统一构图 ＋ 晕染）；
//   * **唯一像素变换是 Lanczos 几何重采样** ⇒ 本页**不承诺**提升真实分辨率，
//     文案一律「按统一成品规格输出（默认宽 1200 px）」，不出现「提升分辨率 / 无损放大 / 更清晰」；
//   * 默认成品**宽度** 1200 px（高度按原图比例）；宽度可在 200–4000 调整，越界就地提示、不请求。
//
// 三条输入通路**共用同一条处理链路**（`acceptFile()` → `state.file` → `run()`）：
//   ① 点击 / 键盘选择文件；② 拖拽落区；③ ⌘V 粘贴剪贴板里的图片（本页挂载时监听、卸载时摘除）。
// 纪律：读数一律来自后端响应（`width/height/bytes/sha256/elapsed_ms/params_used`），本地不复算不编造；
//       后端错误把 `error` / `reason` **原样**显示；后端不可达 ⇒ BackendUnreachableError 语义（全局横幅同源）。
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { base64ToBlob, enhanceImage } from '@/api/enhance'
import { describeFailure } from '@/api/client'
import { useBackendStatus } from '@/composables/useBackendStatus'
import StateNotice from '@/components/StateNotice.vue'

const { markBackendDown } = useBackendStatus()

// ── 表单态 ────────────────────────────────────────────────────────────────
const state = ref({
  file: null, // 原始 File（三条输入通路归一到这里）
  origin: '', // file | drop | paste —— 只用于提示文案，不参与请求
  srcUrl: '', // 原图 objectURL
  srcMeta: null, // {width,height} 由浏览器实测（图片自然尺寸）
})
const widthInput = ref('1200')
const widthError = ref('')
const background = ref('paper') // paper（宣纸底纹）| plain_white（纯白）
const running = ref(false)
const elapsedTick = ref(0) // 处理中补一个真实秒表（不做假进度条）
const result = ref(null) // 后端 200 响应体 ＋ viewUrl
const failure = ref(null) // {kind,status,error,reason,raw,message}
const pasteNote = ref('') // 「剪贴板里没有图片」／「剪贴板含 N 张，已取第 1 张」
const clipboardCount = ref(0)
const dragged = ref(false)
const fileInputEl = ref(null)
let tickTimer = null

const BACKGROUND_LABELS = { paper: '宣纸底纹', plain_white: '纯白 #FFFFFF' }

const canRun = computed(
  () => !!state.value.file && !running.value && widthError.value === '' && widthInput.value !== ''
)

function fmtBytes(n) {
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}

function revoke(url) {
  if (url) {
    try {
      URL.revokeObjectURL(url)
    } catch {
      /* 忽略：URL 已失效 */
    }
  }
}

function resetOutput() {
  if (result.value && result.value.viewUrl) revoke(result.value.viewUrl)
  result.value = null
  failure.value = null
}

// ── ① 输入归一化：选择 / 拖拽 / 粘贴 三条通路都进这里 ──────────────────────
function acceptFile(file, origin) {
  if (!file) return
  const looksImage =
    (file.type || '').startsWith('image/') || /\.(png|jpe?g|webp|tiff?|bmp|gif)$/i.test(file.name || '')
  if (!looksImage) {
    resetOutput()
    failure.value = {
      kind: 'error',
      status: '',
      error: 'LOCAL_NOT_IMAGE',
      reason: `只接受图片文件（image/*）；收到「${file.name || '无文件名'}」（${file.type || '未知类型'}）——未发出请求。`,
      raw: '',
    }
    return
  }
  revoke(state.value.srcUrl)
  resetOutput()
  pasteNote.value = origin === 'paste' ? pasteNote.value : ''
  state.value = { file, origin, srcUrl: URL.createObjectURL(file), srcMeta: null }
  // 原始尺寸由浏览器实测（Image 自然尺寸），不猜
  const img = new Image()
  img.onload = () => {
    state.value = { ...state.value, srcMeta: { width: img.naturalWidth, height: img.naturalHeight } }
  }
  img.onerror = () => {
    state.value = { ...state.value, srcMeta: null }
  }
  img.src = state.value.srcUrl
}

function pickFile() {
  if (running.value) return
  if (fileInputEl.value) fileInputEl.value.click()
}

function onFileInput(e) {
  const f = e.target.files && e.target.files[0]
  if (f) acceptFile(f, 'file')
  e.target.value = '' // 允许再次选同一文件
}

function onDragOver() {
  if (!running.value) dragged.value = true
}

function onDrop(e) {
  dragged.value = false
  const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]
  if (f) acceptFile(f, 'drop')
}

function onDropzoneKey(e) {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    pickFile()
  }
}

// ── ③ 剪贴板粘贴（仅本页激活期间监听；输入框里粘贴放行不拦截）──────────────
function stampName() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(
    d.getMinutes()
  )}${p(d.getSeconds())}`
}

function extOf(mime, fallbackName) {
  const m = String(mime || '').toLowerCase()
  if (m === 'image/png') return 'png'
  if (m === 'image/jpeg') return 'jpg'
  if (m === 'image/webp') return 'webp'
  if (m === 'image/tiff') return 'tif'
  if (m === 'image/gif') return 'gif'
  if (m === 'image/bmp') return 'bmp'
  const m2 = /\.([a-z0-9]+)$/i.exec(fallbackName || '')
  return m2 ? m2[1].toLowerCase() : 'png'
}

function onPaste(ev) {
  // 在输入框 / 文本域 / 可编辑区里粘贴 ⇒ 放行（不拦截用户的文字粘贴）
  const t = ev.target
  const tag = (t && t.tagName ? String(t.tagName).toLowerCase() : '')
  if (tag === 'input' || tag === 'textarea' || tag === 'select' || (t && t.isContentEditable)) return

  const items = ev.clipboardData && ev.clipboardData.items
  const imgs = []
  if (items) {
    for (let i = 0; i < items.length; i += 1) {
      const it = items[i]
      if (it && it.kind === 'file' && String(it.type || '').startsWith('image/')) imgs.push(it)
    }
  }
  if (!imgs.length) {
    clipboardCount.value = 0
    pasteNote.value = '剪贴板里没有图片（截图请先复制到剪贴板）'
    return
  }
  const raw = imgs[0].getAsFile()
  if (!raw) {
    clipboardCount.value = 0
    pasteNote.value = '剪贴板里没有图片（该条目取不到文件）'
    return
  }
  const ext = extOf(raw.type, raw.name)
  // 稳定文件名（后端不看文件名，但下载 / 排查需要可读名）
  const named = new File([raw], `clipboard-${stampName()}.${ext}`, { type: raw.type || 'image/png' })
  clipboardCount.value = imgs.length
  pasteNote.value = imgs.length > 1 ? `剪贴板含 ${imgs.length} 张，已取第 1 张` : '已从剪贴板取到 1 张图'
  acceptFile(named, 'paste') // ← 与选择 / 拖拽**同一条链路**，不自动提交
}

onMounted(() => {
  window.addEventListener('paste', onPaste)
})
onBeforeUnmount(() => {
  window.removeEventListener('paste', onPaste)
  if (tickTimer) clearInterval(tickTimer)
  tickTimer = null
  revoke(state.value.srcUrl)
  if (result.value && result.value.viewUrl) revoke(result.value.viewUrl)
})

// ── 宽度校验（失焦就地提示；越界不发请求）────────────────────────────────
function validateWidth() {
  const raw = String(widthInput.value).trim()
  if (!/^\d+$/.test(raw)) {
    widthError.value = '宽度须为整数像素（200–4000）'
    return null
  }
  const n = Number(raw)
  if (n < 200 || n > 4000) {
    widthError.value = `宽度越界：${n}（须在 200–4000 px 之间）`
    return null
  }
  widthError.value = ''
  return n
}

function onWidthInput() {
  const raw = String(widthInput.value).trim()
  if (raw === '') {
    widthError.value = '宽度不能为空（200–4000）'
    return
  }
  validateWidth()
}

// ── ② 请求 ────────────────────────────────────────────────────────────────
async function run() {
  if (!state.value.file || running.value) return
  const w = validateWidth()
  if (w === null) return
  resetOutput()
  running.value = true
  elapsedTick.value = 0
  tickTimer = setInterval(() => {
    elapsedTick.value += 1
  }, 1000)
  try {
    const res = await enhanceImage(state.value.file, { width: w, background: background.value })
    if (res.ok && res.body && res.body.ok === true) {
      result.value = {
        ...res.body,
        viewUrl: URL.createObjectURL(base64ToBlob(res.body.image_base64, res.body.mime || 'image/png')),
      }
    } else {
      failure.value = {
        kind: 'error',
        status: res.status,
        error: (res.body && res.body.error) || '',
        reason: (res.body && res.body.reason) || '',
        detail: (res.body && res.body.detail) || '',
        raw: res.raw || '',
      }
    }
  } catch (e) {
    const f = describeFailure(e)
    if (f.kind === 'backend-down') markBackendDown(f.detail)
    failure.value = {
      kind: f.kind === 'backend-down' ? 'backend-down' : 'error',
      status: '',
      error: f.kind === 'backend-down' ? 'BACKEND_UNREACHABLE' : '',
      reason: f.message,
      raw: '',
    }
  } finally {
    running.value = false
    if (tickTimer) clearInterval(tickTimer)
    tickTimer = null
  }
}

function download() {
  if (!result.value) return
  const url = result.value.viewUrl
  const a = document.createElement('a')
  a.href = url
  a.download = `feicui-enhance-${result.value.width}w.png`
  document.body.appendChild(a)
  a.click()
  a.remove()
}

function clearAll() {
  revoke(state.value.srcUrl)
  resetOutput()
  state.value = { file: null, origin: '', srcUrl: '', srcMeta: null }
  pasteNote.value = ''
  clipboardCount.value = 0
  dragged.value = false
}
</script>

<template>
  <section class="enhance">
    <header class="page__head">
      <h2>图片高清化</h2>
      <p class="page__sub">
        上传／拖入／粘贴一张印章图 ⇒ 后端按<b>统一成品规格</b>输出一张成品 PNG（默认宽 1200 px，高度按原图比例）。
        印章本体像素只做 Lanczos 几何重采样，不做任何颜色处理；背景可选宣纸底纹或纯白。
      </p>
      <p class="page__sub muted">
        口径提示：原图有多少细节，成品就只有多少——本页统一的是<b>尺寸</b>与<b>纸底</b>，不是让细节变多。
      </p>
    </header>

    <!-- ── 输入区 ─────────────────────────────────────────────────────── -->
    <div class="card">
      <div class="card__head">
        <h3>① 选择图片（单张）</h3>
        <button v-if="state.file" class="ghost" type="button" :disabled="running" @click="clearAll">
          清空
        </button>
      </div>

      <div
        class="dropzone"
        :class="{ 'dropzone--over': dragged, 'dropzone--busy': running }"
        role="button"
        tabindex="0"
        aria-label="选择或拖入一张印章图片；也可以直接按 Command+V 粘贴剪贴板里的截图"
        aria-describedby="enhance-dropzone-hint"
        @click="pickFile"
        @keydown="onDropzoneKey"
        @dragover.prevent="onDragOver"
        @dragenter.prevent="onDragOver"
        @dragleave.prevent="dragged = false"
        @drop.prevent="onDrop"
      >
        <p class="dropzone__title">把印章图片拖到这里，或点此选择文件</p>
        <p id="enhance-dropzone-hint" class="dropzone__hint">
          单张 · PNG / JPEG / WebP / TIFF 等（凡可解码的图片皆可）；也可以直接 ⌘V 粘贴截图
        </p>
        <p class="dropzone__hint">
          <button class="ghost" type="button" :disabled="running" @click.stop="pickFile">
            选择图片文件…
          </button>
        </p>
        <input
          ref="fileInputEl"
          class="dropzone__file"
          type="file"
          accept="image/*"
          :disabled="running"
          @change="onFileInput"
        />
      </div>

      <p v-if="pasteNote" class="enhance__paste" aria-live="polite">{{ pasteNote }}</p>

      <div v-if="state.file" class="enhance__picked">
        <img v-if="state.srcUrl" class="enhance__thumb" :src="state.srcUrl" alt="待处理的印章原图缩略图" />
        <ul class="enhance__meta">
          <li>文件名：<code>{{ state.file.name || '（无文件名）' }}</code></li>
          <li>
            原始尺寸：
            <b v-if="state.srcMeta">{{ state.srcMeta.width }} × {{ state.srcMeta.height }} px</b>
            <span v-else class="muted">读取中…</span>
          </li>
          <li>文件大小：<b>{{ fmtBytes(state.file.size) }}</b> · 类型：<code>{{ state.file.type || '未知' }}</code></li>
          <li>来源：<b>{{ state.origin === 'paste' ? '剪贴板粘贴' : state.origin === 'drop' ? '拖拽' : '文件选择' }}</b></li>
        </ul>
      </div>
    </div>

    <!-- ── 参数区 ─────────────────────────────────────────────────────── -->
    <div class="card">
      <div class="card__head"><h3>② 成品参数</h3></div>
      <div class="field-row">
        <label class="field field--sm">
          <span class="field__label">成品宽度 width（px，200–4000；默认 1200，高度按原图比例）</span>
          <input
            v-model="widthInput"
            type="number"
            min="200"
            max="4000"
            step="1"
            inputmode="numeric"
            :disabled="running"
            @input="onWidthInput"
            @blur="validateWidth"
          />
        </label>
        <div class="field">
          <span class="field__label">底色 background</span>
          <div class="field-row enhance__radios">
            <label class="field field--check">
              <input v-model="background" type="radio" value="paper" :disabled="running" />
              <span>宣纸底纹（paper）</span>
            </label>
            <label class="field field--check">
              <input v-model="background" type="radio" value="plain_white" :disabled="running" />
              <span>纯白（plain_white）</span>
            </label>
          </div>
        </div>
      </div>
      <p v-if="widthError" class="errlist enhance__widtherr">{{ widthError }}（未发出请求）</p>

      <div class="actions">
        <button type="button" :disabled="!canRun" @click="run">
          {{ running ? `处理中…（已 ${elapsedTick}s）` : '开始处理' }}
        </button>
        <span class="muted">
          请求：<code>POST /api/tools/enhance</code>（multipart/form-data · image / width / background）
        </span>
      </div>
    </div>

    <!-- ── 处理中 ─────────────────────────────────────────────────────── -->
    <StateNotice
      v-if="running"
      kind="loading"
      title="正在处理（worker 子进程计算中）"
      :detail="`已等待 ${elapsedTick}s；后端不做假进度，只报真实耗时。`"
    />

    <!-- ── 错误态（原样展示）─────────────────────────────────────────── -->
    <StateNotice
      v-if="failure && failure.kind === 'backend-down'"
      kind="backend-down"
      title="后端未启动 / 未连接：请求未到达"
      :detail="failure.reason || '—'"
    />
    <StateNotice
      v-else-if="failure && failure.kind === 'error'"
      kind="error"
      title="处理失败（后端返回原样展示）"
      :status-code="failure.status || ''"
      :raw-text="failure.raw"
      :detail="`error = ${failure.error || '（响应无 error 字段）'} · reason = ${failure.reason || '（响应无 reason 字段）'}`"
    />

    <!-- ── 结果区 ─────────────────────────────────────────────────────── -->
    <div v-if="result" class="card">
      <div class="card__head">
        <h3>③ 结果（原图 ｜ 成品）</h3>
        <button type="button" @click="download">下载 PNG</button>
      </div>

      <div class="enhance__pair">
        <figure class="enhance__fig">
          <figcaption>原图</figcaption>
          <img :src="state.srcUrl" alt="原图" class="enhance__img" />
          <div class="enhance__figmeta">
            {{ result.source.width }} × {{ result.source.height }} px · {{ result.source.mode }} ·
            {{ fmtBytes(result.source.bytes) }}
          </div>
        </figure>
        <figure class="enhance__fig">
          <figcaption>成品（{{ BACKGROUND_LABELS[result.params_used.background] || result.params_used.background }}）</figcaption>
          <img :src="result.viewUrl" alt="成品图（后端生成）" class="enhance__img" />
          <div class="enhance__figmeta">
            {{ result.width }} × {{ result.height }} px · PNG · {{ fmtBytes(result.bytes) }}
          </div>
        </figure>
      </div>

      <h4>读数（全部取后端响应，本地不复算）</h4>
      <table class="table">
        <tbody>
          <tr>
            <th>成品尺寸</th>
            <td><b>{{ result.width }} × {{ result.height }}</b> px（宽 ＝ 请求 width）</td>
          </tr>
          <tr>
            <th>成品字节</th>
            <td>{{ result.bytes }} B（{{ fmtBytes(result.bytes) }}）</td>
          </tr>
          <tr>
            <th>sha256（前 12 位）</th>
            <td><code>{{ (result.sha256 || '').slice(0, 12) }}</code></td>
          </tr>
          <tr>
            <th>耗时</th>
            <td>{{ result.elapsed_ms }} ms（含 worker 子进程启动）</td>
          </tr>
          <tr>
            <th>所用参数</th>
            <td>
              width={{ result.params_used.width }} · background={{ result.params_used.background }} ·
              caliber={{ result.params_used.caliber }} · subject_ratio={{ result.params_used.subject_ratio }} ·
              seed={{ result.params_used.seed }} · halo_policy={{ result.params_used.halo_policy }}
            </td>
          </tr>
          <tr>
            <th>算法读数</th>
            <td>
              画布尺寸 {{ result.readings?.composition?.canvas_size?.join(' × ') || '—' }} px ·
              主体占比 {{ result.readings?.composition?.subject_ratio_actual ?? '—' }}（目标
              {{ result.readings?.composition?.subject_ratio_target ?? '—' }}）·
              印区像素＝纯重采样：<b>{{ result.readings?.freeze?.bit_exact_no_color_processing ? '是' : '否' }}</b> ·
              纸底无印泥：<b>{{ result.readings?.bg_no_seal?.ok ? '是' : '否' }}</b> ·
              晕染合规：<b>{{ result.readings?.halo?.ok ? '是' : '否' }}</b>
            </td>
          </tr>
          <tr v-if="clipboardCount > 1">
            <th>剪贴板</th>
            <td>剪贴板含 {{ clipboardCount }} 张，已取第 1 张</td>
          </tr>
        </tbody>
      </table>
      <p class="muted">
        下载文件名：<code>feicui-enhance-{{ result.width }}w.png</code>（PNG 无损；细节以原图为准，
        本页只统一尺寸与纸底）。
      </p>
    </div>
  </section>
</template>

<style scoped>
.enhance__paste {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--accent-deep);
}
.enhance__picked {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  margin-top: 10px;
  padding: 8px 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--bg-soft);
}
.enhance__thumb {
  max-width: 180px;
  max-height: 180px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--card);
}
.enhance__meta {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  color: var(--text);
}
.enhance__meta li {
  margin: 2px 0;
}
.enhance__radios {
  gap: 12px;
}
.enhance__widtherr {
  font-size: 12px;
}
.enhance__pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin: 8px 0 4px;
}
.enhance__fig {
  margin: 0;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--bg-soft);
  padding: 8px;
  min-width: 0;
}
.enhance__fig figcaption {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 6px;
}
/* 成品按容器宽自适应，**不放大**超过自然宽度（max-width:100% ＋ height:auto） */
.enhance__img {
  display: block;
  max-width: 100%;
  height: auto;
  border-radius: 6px;
  background: var(--card);
}
.enhance__figmeta {
  margin-top: 6px;
  font-size: 11.5px;
  color: var(--muted);
}
@media (max-width: 760px) {
  .enhance__pair {
    grid-template-columns: 1fr;
  }
}
</style>
