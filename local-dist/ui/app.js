/* local-dist/ui/app.js —— 斐萃 本地封装分发版：三 tab UI 逻辑（纯本地 JS，无 CDN 依赖）
 *
 * 桥：window.pywebview.api[method](payload) —— 由 pywebview 注入（唯一形态＝原生窗口）。
 * 进度：Python 端 `window.evaluate_js('window.onProgress(…)')` 推；另有 1.5 s 轮询兜底。
 */
(function () {
  'use strict';

  var ST = {                     // 页面状态（单页应用的手写小 store）
    user: null, root: '', navPath: '',
    yy: { connected: false, prefix: '', label: '' },   // yinyuan 连接态（**只有 prefix**）
    tab1: { rows: [], items: [], selected: null, options: [] },
    tab2: {
      sources: [], job: null, lastPath: '',
      // 切图台（Phase B）：items＝2_HighRes_PDF 下的高清 PDF；boxes＝**400dpi 页坐标**的手工可编辑框
      ct: { items: [], pdf: '', pdfName: '', page: 1, pages: null, boxes: [], sel: -1,
            img: null, scale: 1, size: [0, 0], boxesDpi: 400, drag: null, dirKey: '', srcDir: '',
            // 字段区（2026-10-20）：fields 与 boxes **同序**；orderResolved＝后端推断的阅读顺序
            fields: [], orderResolved: '', orderSource: '', bookDynasty: '', bookAuthor: '',
            bookOrder: 'auto' }
    },
    // tab3：curSubdir / files / view(四档) / page(分页) / selected / 解析回填与本地记录
    tab3: {
      subdirs: [], files: [], curSubdir: '', view: '', page: 0, selected: '',
      cfg: null, limits: null, isAdmin: false, els: {}, pageNames: [],
      thumbStat: null, previewStat: null, lastCheck: null, versions: 0,
      // OCR 试试看：corrHits = 当前展示的纠错建议；ocrRaw = 这些建议所基于的释文文本
      corrHits: [], ocrRaw: ''
    }
  };

  // ───────────── 桥：就绪检测 + 调用 ─────────────
  var bridgeReady = false;
  window.addEventListener('pywebviewready', function () { bridgeReady = true; setModeLabel(true); });
  setTimeout(function () { setModeLabel(!!(window.pywebview && window.pywebview.api)); }, 400);

  function hasBridge() { return !!(window.pywebview && window.pywebview.api); }

  function call(method, payload) {
    if (!hasBridge()) {
      return Promise.reject(new Error('pywebview 桥未就绪（应以 ./venv/bin/python local-dist/app.py 启动）'));
    }
    return Promise.resolve(window.pywebview.api[method](payload || {}))
      .then(function (r) {
        if (r && typeof r === 'object' && r.ok === false) { toast(r.msg || '操作失败', true); }
        return r;
      })
      .catch(function (e) { toast('调用 ' + method + ' 失败：' + (e && e.message ? e.message : e), true); throw e; });
  }

  function setModeLabel(native) {
    var el = document.getElementById('mode-label');
    if (!el) return;
    el.textContent = (window.pywebview && window.pywebview.api)
      ? '原生窗口（PyWebView）' : (native ? '原生窗口（PyWebView）' : '窗口未就绪…');
  }

  // ───────────── 小工具 ─────────────
  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s === null || s === undefined ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function toast(msg, isErr) {
    var t = $('toast');
    t.textContent = msg;
    t.style.background = isErr ? '#d93025' : '#333';
    t.classList.add('show');
    setTimeout(function () { t.classList.remove('show'); }, 3200);
  }
  function setMsg(id, text, cls) {
    var el = $(id); if (!el) return;
    el.textContent = text || '';
    el.className = 'msg' + (cls ? ' ' + cls : '');
  }
  function show(view) {
    ['view-login', 'view-dir', 'view-main'].forEach(function (v) {
      $(v).classList.toggle('active', v === view);
    });
  }

  // ───────────── 登录 ─────────────
  function bindLogin() {
    $('btn-login').addEventListener('click', doLogin);
    $('login-pwd').addEventListener('keydown', function (e) { if (e.key === 'Enter') doLogin(); });
  }
  function doLogin() {
    var u = $('login-user').value.trim(), p = $('login-pwd').value;
    if (!u || !p) { setMsg('login-msg', '请输入账号与密码', 'err'); return; }
    call('login', { username: u, password: p }).then(function (r) {
      if (!r || !r.ok) { setMsg('login-msg', (r && r.msg) || '登录失败', 'err'); return; }
      ST.user = r.user; $('login-pwd').value = '';
      setMsg('login-msg', '登录成功', 'ok');
      afterAuth();
    }).catch(function () { setMsg('login-msg', '后端不可用', 'err'); });
  }

  function afterAuth() {
    $('dir-user').textContent = ST.user.username + (ST.user.is_admin ? '（管理员）' : '');
    $('user-pill').textContent = '👤 ' + ST.user.username + (ST.user.is_admin ? ' · 管理员' : '');
    if (ST.user.feicui_root) { show('view-main'); enterMain(); } else { show('view-dir'); browseHome(); }
  }

  // ───────────── 目录选择 / 校验 ─────────────
  function browse(path, silent) {
    call('browse', { path: path || '' }).then(function (r) {
      if (!r || !r.ok) { if (!silent) setMsg('dir-msg', (r && r.msg) || '浏览失败', 'err'); return; }
      ST.navPath = r.path;
      $('dir-path').textContent = r.path;
      var box = $('dir-entries');
      box.innerHTML = '';
      r.entries.forEach(function (name) {
        var li = document.createElement('li');
        li.textContent = '📁 ' + name;
        li.addEventListener('click', function () { browse(r.path + '/' + name, false); });
        box.appendChild(li);
      });
      if (!r.entries.length) { box.innerHTML = '<li class="muted">（无子目录）</li>'; }
      if (r.is_feicui) { setMsg('dir-msg', '这是 feicui 目录，可以校验并进入', 'ok'); }
      else { setMsg('dir-msg', ''); }
    });
  }
  function browseHome() { browse(''); }
  function browseUp() {
    call('browse', { path: ST.navPath || '' }).then(function (r) {
      if (r && r.ok) browse(r.parent, true);
    });
  }
  function verifyDir() {
    call('verify_dir', { path: ST.navPath }).then(function (r) {
      if (!r || !r.ok) { setMsg('dir-msg', (r && r.msg) || '校验失败', 'err'); return; }
      ST.root = r.feicui_root; ST.user.feicui_root = ST.root;
      setMsg('dir-msg', r.msg, 'ok');
      show('view-main'); enterMain();
    });
  }
  function ensureSubdirs() {
    call('ensure_subdirs', { path: ST.navPath }).then(function (r) {
      setMsg('dir-msg', (r && r.msg) || '', r && r.ok ? 'ok' : 'err');
    });
  }
  function changeDir() { show('view-dir'); browse(ST.root || ''); }

  // ───────────── 主界面 ─────────────
  function enterMain() {
    $('root-pill').textContent = '📁 ' + (ST.root || '—');
    call('app_info').then(function (r) { if (r && r.ok) { applyBrand(r); } });
    // yinyuan 连接态（只显示 prefix）；未连接 ⇒ 入口按钮保持「连接 yinyuan」
    call('yinyuan_status').then(function (r) { if (r && r.ok) { renderYinyuan(r); } }).catch(function () { });
    loadTab1();
    hrPollOnce();                     // 上一轮高清化可能还在跑（切回来要看到进度）
  }

  // 标题/副标题：**单一真源**在后端（`api.APP_TITLE` / `APP_SLOGAN`），此处只做应用
  function applyBrand(info) {
    if (info.title) {
      document.title = info.title;
      // 注意：topbar 标题在 **内层 span**（外层还有 logo <img>，不能直接覆写 textContent）
      ['brand-title', 'topbar-title-text'].forEach(function (id) {
        if ($(id)) { $(id).textContent = info.title; }
      });
    }
    if (info.slogan && $('brand-slogan')) { $('brand-slogan').textContent = info.slogan; }
    if (info.version) { $('app-version').textContent = 'v' + info.version; }
  }
  function bindTabs() {
    Array.prototype.forEach.call(document.querySelectorAll('#tabs .tab'), function (btn) {
      btn.addEventListener('click', function () { activateTab(btn.dataset.tab); });
    });
  }
  function activateTab(name) {
    Array.prototype.forEach.call(document.querySelectorAll('#tabs .tab'), function (b) {
      b.classList.toggle('active', b.dataset.tab === name);
    });
    Array.prototype.forEach.call(document.querySelectorAll('.panel'), function (p) {
      p.classList.toggle('active', p.dataset.panel === name);
    });
    if (name === '1_Original_PDF') hrPollOnce();          // 回到 tab1 时对齐高清化进度
    if (name === '2_HighRes_PDF') loadTab2();
    if (name === '3_Cropped_Tiff') loadTab3();
  }

  // ── tab1 ──
  function loadTab1(force) {
    setMsg('tab1-msg', '扫描中…');
    call('tab1_list', { force_probe: !!force }).then(function (r) {
      if (!r || !r.ok) { setMsg('tab1-msg', (r && r.msg) || '扫描失败', 'err'); return; }
      ST.tab1.rows = r.rows || []; ST.tab1.items = r.items || []; ST.tab1.options = r.dynasty_options || [];
      $('tab1-count').textContent = String((r.stats && r.stats.count) || 0);
      var s = r.stats || {};
      $('tab1-stats').innerHTML =
        ['共 ' + (s.count || 0) + ' 个 PDF', '合计 ' + ((s.total_bytes || 0) / 1048576).toFixed(1) + ' MB',
          '已读数 ' + (s.with_pages || 0), '已注朝代/作者/备注 ' + (s.annotated || 0),
          '本次新探 ' + (s.probed_now || 0), '探针可用：' + (r.probe_available ? '是' : '否'),
          '侧车：' + (s.meta_store || '')]
          .map(function (t) { return '<span>' + esc(t) + '</span>'; }).join('');
      var tb = $('tab1-body'); tb.innerHTML = '';
      ST.tab1.rows.forEach(function (row, i) {
        var tr = document.createElement('tr');
        ['文件名', '大小(MB)', '页数', '页面尺寸', '扫描dpi(估)', '朝代', '作者', '改时间']
          .forEach(function (k) { var td = document.createElement('td'); td.textContent = row[k]; tr.appendChild(td); });
        tr.addEventListener('click', function () { selectTab1(i, tr); });
        tb.appendChild(tr);
      });
      var sel = $('tab1-dynasty'); sel.innerHTML = '<option value="">（未填）</option>';
      ST.tab1.dynSource = r.dynasty_source || '';
      sel.title = (r.dynasty_source === 'network' || r.dynasty_source === 'cache' ||
        r.dynasty_source === 'cache_stale')
        ? '朝代值域来自 yinyuan（' + r.dynasty_source + '）'
        : '朝代值域＝本地 15 类（未连接 yinyuan 或离线回落）';
      ST.tab1.options.forEach(function (d) {
        var o = document.createElement('option'); o.value = d; o.textContent = d; sel.appendChild(o);
      });
      setMsg('tab1-msg', '扫描完成：' + ST.tab1.rows.length + ' 个 PDF', 'ok');
      renderHrSource();                     // 「⚡ 一键高清化」的源行（取当前选中行）
    });
  }
  function selectTab1(i, tr) {
    Array.prototype.forEach.call(document.querySelectorAll('#tab1-body tr'), function (r) { r.classList.remove('active'); });
    tr.classList.add('active');
    var m = ST.tab1.items[i]; ST.tab1.selected = m;
    $('tab1-selected').textContent = '已选：' + m.filename + (m.page_count ? '（' + m.page_count + ' 页）' : '');
    $('tab1-dynasty').value = m.dynasty || '';
    $('tab1-author').value = m.author || '';
    $('tab1-notes').value = m.notes || '';
    $('tab1-reading-order').value = m.reading_order || 'auto';
    renderHrSource();                       // 高清化卡片跟随选中行
  }
  function saveTab1() {
    if (!ST.tab1.selected) { setMsg('tab1-msg', '请先选中一行', 'err'); return; }
    call('tab1_save_meta', {
      filename: ST.tab1.selected.filename,
      dynasty: $('tab1-dynasty').value,
      author: $('tab1-author').value,
      notes: $('tab1-notes').value,
      reading_order: $('tab1-reading-order').value
    }).then(function (r) {
      setMsg('tab1-msg', (r && r.msg) || '', r && r.ok ? 'ok' : 'err');
      if (r && r.ok) loadTab1(false);
    });
  }

  // ── tab1 · ⚡ 一键高清化（Phase A 后端：tab1_highres_start / status / cancel）──
  //   源＝**当前选中行**；三档 dpi（300/600/1200，默认 1200）＋页区间；后台线程跑，
  //   本页 900 ms 轮询 + `window.onProgress({kind:'tab1_highres'})` 推送兜底。
  var hrTimer = null;

  function hrSource() { var m = ST.tab1.selected; return m ? (m.filename || '') : ''; }

  function renderHrSource() {
    var el = $('tab1-hr-source'), m = ST.tab1.selected;
    if (!el) { return; }
    if (!m) {
      el.textContent = '源 PDF：未选择文件（请先在上方表格点一行）';
      el.classList.add('warn');
      return;
    }
    el.classList.remove('warn');
    el.textContent = '源 PDF：' + m.filename + (m.page_count ? '（' + m.page_count + ' 页）' : '（页数未探）');
  }

  function hrSetBusy(running) {
    $('btn-tab1-hr-start').disabled = !!running;
    $('btn-tab1-hr-cancel').disabled = !running;
  }

  function hrStopPoll() { if (hrTimer) { clearInterval(hrTimer); hrTimer = null; } }

  function hrStartPoll() {
    if (hrTimer) { return; }
    hrTimer = setInterval(function () {
      call('tab1_highres_status').then(function (r) {
        if (r && r.ok) { renderHrStatus(r); }
      }).catch(hrStopPoll);
    }, 900);
  }

  function renderHrStatus(st) {
    if (!st) { return; }
    var total = st.pages_total || 0, done = st.pages_done || 0;
    var pct = total ? Math.min(100, Math.round(done * 100 / total)) :
      (st.state === 'done' ? 100 : 0);
    var mb = ((st.bytes || 0) / 1048576).toFixed(1);
    $('tab1-hr-bar').style.width = pct + '%';
    var line = '[' + (st.state || 'idle') + '] ' + done + '/' + (total || '?') + ' 页 · 累计 ' + mb + ' MB';
    if (st.page) { line += ' · 当前页 ' + st.page; }
    if (st.elapsed_s) { line += ' · ' + st.elapsed_s + ' s'; }
    if (st.msg) { line += ' · ' + st.msg; }
    $('tab1-hr-msg').textContent = line;
    var running = (st.state === 'running' || st.state === 'queued');
    hrSetBusy(running);
    if (running) { hrStartPoll(); } else { hrStopPoll(); }
    if (st.state === 'done') {
      $('tab1-hr-done').hidden = false;
      $('tab1-hr-out').textContent = '✅ ' + (st.out || '—') + '（' + done + ' 页 · ' + mb + ' MB）';
      setMsg('tab1-hr-err', '完成：' + (st.out || ''), 'ok');
    } else if (st.state === 'failed') {
      $('tab1-hr-done').hidden = true;
      setMsg('tab1-hr-err', '❌ 失败：' + (st.error || st.msg || ''), 'err');
    } else if (st.state === 'cancelled') {
      setMsg('tab1-hr-err', (st.msg || '已取消') + '（进度保留，可续跑）', 'err');
    }
  }

  function hrStart() {
    var pdf = hrSource();
    if (!pdf) { setMsg('tab1-hr-err', '请先在上方表格选中一行（源 PDF 取当前选中行）', 'err'); return; }
    var from = ($('tab1-hr-from').value || '').trim();
    var to = ($('tab1-hr-to').value || '').trim();
    var payload = { pdf: pdf, dpi: parseInt($('tab1-hr-dpi').value || '1200', 10) };
    if (from) { payload.page_from = parseInt(from, 10); }
    if (to) { payload.page_to = parseInt(to, 10); }
    hrSetBusy(true);
    $('tab1-hr-done').hidden = true;
    setMsg('tab1-hr-err', '已提交（后台线程，UI 不阻塞）…');
    call('tab1_highres_start', payload).then(function (r) {
      if (!r || !r.ok) {
        hrSetBusy(false);
        var why = (r && r.reason) || '';
        var m = (r && r.msg) || '启动失败';
        if (why === 'BAD_DPI' && r.allowed) { m += '（允许：' + r.allowed.join(' / ') + '）'; }
        if (why === 'BUSY' && r.status) {
          renderHrStatus(r.status);
        }
        setMsg('tab1-hr-err', '❌ ' + why + ' ' + m, 'err');
        return;
      }
      setMsg('tab1-hr-err', '已开始：' + (r.out || '') + '（' + r.dpi + ' dpi · ' +
        (r.note || '≈6.2 s/页') + '）', 'ok');
      hrStartPoll();
      call('tab1_highres_status').then(function (s) { if (s && s.ok) { renderHrStatus(s); } });
    });
  }

  function hrCancel() {
    call('tab1_highres_cancel').then(function (r) {
      setMsg('tab1-hr-err', (r && r.msg) || (r && r.ok ? '已请求取消' : '没有在跑的高清化任务'),
        r && r.ok ? 'ok' : 'err');
    });
  }

  function hrPollOnce() {
    call('tab1_highres_status').then(function (r) {
      if (r && r.ok) { renderHrStatus(r); }
    }).catch(function () { });
  }

  // ── tab2 ──
  function loadTab2() {
    call('tab2_list').then(function (r) {
      if (!r || !r.ok) { setMsg('tab2-msg', (r && r.msg) || '加载失败', 'err'); return; }
      ST.tab2.sources = r.sources || []; ST.tab2.lastPath = r.out_dir || '';
      var sel = $('tab2-source'); sel.innerHTML = '';
      ST.tab2.sources.forEach(function (s) {
        var o = document.createElement('option');
        o.value = s.filename; o.textContent = s.filename + '  →  ' + s.dir_key;
        sel.appendChild(o);
      });
      if (!ST.tab2.sources.length) { sel.innerHTML = '<option value="">（1_Original_PDF 下无 PDF）</option>'; }
      var box = $('tab2-products'); box.innerHTML = '';
      (r.dirs || []).forEach(function (d) {
        var h = document.createElement('div'); h.className = 'dirkey';
        h.textContent = '📂 ' + d.dir_key + '（' + d.file_count + ' 个）';
        box.appendChild(h);
        d.files.forEach(function (f) {
          var row = document.createElement('div'); row.className = 'file';
          row.innerHTML = '<span>' + esc(f.name) + '</span><span class="muted">' + f.size_mb + ' MB · ' + esc(f.mtime) + '</span>';
          box.appendChild(row);
        });
      });
      if (!(r.dirs || []).length) { box.innerHTML = '<div class="muted">（2_HighRes_PDF 下暂无产物）</div>'; }
      if (!r.engine.exists) { setMsg('tab2-msg', '引擎脚本缺失：' + r.engine.script, 'err'); }
      else if (r.jobs && r.jobs.length) { renderJob(r.jobs[0]); }
      loadTab2Sources();                    // 切图台的源列表（2_HighRes_PDF/**/*.pdf）
    });
  }
  function generateTab2() {
    var payload = {
      filename: $('tab2-source').value,
      page: parseInt($('tab2-page').value || '1', 10),
      dpi: parseInt($('tab2-dpi').value || '1200', 10),
      overwrite: $('tab2-overwrite').checked,
      force: $('tab2-force').checked
    };
    if (!payload.filename) { setMsg('tab2-msg', '请在 1_Original_PDF 放入 PDF 后刷新', 'err'); return; }
    setMsg('tab2-msg', '已提交（异步）…');
    call('tab2_generate', payload).then(function (r) {
      setMsg('tab2-msg', (r && r.msg) || '', r && r.ok ? 'ok' : 'err');
      if (r && r.ok && r.job) { renderJob(r.job); startPolling(r.job.job_id); }
    });
  }
  function cancelTab2() {
    if (!ST.tab2.job) return;
    call('tab2_cancel', { job_id: ST.tab2.job.job_id }).then(function (r) {
      setMsg('tab2-msg', (r && r.msg) || '', r && r.ok ? 'ok' : 'err');
    });
  }
  function renderJob(job) {
    if (!job) return;
    ST.tab2.job = job;
    $('tab2-progress-bar').style.width = (job.percent || 0) + '%';
    $('tab2-progress-msg').textContent = '[' + job.state + '] ' + (job.message || '') +
      ' — ' + (job.percent || 0) + '%' + (job.out ? ' → ' + job.out : '');
    $('tab2-log').textContent = job.log_tail || '';
    var running = job.state === 'running' || job.state === 'queued';
    $('btn-tab2-cancel').disabled = !running;
    $('btn-tab2-generate').disabled = running;
    if (!running && job.state === 'done') { loadTab2ProductsOnly(); }
  }
  function loadTab2ProductsOnly() {
    call('tab2_list').then(function (r) { if (r && r.ok) { ST.tab2.sources = r.sources || []; } });
  }
  var pollTimer = null;
  function startPolling(jobId) {
    if (pollTimer) { clearInterval(pollTimer); }
    pollTimer = setInterval(function () {
      call('tab2_job', { job_id: jobId }).then(function (r) {
        if (!r || !r.ok) { return; }
        renderJob(r.job);
        if (['done', 'error', 'cancelled'].indexOf(r.job.state) >= 0) {
          clearInterval(pollTimer); pollTimer = null; loadTab2();
        }
      }).catch(function () { clearInterval(pollTimer); pollTimer = null; });
    }, 1500);
  }
  // Python 端进度推送入口（pywebview evaluate_js）
  window.onProgress = function (job) {
    if (!job) return;
    if (job.kind === 'tab1_highres') { renderHrStatus(job); return; }   // tab1 一键高清化
    if (!ST.tab2.job || ST.tab2.job.job_id === job.job_id) { renderJob(job); }
  };
  function openInFinder() {
    var first = document.querySelector('#tab2-products .file span');
    call('open_in_finder', { path: ST.tab2.lastPath }).then(function (r) {
      setMsg('tab2-msg', (r && r.msg) || '', r && r.ok ? 'ok' : 'err');
    });
  }

  // ═════════ 切图台（phase B）：源列表 → 选页 → 400dpi 自动检测 → 画布微调 → 1200dpi 裁切 ═════════
  //   坐标口径：**框一律存 400dpi 页坐标**（＝后端 tab2_detect / tab2_crop 与库内 bbox 同系），
  //   画布上的一切换算只经 `ct.scale`（＝后端 preview_scale；预览已由后端画框图并降采样到宽 ≤1000）。
  function ctState() { return ST.tab2.ct; }

  function ctItem() {
    var v = $('tab2-ct-source').value, items = ctState().items || [];
    for (var i = 0; i < items.length; i++) {
      if ((items[i].path || items[i].name) === v) { return items[i]; }
    }
    return null;
  }

  function ctUpdateCount() {
    var ct = ctState(), n = ct.boxes.length;
    $('tab2-box-count').textContent = '检测到 ' + n + ' 枚';
    var btn = $('btn-tab2-crop');
    btn.textContent = '✂️ 裁切选中（' + n + '）';
    btn.disabled = (n === 0);
    var cv = $('tab2-canvas');
    if (cv) {
      cv.dataset.boxes = String(n);
      cv.dataset.page = String(ct.page || 1);
      cv.dataset.scale = String(ct.scale || 1);
    }
  }

  function ctUpdatePageInfo() {
    var ct = ctState();
    $('tab2-ct-pageinfo').textContent = '第 ' + (ct.page || 1) + ' / ' + (ct.pages || '?') +
      ' 页 · 检测坐标系 400dpi';
  }

  // ───── 字段区（释文/状态/编号 + 阅读顺序 + 裁切文件名预演）─────
  //   口径与后端 `src/field_extract.py` / `src/seal_crop.py` **逐条对齐**：
  //   ① C/R 方向跟随阅读顺序（rtl ⇒ 右列 C1；btt ⇒ 下行 R1）；② 有编号 ⇒ 编号前缀名，
  //   否则 `P<页>-C<列>-R<行>.tiff`；③ 段清洗（非法字符→`-`、折叠、去首尾、空⇒NA）、整名 >200 截断。
  function foNormalize(v) {
    var parts = String(v || '').toLowerCase().split(/[-_\s]+/), h = null, vt = null;
    parts.forEach(function (p) {
      if (p === 'rtl' || p === 'ltr') { h = p; }
      if (p === 'ttb' || p === 'btt') { vt = p; }
    });
    return (h && vt) ? (h + '-' + vt) : '';
  }

  // 生效的阅读顺序：下拉显式值 > 后端推断值 > 本书元数据 > ltr-ttb（＝改动前行为）
  function foEffective() {
    var ct = ctState(), v = $('tab2-read-order') ? $('tab2-read-order').value : 'auto';
    if (v && v !== 'auto') { return foNormalize(v) || 'ltr-ttb'; }
    return ct.orderResolved || foNormalize(ct.bookOrder) || 'ltr-ttb';
  }

  // 与后端 grid_positions 同规则：行带按垂直重叠 ≥ 0.5×较矮框高聚类
  function foGrid(boxes, order) {
    var horiz = (order.indexOf('rtl') === 0) ? 'rtl' : 'ltr';
    var vert = (order.slice(-3) === 'btt') ? 'btt' : 'ttb';
    var info = boxes.map(function (b, i) {
      return { i: i, y1: b.y1, y2: b.y2, cx: (b.x1 + b.x2) / 2, cy: (b.y1 + b.y2) / 2,
               h: Math.max(1, b.y2 - b.y1) };
    });
    var bands = [];
    info.slice().sort(function (a, b) { return (a.cy - b.cy) || (a.cx - b.cx) || (a.i - b.i); })
      .forEach(function (it) {
        var placed = false;
        bands.forEach(function (band) {
          if (placed) { return; }
          var top = Math.min.apply(null, band.map(function (x) { return x.y1; }));
          var bot = Math.max.apply(null, band.map(function (x) { return x.y2; }));
          var od = Math.min(bot, it.y2) - Math.max(top, it.y1);
          var short = Math.min(Math.min.apply(null, band.map(function (x) { return x.h; })), it.h);
          if (od >= 0.5 * short) { band.push(it); placed = true; }
        });
        if (!placed) { bands.push([it]); }
      });
    var out = new Array(info.length);
    bands.forEach(function (band, bi) {
      var r = (vert === 'ttb') ? (bi + 1) : (bands.length - bi);
      var sorted = band.slice().sort(function (a, b) { return (a.cx - b.cx) || (a.i - b.i); });
      if (horiz === 'rtl') { sorted.reverse(); }
      sorted.forEach(function (it, ci) { out[it.i] = { c: ci + 1, r: r }; });
    });
    return out;
  }

  function foSanitize(v) {
    var s = (v === null || v === undefined) ? '' : String(v);
    s = s.replace(/[\/\\:*?"<>|\r\n\t]+/g, '-').replace(/-{2,}/g, '-')
      .replace(/^[-\s]+/, '').replace(/[-\s]+$/, '');
    return s || 'NA';
  }

  // 裁切文件名预演（与 `seal_crop.build_crop_name` 同规则；越界/超长策略一致）
  //   段顺序＝**释文_朝代_作者**（与后端/文档/示例一致），截断顺序 ins → aut → dyn 也与后端 `_fit_name` 一致。
  function foName(page, c, r, f) {
    var ct = ctState(), code = (f && f.code) ? String(f.code).trim() : '';
    if (!code) { return 'P' + (page || 1) + '-C' + c + '-R' + r + '.tiff'; }
    var prefix = foSanitize(code) + '_P' + (page || 1) + '_C' + c + '_R' + r + '_';
    var vals = {
      ins: foSanitize((f && f.inscription) || ''),
      aut: foSanitize((f && f.author) || ct.bookAuthor),
      dyn: foSanitize((f && f.dynasty) || ct.bookDynasty)
    };
    function build() { return prefix + vals.ins + '_' + vals.dyn + '_' + vals.aut + '.tiff'; }
    ['ins', 'aut', 'dyn'].forEach(function (k) {
      while (build().length > 200 && vals[k].length > 4) { vals[k] = vals[k].slice(0, -1); }
    });
    var name = build();
    if (name.length > 200) { name = name.slice(0, 199) + '~'; }
    return name;
  }

  function foScore(f) {
    var sc = f && f.inscription_score;
    var txt = (sc === null || sc === undefined) ? '—' : Number(sc).toFixed(2);
    return txt + ((f && f.needs_review) ? ' ⚠' : '');
  }

  function ctRenderFields() {
    var ct = ctState(), box = $('tab2-fields');
    if (!box) { return; }
    ct.fields = ct.fields || [];
    while (ct.fields.length < ct.boxes.length) { ct.fields.push({}); }
    if (ct.fields.length > ct.boxes.length) { ct.fields = ct.fields.slice(0, ct.boxes.length); }
    var pos = foGrid(ct.boxes, foEffective());
    box.innerHTML = '';
    ct.boxes.forEach(function (b, i) {
      var f = ct.fields[i] || {}, p = pos[i] || { c: '?', r: '?' };
      var row = document.createElement('div');
      row.className = 'frow' + (f.needs_review ? ' rev' : '');
      row.dataset.i = String(i);
      row.innerHTML = '<span class="fno">#' + esc(f.read_order || (i + 1)) + '</span>'
        + '<input class="fin" data-k="inscription" maxlength="40" placeholder="释文" value="'
        + esc(f.inscription || '') + '">'
        + '<input class="fin" data-k="status" maxlength="4" placeholder="状态" value="'
        + esc(f.status || '') + '">'
        + '<input class="fin" data-k="code" maxlength="8" placeholder="编号" value="'
        + esc(f.code || '') + '">'
        + '<span class="fscore">' + esc(foScore(f)) + '</span>'
        + '<span class="fname" title="裁切文件名">' + esc(foName(ct.page, p.c, p.r, f)) + '</span>';
      box.appendChild(row);
    });
    if (!ct.boxes.length) {
      box.innerHTML = '<div class="muted">（先「🔍 自动检测」：检测后每枚印一行，三字段可直接改）</div>';
    }
    // 来源标签**带上后端原值**（`code-sequence` / `manual` / `book-meta` / `fallback`）：
    // 中文说明给人看，原值给 DOM 断言与排障用（否则「机器推的」与「人选的」在界面上无从区分）。
    var src = ct.orderSource === 'code-sequence'
      ? '自动 ⇒ ' + (ct.orderResolved || '?') + '（code-sequence：按编号序列推断）'
      : (ct.orderSource === 'manual' ? '手动：' + (ct.orderResolved || '?') + '（manual）'
        : (ct.orderSource ? '兜底：' + (ct.orderResolved || '?') + '（' + ct.orderSource + '）' : '—'));
    if ($('tab2-order-src')) { $('tab2-order-src').textContent = src; }
  }

  // 只刷新某一行的文件名预演（输入时不重绘，避免丢焦点）
  function ctRefreshName(i) {
    var ct = ctState(), row = document.querySelector('#tab2-fields .frow[data-i="' + i + '"]');
    if (!row) { return; }
    var pos = foGrid(ct.boxes, foEffective());
    var p = pos[i] || { c: '?', r: '?' };
    var el = row.querySelector('.fname');
    if (el) { el.textContent = foName(ct.page, p.c, p.r, ct.fields[i] || {}); }
  }

  function ctRefreshAllNames() {
    var ct = ctState(), pos = foGrid(ct.boxes, foEffective());
    Array.prototype.forEach.call(document.querySelectorAll('#tab2-fields .frow'), function (row) {
      var i = parseInt(row.dataset.i, 10), p = pos[i] || { c: '?', r: '?' };
      var el = row.querySelector('.fname');
      if (el) { el.textContent = foName(ct.page, p.c, p.r, ct.fields[i] || {}); }
    });
  }

  function ctRender() {
    var cv = $('tab2-canvas');
    if (!cv) { return; }
    var ct = ctState(), ctx = cv.getContext('2d');
    if (!cv.width || !cv.height) { cv.width = 1000; cv.height = 1414; }
    if (ct.img) {
      ctx.drawImage(ct.img, 0, 0, cv.width, cv.height);
    } else {
      ctx.fillStyle = '#f5f5f5'; ctx.fillRect(0, 0, cv.width, cv.height);
    }
    var s = ct.scale || 1;
    ct.boxes.forEach(function (b, i) {
      var x = b.x1 * s, y = b.y1 * s, w = (b.x2 - b.x1) * s, h = (b.y2 - b.y1) * s;
      var sel = (i === ct.sel);
      ctx.lineWidth = sel ? 3 : 2;
      ctx.strokeStyle = sel ? '#d93025' : '#00b8e6';
      ctx.strokeRect(x, y, w, h);
      ctx.fillStyle = sel ? '#d93025' : '#00b8e6';
      ctx.font = 'bold 13px -apple-system, sans-serif';
      ctx.fillText(String(i + 1), x + 4, Math.max(y - 5, 13));
      if (sel) {
        ctx.fillRect(x - 4, y - 4, 8, 8); ctx.fillRect(x + w - 4, y - 4, 8, 8);
        ctx.fillRect(x - 4, y + h - 4, 8, 8); ctx.fillRect(x + w - 4, y + h - 4, 8, 8);
      }
    });
    ctUpdateCount();
    ctRenderFields();                        // 字段区与框**同序**：框一变就读数列/文件名预演全刷
  }

  // 视口坐标 ⇒ 400dpi 页坐标（CSS 缩放 × 预览缩放两级换算）
  function ctPt(ev) {
    var cv = $('tab2-canvas'), ct = ctState();
    var r = cv.getBoundingClientRect();
    var kx = cv.width / (r.width || cv.width || 1);
    var ky = cv.height / (r.height || cv.height || 1);
    var px = (ev.clientX - r.left) * kx, py = (ev.clientY - r.top) * ky;
    var s = ct.scale || 1;
    return { x: px / s, y: py / s };
  }

  function ctHit(p) {                       // 命中最小的框（叠框时点最上面那枚）
    var boxes = ctState().boxes, best = -1, bestA = Infinity;
    boxes.forEach(function (b, i) {
      if (p.x >= b.x1 && p.x <= b.x2 && p.y >= b.y1 && p.y <= b.y2) {
        var a = (b.x2 - b.x1) * (b.y2 - b.y1);
        if (a < bestA) { bestA = a; best = i; }
      }
    });
    return best;
  }

  function ctHandle(p, i) {                 // 选中框的四角手柄（9 预览像素容差）
    var b = ctState().boxes[i];
    if (!b) { return ''; }
    var tol = 9 / (ctState().scale || 1);
    var xs = [b.x1, b.x2], ys = [b.y1, b.y2];
    for (var a = 0; a < 2; a += 1) {
      for (var c = 0; c < 2; c += 1) {
        if (Math.abs(p.x - xs[a]) <= tol && Math.abs(p.y - ys[c]) <= tol) {
          return (a ? 'r' : 'l') + (c ? 'b' : 't');
        }
      }
    }
    return '';
  }

  function ctClampBox(b) {                  // 夹在页内 + 保证正序
    var size = ctState().size || [0, 0];
    var W = size[0] || 1e9, H = size[1] || 1e9;
    var x1 = Math.max(0, Math.min(b.x1, b.x2)), x2 = Math.min(W, Math.max(b.x1, b.x2));
    var y1 = Math.max(0, Math.min(b.y1, b.y2)), y2 = Math.min(H, Math.max(b.y1, b.y2));
    return { x1: x1, y1: y1, x2: x2, y2: y2 };
  }

  function ctDelete(i) {
    var ct = ctState();
    if (i < 0 || i >= ct.boxes.length) { return; }
    ct.boxes.splice(i, 1);
    if (ct.fields && i < ct.fields.length) { ct.fields.splice(i, 1); }   // 字段与框**同序删**（别错位）
    ct.sel = -1;
    ctRender();
  }

  function ctDown(ev) {
    var ct = ctState();
    if (!ct.img) { return; }
    var p = ctPt(ev), i = ctHit(p);
    if (i >= 0) {
      var h = (i === ct.sel) ? ctHandle(p, i) : '';
      var o = ct.boxes[i];
      ct.sel = i;
      ct.drag = (h ? { mode: 'resize', idx: i, corner: h, start: p, orig: { x1: o.x1, y1: o.y1, x2: o.x2, y2: o.y2 } }
        : { mode: 'move', idx: i, start: p, moved: false, orig: { x1: o.x1, y1: o.y1, x2: o.x2, y2: o.y2 } });
    } else {
      ct.sel = -1;
      ct.drag = { mode: 'new', start: p, cur: p };
    }
    ctRender();
    ev.preventDefault();
  }

  function ctMove(ev) {
    var ct = ctState(), d = ct.drag;
    if (!d) { return; }
    var p = ctPt(ev), minStep = 2 / (ct.scale || 1);
    ev.preventDefault();
    if (d.mode === 'new') {
      d.cur = p;
      ctRender();
      var a = ctClampBox({ x1: d.start.x, y1: d.start.y, x2: p.x, y2: p.y });
      var ctx = $('tab2-canvas').getContext('2d'), s = ct.scale || 1;
      ctx.setLineDash([6, 4]);
      ctx.strokeStyle = '#d93025'; ctx.lineWidth = 2;
      ctx.strokeRect(a.x1 * s, a.y1 * s, (a.x2 - a.x1) * s, (a.y2 - a.y1) * s);
      ctx.setLineDash([]);
      return;
    }
    var o = d.orig;
    if (d.mode === 'move') {
      var dx = p.x - d.start.x, dy = p.y - d.start.y;
      if (Math.abs(dx) > minStep || Math.abs(dy) > minStep) { d.moved = true; }
      ct.boxes[d.idx] = ctClampBox({ x1: o.x1 + dx, y1: o.y1 + dy, x2: o.x2 + dx, y2: o.y2 + dy });
    } else if (d.mode === 'resize') {
      var nb = { x1: o.x1, y1: o.y1, x2: o.x2, y2: o.y2 };
      if (d.corner.indexOf('l') >= 0) { nb.x1 = p.x; } else { nb.x2 = p.x; }
      if (d.corner.indexOf('t') >= 0) { nb.y1 = p.y; } else { nb.y2 = p.y; }
      ct.boxes[d.idx] = ctClampBox(nb);
    }
    ctRender();
  }

  function ctUp(ev) {
    var ct = ctState(), d = ct.drag;
    ct.drag = null;
    if (!d) { return; }
    if (d.mode === 'new') {
      var a = ctClampBox({ x1: d.start.x, y1: d.start.y, x2: d.cur.x, y2: d.cur.y });
      var minSize = 8 / (ct.scale || 1);
      if (!ev.__abort && (a.x2 - a.x1) >= minSize && (a.y2 - a.y1) >= minSize) {
        ct.boxes.push(a);
        ct.fields = ct.fields || []; ct.fields.push({});    // 新框 ⇒ 字段占位（同序）
        ct.sel = ct.boxes.length - 1;
      } else {
        ct.sel = -1;
      }
    } else if (d.mode === 'move' && !d.moved) {
      ctDelete(d.idx);                      // **单击框＝删除**（点中先变红，松开即删）
      return;
    }
    ctRender();
  }

  function ctDbl(ev) {                      // 空白处双击＝新增默认框（≈1 英寸见方，400dpi 下 400×400）
    var ct = ctState();
    if (!ct.img) { return; }
    var p = ctPt(ev);
    if (ctHit(p) >= 0) { return; }
    var b = ctClampBox({ x1: p.x - 200, y1: p.y - 200, x2: p.x + 200, y2: p.y + 200 });
    ct.boxes.push(b);
    ct.fields = ct.fields || []; ct.fields.push({});        // 新增框 ⇒ 字段占位（同序）
    ct.sel = ct.boxes.length - 1;
    ctRender();
    setMsg('tab2-ct-msg', '已新增 1 枚手绘框（拖角手柄可改大小）', 'ok');
  }

  function ctKey(ev) {
    if (!document.querySelector('.panel.active[data-panel="2_HighRes_PDF"]')) { return; }
    var tag = (document.activeElement && document.activeElement.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') { return; }
    if (ev.key === 'Delete' || ev.key === 'Backspace') {
      var ct = ctState();
      if (ct.sel >= 0 && ct.boxes.length) { ev.preventDefault(); ctDelete(ct.sel); }
    }
  }

  function ctBindCanvas() {
    var cv = $('tab2-canvas');
    if (!cv || cv.dataset.bound) { return; }
    cv.dataset.bound = '1';
    cv.addEventListener('mousedown', ctDown);
    cv.addEventListener('mousemove', ctMove);
    cv.addEventListener('mouseup', ctUp);
    cv.addEventListener('mouseleave', function () {
      if (ctState().drag) { ctUp({ __abort: true }); }
    });
    cv.addEventListener('dblclick', ctDbl);
    document.addEventListener('keydown', ctKey);
  }

  function ctLoadPreview(b64, cb) {
    var ct = ctState();
    if (!b64) { ct.img = null; cb(); return; }
    var im = new Image();
    im.onload = function () { ct.img = im; cb(); };
    im.onerror = function () { ct.img = null; cb(); };
    im.src = 'data:image/png;base64,' + b64;
  }

  function loadTab2Sources() {
    return call('tab2_list_sources').then(function (r) {
      var sel = $('tab2-ct-source'), ct = ctState();
      if (!r || !r.ok) {
        sel.innerHTML = '<option value="">（源列表读取失败）</option>';
        setMsg('tab2-ct-msg', (r && r.msg) || '源列表读取失败', 'err');
        return r;
      }
      var keep = sel.value || '';
      ct.items = r.items || [];
      ct.srcDir = r.dir || '';
      sel.innerHTML = '';
      if (!ct.items.length) {
        sel.innerHTML = '<option value="">（2_HighRes_PDF 下暂无 PDF —— 先在 tab1「⚡ 一键高清化」）</option>';
      }
      ct.items.forEach(function (it) {
        var o = document.createElement('option');
        o.value = it.path || it.name;
        o.textContent = it.name + '  →  ' + it.dir_key +
          (it.pages ? '（' + it.pages + ' 页）' : '') + ' · ' + it.size_mb + ' MB';
        sel.appendChild(o);
      });
      if (keep) {
        var hit = ct.items.some(function (it) { return (it.path || it.name) === keep; });
        if (hit) { sel.value = keep; }
      }
      ctOnSourceChange(!!keep);
      return r;
    }).catch(function () { return null; });
  }

  function ctOnSourceChange(silent) {
    var ct = ctState(), it = ctItem();
    // 同一份 PDF 的「静默刷新」（切页签回来 / 点「🔄 刷新」）⇒ **保留**已调好的框，别把人工微调清掉
    if (silent && it && ct.pdf === (it.path || it.name) && ct.boxes.length && ct.img) {
      ct.pages = it.pages || ct.pages;
      ct.dirKey = it.dir_key || ct.dirKey;
      $('tab2-ct-srcinfo').textContent = it.name + ' · ' + it.size_mb + ' MB · 目录键 ' + it.dir_key +
        '（' + it.dir_key_source + '）· ' + (it.pages ? it.pages + ' 页' : '页数未知');
      ctUpdatePageInfo();
      ctRender();
      return;
    }
    ct.boxes = []; ct.sel = -1; ct.img = null; ct.size = [0, 0]; ct.scale = 1;
    ct.fields = []; ct.orderResolved = ''; ct.orderSource = '';
    if (!it) {
      ct.pdf = ''; ct.pages = null;
      $('tab2-ct-srcinfo').textContent = '（无可选源：先在 tab1 一键高清化，再回本页「🔄 重列」）';
      ctUpdatePageInfo();
      ctRender();
      return;
    }
    ct.pdf = it.path || it.name;
    ct.pages = it.pages || null;
    ct.dirKey = it.dir_key || '';
    $('tab2-ct-srcinfo').textContent = it.name + ' · ' + it.size_mb + ' MB · 目录键 ' + it.dir_key +
      '（' + it.dir_key_source + '）· ' + (it.pages ? it.pages + ' 页' : '页数未知') +
      ' · 改于 ' + (it.mtime || '—');
    $('tab2-crop-dir').textContent = '目录键：' + (it.dir_key || '—') +
      '（' + (it.dir_key_source || '?') + '）⇒ 3_Cropped_Tiff/' + (it.dir_key || '') + '/';
    if (!silent) { ct.page = 1; $('tab2-ct-page').value = '1'; }
    $('tab2-canvas-hint').hidden = false;      // 新源／新页：先提示「自动检测」
    ctUpdatePageInfo();
    ctRender();
  }

  function ctGoPage(delta) {
    var ct = ctState(), p = (ct.page || 1) + delta;
    if (p < 1) { p = 1; }
    if (ct.pages && p > ct.pages) { p = ct.pages; }
    ct.page = p;
    $('tab2-ct-page').value = String(p);
    ct.boxes = []; ct.sel = -1; ct.img = null;
    ct.fields = []; ct.orderResolved = ''; ct.orderSource = '';   // 换页 ⇒ 上一页字段作废
    ctUpdatePageInfo();
    ctRender();
    ctDetect();                            // 翻页即重检（少一次点击；检测 ≈0.2–0.5 s）
  }

  function ctClear() {
    var ct = ctState();
    ct.boxes = []; ct.sel = -1;
    ct.fields = []; ct.orderResolved = ''; ct.orderSource = '';   // 字段/阅读顺序一并清（不留上一页读数）
    ctRender();
    setMsg('tab2-ct-msg', '已清空本页框（底图保留；「全部重检」可拿回自动框）', '');
  }

  // 后端 seal（`tab2_extract` 的一枚）⇒ 字段行对象；**顺序＝boxes 顺序**（后端按 seals 同序给 boxes）
  function ctFieldOf(s) {
    s = s || {};
    return {
      inscription: s.inscription || '', status: s.status || '', code: s.code || '',
      inscription_score: (s.inscription_score === undefined ? null : s.inscription_score),
      inscription_verified: !!s.inscription_verified,
      status_score: s.status_score, code_score: s.code_score,
      needs_review: !!s.needs_review, read_order: s.read_order || null
    };
  }

  // 送后端的阅读顺序：下拉显式值 > 后端推断值（本页已检出的 `orderResolved`）> `auto`（后端取本书元数据）
  function ctOrderForDetect() {
    var v = $('tab2-read-order') ? $('tab2-read-order').value : 'auto';
    return (v && v !== 'auto') ? (foNormalize(v) || 'auto') : 'auto';
  }
  // 送后端的阅读顺序：**只有用户显式选择时才传具体值**；停在 `auto` ⇒ 一律传 `'auto'`
  // （让后端自己推断，返回 `order_source='code-sequence'` / `book-meta` / `fallback`）。
  // ⚠ 不要把 `ct.orderResolved`（上一轮 tab2_extract 的推断值）当显式值回传 —— 那会被后端
  //   记成 `manual`，把「机器推的」冒充成「人选的」。
  function ctOrderForCrop() {
    var v = $('tab2-read-order') ? $('tab2-read-order').value : 'auto';
    return (v && v !== 'auto') ? (foNormalize(v) || 'auto') : 'auto';
  }

  function ctDetect() {
    var ct = ctState(), it = ctItem();
    if (!it) {
      setMsg('tab2-ct-msg', '请先选一份高清 PDF（2_HighRes_PDF 下无 PDF 时先在 tab1 一键高清化）', 'err');
      return;
    }
    var page = parseInt($('tab2-ct-page').value || '1', 10);
    if (!(page >= 1)) { setMsg('tab2-ct-msg', '页号从 1 开始（1-based）', 'err'); return; }
    ct.page = page;
    ctUpdatePageInfo();
    var btn = $('btn-tab2-detect');
    btn.disabled = true;
    setMsg('tab2-ct-msg', '检测中…（400dpi 渲页 + 红印检测 + 三字段提取，约 0.5–2 s）');
    // ★ 走 `tab2_extract`（不是 tab2_detect）：同一次渲页顺带把释文/状态/编号与阅读顺序一起拿回来
    call('tab2_extract', { pdf: ct.pdf, page: page, dpi: 400, reading_order: ctOrderForDetect() })
      .then(function (r) {
        btn.disabled = false;
        if (!r || !r.ok) {
          setMsg('tab2-ct-msg', '❌ ' + ((r && r.msg) || '检测失败'), 'err');
          return;
        }
        ct.size = r.size || [0, 0];
        ct.scale = r.preview_scale || 1;
        ct.boxesDpi = r.boxes_dpi || 400;
        ct.boxes = (r.boxes || []).map(function (b) {
          return { x1: b.x1, y1: b.y1, x2: b.x2, y2: b.y2 };   // 只留几何（序号由本页重排）
        });
        var seals = r.seals || [];
        ct.fields = (seals.length === ct.boxes.length)
          ? seals.map(ctFieldOf)                               // 同长度 ⇒ 逐枚对齐
          : ct.boxes.map(function () { return {}; });          // 长度不符（旧后端）⇒ 空字段占位
        ct.orderResolved = r.reading_order || '';
        ct.orderSource = r.order_source || '';
        var bm = r.book_meta || {};
        ct.bookDynasty = bm.dynasty || '';
        ct.bookAuthor = bm.author || '';
        ct.bookOrder = bm.reading_order || 'auto';
        ctMetaSrc(r);
        ct.sel = -1;
        if (r.preview_size && r.preview_size[0]) {
          var cv = $('tab2-canvas');
          cv.width = Math.round(r.preview_size[0]);
          cv.height = Math.round(r.preview_size[1]);
        }
        ctLoadPreview(r.preview_png_b64, function () {
          ctRender();
          $('tab2-canvas-hint').hidden = !!ct.img;
        });
        var rev = ct.fields.filter(function (f) { return f && f.needs_review; }).length;
        setMsg('tab2-ct-msg', '检测到 ' + ct.boxes.length + ' 枚 · 字段 ' + ct.fields.length +
          ' 组（阅读顺序 ' + (ct.orderResolved || '—') + ' / ' + (ct.orderSource || '—') +
          (rev ? ' · ⚠ 待人工确认 ' + rev : '') + '）· ' +
          (r.elapsed_s === undefined ? '?' : r.elapsed_s) + ' s · 页 ' + ct.size[0] + '×' + ct.size[1],
          ct.boxes.length ? 'ok' : 'err');
      }).catch(function () { btn.disabled = false; });
  }

  function ctCrop() {
    var ct = ctState(), it = ctItem();
    if (!it) { setMsg('tab2-ct-msg', '请先选一份高清 PDF', 'err'); return; }
    var boxes = ct.boxes.map(function (b) {
      return { x1: Math.round(b.x1), y1: Math.round(b.y1), x2: Math.round(b.x2), y2: Math.round(b.y2) };
    });
    if (!boxes.length) { setMsg('tab2-ct-msg', '没有可裁的框（先「🔍 自动检测」或空白处双击新增）', 'err'); return; }
    // 字段与框**同序**整页提交；阅读顺序＝字段区预演用的那一个（否则文件名与预演不一致）
    var fields = ct.boxes.map(function (b, i) { return ct.fields[i] || {}; });
    var order = ctOrderForCrop();
    var btn = $('btn-tab2-crop');
    btn.disabled = true;
    setMsg('tab2-crop-msg', '裁切中…（1200dpi 渲页，单页约 6 s）');
    call('tab2_crop', { pdf: ct.pdf, page: ct.page, boxes: boxes, dpi: 1200,
                        reading_order: order, fields: fields }).then(function (r) {
      if (!r || !r.ok) {
        btn.disabled = false;
        setMsg('tab2-crop-msg', '❌ ' + ((r && r.msg) || '裁切失败'), 'err');
        return;
      }
      ctRenderOutputs(r);
      btn.disabled = false;
    }).catch(function () { btn.disabled = false; });
  }

  // 朝代/作者**取自哪一级键**（exact/stripped-suffix/dir-key/stem-prefix/none）——一眼看出为何是 NA
  function ctMetaSrc(r) {
    var el = $('tab2-meta-src');
    if (!el) { return; }
    var src = (r && r.meta_source) || (r && r.book_meta && r.book_meta.meta_source) || 'none';
    var key = (r && r.meta_key) || (r && r.book_meta && r.book_meta.meta_key) || '';
    el.textContent = '朝代/作者来源：' + src + (key ? '（books 键 ' + key + '）' : '') +
      (src === 'none' ? ' —— 侧车无本书元数据 ⇒ 文件名写 NA' : '');
  }

  function ctRenderOutputs(r) {
    ctMetaSrc(r);
    var box = $('tab2-crop-out');
    box.innerHTML = '';
    var outs = r.outputs || [];
    outs.forEach(function (o) {
      var row = document.createElement('div');
      row.className = 'file';
      var sz = Array.isArray(o.size) ? (o.size[0] + '×' + o.size[1]) : (o.size || '—');
      var kb = Math.max(1, Math.round((o.bytes || 0) / 1024));
      row.innerHTML = '<span>' + esc(o.name) + '</span><span class="muted">' + esc(sz) +
        ' · ' + kb + ' KB</span>';
      box.appendChild(row);
    });
    if (!outs.length) { box.innerHTML = '<div class="muted">（无产物）</div>'; }
    var skipped = Array.isArray(r.skipped) ? r.skipped.length : (r.skipped || 0);
    $('tab2-crop-dir').textContent = '目录键：' + (r.dir_key || '—') + '（' + (r.dir_key_source || '?') +
      '）⇒ 3_Cropped_Tiff/' + (r.dir_key || '') + '/';
    var fc = (r.fields_count === undefined ? 0 : r.fields_count);
    setMsg('tab2-crop-msg', '✅ ' + outs.length + ' 件落到 3_Cropped_Tiff/' + (r.dir_key || '') + '/ · ' +
      (r.elapsed_s === undefined ? '?' : r.elapsed_s) + ' s' +
      (skipped ? ' · 跳过 ' + skipped : '') +
      (fc ? ' · 字段 ' + fc + ' 组 → ' + (r.fields_sidecar || '_fields.json') : ' · 未写字段 sidecar') +
      ' · 顺序 ' + (r.reading_order || '—') + '/' + (r.order_source || '—'), 'ok');
    toast('已裁切 ' + outs.length + ' 件');
  }

  function ctBind() {
    ctBindCanvas();
    $('btn-tab2-detect').addEventListener('click', ctDetect);
    $('btn-tab2-redetect').addEventListener('click', ctDetect);
    $('btn-tab2-clear').addEventListener('click', ctClear);
    $('btn-tab2-crop').addEventListener('click', ctCrop);
    $('btn-tab2-ct-reload').addEventListener('click', loadTab2Sources);
    $('btn-tab2-ct-prev').addEventListener('click', function () { ctGoPage(-1); });
    $('btn-tab2-ct-next').addEventListener('click', function () { ctGoPage(1); });
    $('tab2-ct-source').addEventListener('change', function () { ctOnSourceChange(false); });
    // 阅读顺序：改了就重算 C/R ⇒ 读数列 + 文件名预演全刷（框不动、不重检）
    var ro = $('tab2-read-order');
    if (ro) {
      ro.addEventListener('change', function () { ctRenderFields(); });
    }
    // 字段编辑（事件委托）：input 改字段值 ⇒ 只刷本行文件名预演/分数；人工改过释文 ⇒ 撤掉 ⚠ 待确认
    var fbox = $('tab2-fields');
    if (fbox) {
      fbox.addEventListener('input', function (ev) {
        var el = ev.target, ct = ctState();
        if (!el || !el.classList || !el.classList.contains('fin')) { return; }
        var row = el.parentNode;
        while (row && !(row.classList && row.classList.contains('frow'))) { row = row.parentNode; }
        if (!row || row.dataset.i === undefined) { return; }
        var i = parseInt(row.dataset.i, 10);
        if (!(i >= 0) || i >= ct.boxes.length) { return; }
        var f = ct.fields[i] || (ct.fields[i] = {});
        f[el.dataset.k] = el.value;
        if (el.dataset.k === 'inscription') {
          f.needs_review = false; f.inscription_verified = true;
          row.classList.remove('rev');
        }
        var sc = row.querySelector('.fscore');
        if (sc) { sc.textContent = foScore(f); }
        ctRefreshName(i);
      });
    }
    $('tab2-ct-page').addEventListener('change', function () {
      var ct = ctState();
      var p = parseInt($('tab2-ct-page').value || '1', 10);
      if (!(p >= 1)) { p = 1; }
      if (ct.pages && p > ct.pages) { p = ct.pages; }
      ct.page = p;
      $('tab2-ct-page').value = String(p);
      ct.boxes = []; ct.sel = -1; ct.img = null;
      ct.fields = []; ct.orderResolved = ''; ct.orderSource = '';
      ctUpdatePageInfo(); ctRender();
    });
  }

  // ── tab3：3_Cropped_Tiff —— 缩略图网格（四档视图/分页/键盘导航）+ 选件解析 + 重命名 ──
  // 口径来源：旧版 `local-dist/src/webui.py` L528–881（view_cfg：large 5×20 / medium 10×50 /
  // small 20×100 / list 1×30；`-Z 150` 缩略图、`-Z 400` 大图、P/C/R 前缀 + 三字段新名预览）。
  function t3cfg() {
    var all = ST.tab3.cfg || {
      large: { cols: 5, per_page: 20 }, medium: { cols: 10, per_page: 50 },
      small: { cols: 20, per_page: 100 }, list: { cols: 1, per_page: 30 }
    };
    return all[ST.tab3.view] || all.medium;
  }

  function loadTab3(subdir) {
    setMsg('tab3-msg', '加载中…');
    call('tab3_list', { subdir: subdir || ST.tab3.curSubdir || '' }).then(function (r) {
      if (!r || !r.ok) { setMsg('tab3-msg', (r && r.msg) || '加载失败', 'err'); return; }
      ST.tab3.subdirs = r.subdirs || [];
      ST.tab3.files = r.files || [];
      ST.tab3.curSubdir = r.current || '';
      ST.tab3.cfg = r.view_cfg || ST.tab3.cfg;
      ST.tab3.limits = r.limits || ST.tab3.limits || { shiwen_max: 10, author_max: 4 };
      ST.tab3.isAdmin = !!r.is_admin;
      // OCR 能力闸：阶段 1 打包件不含 rapidocr ⇒ **打开就置灰**，不让用户点了才炸
      ST.tab3.ocrAvailable = (r.ocr_available !== false);
      ST.tab3.ocrNote = r.ocr_note || '本版本未内置 OCR 引擎';
      var ocrBtn = $('btn-tab3-ocr');
      if (ocrBtn) {
        ocrBtn.disabled = !ST.tab3.ocrAvailable;
        ocrBtn.title = ST.tab3.ocrAvailable
          ? '对当前选中的裁切件跑本地通用 OCR（只填释文框，不改文件）'
          : ST.tab3.ocrNote;
      }
      var autoBox = $('tab3-corr-auto');
      if (autoBox) { autoBox.disabled = !ST.tab3.ocrAvailable; }
      setMsg('tab3-ocr-msg', ST.tab3.ocrAvailable ? '' : ST.tab3.ocrNote,
        ST.tab3.ocrAvailable ? '' : 'err');
      ST.tab3.view = ST.tab3.view || r.view_default || 'medium';
      ST.tab3.page = 0;
      $('tab3-template').textContent = r.template || '—';
      $('btn-tab3-test').disabled = !ST.tab3.isAdmin;
      $('btn-tab3-test').title = ST.tab3.isAdmin ? '' : '仅管理员可生成测试 TIFF';
      $('tab3-shiwen-label').textContent = '印面释文（最多 ' + ST.tab3.limits.shiwen_max + ' 个汉字）';
      $('tab3-author-label').textContent = '作者（最多 ' + ST.tab3.limits.author_max + ' 个汉字）';
      var gone = ST.tab3.selected &&
        !ST.tab3.files.some(function (f) { return f.name === ST.tab3.selected; });
      if (gone) { ST.tab3.selected = ''; ST.tab3.previewStat = null; }
      renderSubdirTabs();
      renderGrid();
      if (ST.tab3.selected) { selectFile(ST.tab3.selected, true); }
      else if (gone) { $('tab3-noselect').hidden = false; $('tab3-edit').hidden = true; }
      setMsg('tab3-msg', '共 ' + ST.tab3.files.length + ' 个 tiff（子目录：' + (ST.tab3.curSubdir || '—') + '）', 'ok');
      renderLog();
    });
  }

  function renderSubdirTabs() {
    var box = $('tab3-subdirs');
    box.innerHTML = '';
    if (!ST.tab3.subdirs.length) {
      box.innerHTML = '<span class="muted">（3_Cropped_Tiff 下无子目录）</span>';
      return;
    }
    ST.tab3.subdirs.forEach(function (d) {
      var b = document.createElement('button');
      b.textContent = '📁 ' + d;
      b.title = d;
      b.classList.toggle('active', d === ST.tab3.curSubdir);
      b.disabled = (d === ST.tab3.curSubdir);
      b.addEventListener('click', function () { ST.tab3.selected = ''; loadTab3(d); });
      box.appendChild(b);
    });
  }

  function setView(v) {
    if (!v) { return; }
    ST.tab3.view = v; ST.tab3.page = 0;
    renderGrid();
  }

  function renderGrid() {
    var cfg = t3cfg();
    var grid = $('tab3-grid');
    grid.dataset.view = ST.tab3.view;
    Array.prototype.forEach.call(document.querySelectorAll('#tab3-views .view-btn'), function (b) {
      b.classList.toggle('active', b.dataset.view === ST.tab3.view);
      b.disabled = (b.dataset.view === ST.tab3.view);
    });
    var per = cfg.per_page || 50, total = ST.tab3.files.length;
    var pages = Math.max(1, Math.ceil(total / per));
    if (ST.tab3.page > pages - 1) { ST.tab3.page = pages - 1; }
    if (ST.tab3.page < 0) { ST.tab3.page = 0; }
    var pageFiles = ST.tab3.files.slice(ST.tab3.page * per, ST.tab3.page * per + per);
    ST.tab3.pageNames = pageFiles.map(function (f) { return f.name; });
    ST.tab3.els = {};
    grid.innerHTML = '';
    if (!total) { grid.innerHTML = '<div class="muted">（该子目录下没有 tiff 文件）</div>'; }
    pageFiles.forEach(function (f) {
      var d = document.createElement('div');
      d.className = 'thumb-item' + (f.name === ST.tab3.selected ? ' selected' : '');
      d.dataset.name = f.name;
      d.title = f.name + (f.standard ? '' : '（命名不合模板）');
      var box = document.createElement('div');
      box.className = 'thumb-box';
      var ph = document.createElement('span');
      ph.className = 'ph'; ph.textContent = '⏳';
      box.appendChild(ph);
      var nm = document.createElement('div');
      nm.className = 'name' + (f.standard ? '' : ' bad');
      nm.textContent = f.name.length > 22 ? f.name.slice(0, 22) + '…' : f.name;
      d.appendChild(box); d.appendChild(nm);
      d.addEventListener('click', function () { selectFile(f.name); });
      grid.appendChild(d);
      ST.tab3.els[f.name] = d;
    });
    $('tab3-pageinfo').textContent = '共 ' + total + ' 个文件 · 第 ' + (ST.tab3.page + 1) + '/' + pages +
      ' 页 · 视图 ' + ST.tab3.view + '（' + cfg.cols + '×' + per + '）· ↑↓←→ 切换选中';
    $('tab3-pageno').textContent = (ST.tab3.page + 1) + ' / ' + pages;
    $('btn-tab3-prev').disabled = (ST.tab3.page === 0);
    $('btn-tab3-next').disabled = (ST.tab3.page >= pages - 1);
    loadThumbs();
  }

  function loadThumbs() {
    var names = ST.tab3.pageNames || [];
    if (!names.length || !ST.tab3.curSubdir) { return; }
    var size = (ST.tab3.view === 'large') ? 150 : 96;
    call('tab3_thumbs', { subdir: ST.tab3.curSubdir, names: names, size: size }).then(function (r) {
      if (!r || !r.ok) { setMsg('tab3-msg', (r && r.msg) || '缩略图加载失败', 'err'); return; }
      var got = 0;
      names.forEach(function (n) {
        var item = ST.tab3.els[n];
        if (!item) { return; }
        var uri = (r.thumbs || {})[n];
        var box = item.querySelector('.thumb-box');
        if (!uri) { box.innerHTML = '<span class="ph">🗎</span>'; return; }
        var img = document.createElement('img');
        img.alt = n; img.src = uri;
        box.innerHTML = ''; box.appendChild(img);
        got += 1;
      });
      ST.tab3.thumbStat = { asked: names.length, got: got,
        failed: Object.keys(r.failed || {}).length, engine: r.engines || {}, size: r.size };
      if (got < names.length) {
        setMsg('tab3-msg', '缩略图：' + got + '/' + names.length + ' 出图（失败：' +
          JSON.stringify(r.failed || {}) + '）', 'err');
      }
    });
  }

  function selectFile(name, silent) {
    var f = null;
    ST.tab3.files.forEach(function (x) { if (x.name === name) { f = x; } });
    if (!f) { setMsg('tab3-msg', '文件不在当前列表：' + name, 'err'); return; }
    ST.tab3.selected = name;
    ST.tab3.versions += 1;
    var ver = ST.tab3.versions;
    Array.prototype.forEach.call(document.querySelectorAll('#tab3-grid .thumb-item'), function (el) {
      el.classList.toggle('selected', el.dataset.name === name);
    });
    var el = ST.tab3.els[name];
    if (el && el.scrollIntoView) { try { el.scrollIntoView({ block: 'nearest' }); } catch (e) { } }
    $('tab3-noselect').hidden = true;
    $('tab3-edit').hidden = false;
    $('tab3-current').textContent = '当前文件：' + name + '（' + f.size_mb + ' MB · ' + f.mtime + '）';
    if (!silent) { setMsg('tab3-rename-msg', ''); }   // 改完名后的自动刷新（silent）**不清**结果提示
    ocrResetPanel();                                  // 换件 ⇒ 上一件的 OCR/纠错读数不再成立
    var pv = $('tab3-preview');
    pv.removeAttribute('src');
    call('tab3_preview', { subdir: ST.tab3.curSubdir, name: name }).then(function (r) {
      if (ver !== ST.tab3.versions) { return; }
      if (r && r.ok) {
        pv.src = r.data_uri;
        ST.tab3.previewStat = { ok: true, size: r.size, bytes: r.bytes, engine: r.engine };
      } else {
        ST.tab3.previewStat = { ok: false, msg: (r && r.msg) || '预览失败' };
      }
    });
    call('tab3_parse', { subdir: ST.tab3.curSubdir, name: name }).then(function (r) {
      if (ver !== ST.tab3.versions || !r || !r.ok) { return; }
      var fl = r.fields || {};
      $('tab3-shiwen').value = fl.shiwen || '';
      $('tab3-dynasty').value = fl.dynasty || '';
      $('tab3-author').value = fl.author || '';
      setMsg('tab3-parsed', r.standard
        ? ('已自动解析：第 ' + r.page + ' 页 · 第 ' + r.col + ' 列 · 第 ' + r.row + ' 行（前缀 ' + r.prefix + '）')
        : (r.note || '文件名非标准模板，请手动填写'), r.standard ? 'ok' : 'err');
      doCheck();
    });
    if (!silent) { $('tab3-msg').textContent = '已选中：' + name; }
  }

  var t3Timer = null;
  function checkFields() {                    // 输入即校验（120 ms 去抖，避免桥被打爆）
    if (t3Timer) { clearTimeout(t3Timer); }
    t3Timer = setTimeout(doCheck, 120);
  }

  function doCheck() {
    var name = ST.tab3.selected;
    if (!name) { return; }
    call('tab3_check', {
      subdir: ST.tab3.curSubdir, name: name,
      shiwen: $('tab3-shiwen').value, dynasty: $('tab3-dynasty').value,
      author: $('tab3-author').value
    }).then(function (r) {
      if (!r || !r.ok) {
        $('tab3-newname').textContent = '—';
        $('btn-tab3-rename').disabled = true;
        setMsg('tab3-valid', (r && r.msg) || '校验失败', 'err');
        return;
      }
      var lim = r.limits || ST.tab3.limits || { shiwen_max: 10, author_max: 4 };
      $('tab3-counts').textContent = '释文 ' + r.counts.shiwen + '/' + lim.shiwen_max +
        '　作者 ' + r.counts.author + '/' + lim.author_max;
      $('tab3-newname').textContent = r.new_name || '—';
      $('btn-tab3-rename').disabled = !r.can_rename;
      setMsg('tab3-valid', r.can_rename ? '' : r.reason, r.can_rename ? 'ok' : 'err');
      ST.tab3.lastCheck = r;
    });
  }

  function doRenameTab3() {
    var name = ST.tab3.selected;
    if (!name) { setMsg('tab3-rename-msg', '请先选择文件', 'err'); return; }
    $('btn-tab3-rename').disabled = true;
    setMsg('tab3-rename-msg', '正在重命名…');
    call('tab3_rename', {
      subdir: ST.tab3.curSubdir, name: name,
      shiwen: $('tab3-shiwen').value, dynasty: $('tab3-dynasty').value,
      author: $('tab3-author').value
    }).then(function (r) {
      if (r && r.ok) {
        ST.tab3.selected = r.new_name;                 // 刷新后仍指向改名后的文件
        setMsg('tab3-rename-msg', (r.msg || '') + '　[cloud_log=' + r.cloud_log +
          ' / cloud_lock=' + r.cloud_lock + '：外部同步未接入]', 'ok');
        toast('已重命名：' + r.new_name);
        loadTab3(ST.tab3.curSubdir);                   // 刷新列表 + 选中 + 本地记录
      } else {
        setMsg('tab3-rename-msg', (r && r.msg) || '重命名失败', 'err');
        doCheck();
      }
    });
  }

  // ── OCR 试试看 ＋ 纠错建议（**只读辅助**：只改释文输入框，绝不改文件/不改名）──
  //   诚实口径：**印面篆书通用 OCR 不可靠**（248 枚均分 0.2428、非空 60.1%）⇒ 结果面板
  //   必带提示；提示文本以后端 `r.hint` 为单一真源，下面只是「后端没给」时的兜底。
  var OCR_HINT_FALLBACK = '印面篆书通用 OCR 不可靠，仅供参考（请逐字人工核对）';

  function corrHide() {
    var box = $('tab3-corr');
    ST.tab3.corrHits = [];
    if (!box) { return; }
    box.hidden = true;
    var list = $('tab3-corr-list');
    if (list) { list.innerHTML = ''; }
  }

  function ocrResetPanel() {                      // 换件 / 重新识别前清场（不留上一件的读数）
    corrHide();
    ST.tab3.ocrRaw = '';
    var out = $('tab3-ocr-out');
    if (out) { out.hidden = true; }
    var raw = $('tab3-ocr-raw');
    if (raw) { raw.innerHTML = ''; }
    var hint = $('tab3-ocr-hint');
    if (hint) { hint.textContent = ''; }
    setMsg('tab3-ocr-msg', '');
    if (ST.tab3.ocrAvailable === false) {          // 缺引擎的提示要常驻（换件也别被清掉）
      setMsg('tab3-ocr-msg', ST.tab3.ocrNote || '本版本未内置 OCR 引擎', 'err');
    }
  }

  function renderOcrResult(r) {
    var out = $('tab3-ocr-out'), box = $('tab3-ocr-raw');
    $('tab3-ocr-hint').textContent = r.hint || OCR_HINT_FALLBACK;
    box.innerHTML = '';
    var texts = r.texts || [], scores = r.scores || [];
    if (!texts.length) {
      var d0 = document.createElement('div');
      d0.className = 'seg muted';
      d0.textContent = r.note || '未识别到文字';
      box.appendChild(d0);
    }
    texts.forEach(function (t, i) {
      var d = document.createElement('span'); d.className = 'seg';
      var s = document.createElement('span'); s.textContent = t;
      var v = scores[i];
      var sc = document.createElement('span');
      sc.className = 'sc' + (typeof v === 'number' && v < 0.6 ? ' low' : '');   // <0.6 标红：低分优先人看
      sc.textContent = '分数 ' + (typeof v === 'number' ? v.toFixed(4) : '—');
      d.appendChild(s); d.appendChild(sc); box.appendChild(d);
    });
    var eng = document.createElement('div');
    eng.className = 'eng';
    eng.textContent = (r.engine || '') + ' · ' + (r.elapsed_s === undefined ? '—' : r.elapsed_s + ' s') +
      ' · 均分 ' + (r.mean_score === undefined ? '—' : r.mean_score);
    box.appendChild(eng);
    out.hidden = false;
  }

  function renderCorrections(c) {
    var hits = (c && c.hits) || [], list = $('tab3-corr-list');
    list.innerHTML = '';
    ST.tab3.corrHits = [];
    if (!hits.length) { corrHide(); return; }     // 无命中 ⇒ **静默**（不显示空面板）
    var m = (c && c.map) || {};
    $('tab3-corr-head').textContent = '纠错建议 ' + hits.length + ' 条（字表 ' +
      (m.n_verified === undefined ? '?' : m.n_verified) + '/' +
      (m.n_entries === undefined ? '?' : m.n_entries) + ' 已核定 · 仅改输入框，不改文件）';
    hits.forEach(function (h) {
      var d = document.createElement('div'); d.className = 'corr-item';
      var f = document.createElement('span'); f.className = 'from'; f.textContent = h.from;
      var t = document.createElement('span'); t.className = 'to'; t.textContent = h.to;
      var meta = document.createElement('span'); meta.className = 'meta';
      meta.textContent = '第 ' + ((h.pos === undefined ? -1 : h.pos) + 1) + ' 字 · ' +
        (h.source || '出处未标') + ' · 置信 ' + (h.confidence === undefined ? '—' : h.confidence) +
        (h.verified ? ' · 已核定' : ' · 未核定');
      d.appendChild(f); d.appendChild(document.createTextNode(' → '));
      d.appendChild(t); d.appendChild(meta);
      list.appendChild(d);
      ST.tab3.corrHits.push(h);
    });
    $('btn-tab3-corr-apply').disabled = false;
    $('tab3-corr').hidden = false;
  }

  function applyAllCorrections() {
    var hits = ST.tab3.corrHits || [];
    if (!hits.length) { return; }
    var el = $('tab3-shiwen');
    var chars = String(el.value || '').split('');
    var n = 0;
    // 仅在「该位置仍是原字」时才替换 ⇒ 用户已手改过的字不被悄悄覆盖
    hits.forEach(function (h) {
      if (typeof h.pos === 'number' && h.pos >= 0 && chars[h.pos] === h.from) {
        chars[h.pos] = h.to; n += 1;
      }
    });
    el.value = chars.join('');
    el.dispatchEvent(new Event('input', { bubbles: true }));   // 触发计数 / 新名预览 / 按钮门禁
    setMsg('tab3-ocr-msg', '已应用 ' + n + '/' + hits.length + ' 条到释文框（未改文件）',
      n ? 'ok' : 'err');
    corrHide();
  }

  function doOcr() {
    var name = ST.tab3.selected;
    if (ST.tab3.ocrAvailable === false) {          // 能力闸：本版不含引擎 ⇒ 只给可读提示，不打桥
      setMsg('tab3-ocr-msg', ST.tab3.ocrNote || '本版本未内置 OCR 引擎', 'err');
      return;
    }
    if (!name) { setMsg('tab3-ocr-msg', '请先选择文件', 'err'); return; }
    var btn = $('btn-tab3-ocr');
    if (btn.disabled) { return; }                 // 防连点（长任务纪律：结果回来再启用）
    btn.disabled = true;
    corrHide();
    setMsg('tab3-ocr-msg', '正在识别…（本地引擎，通常 <1 s）');
    var ver = ST.tab3.versions;                   // 识别途中换了件 ⇒ 丢弃旧结果
    call('tab3_ocr', { subdir: ST.tab3.curSubdir, name: name }).then(function (r) {
      if (ver !== ST.tab3.versions) { return; }
      if (!r || !r.ok) {
        $('tab3-ocr-out').hidden = true;
        setMsg('tab3-ocr-msg', (r && r.msg) || 'OCR 失败', 'err');
        return;
      }
      renderOcrResult(r);
      var box = $('tab3-shiwen'), filled = false;
      if (!String(box.value || '').trim() && String(r.text || '').trim()) {
        box.value = r.text;                       // **仅当输入框为空**才填（不覆盖用户/文件名解析结果）
        filled = true;
        box.dispatchEvent(new Event('input', { bubbles: true }));
      }
      var srcText = String(box.value || '');
      ST.tab3.ocrRaw = srcText;
      setMsg('tab3-ocr-msg',
        (r.texts || []).length
          ? ('识别 ' + r.texts.length + ' 段 · ' + r.elapsed_s + ' s' +
             (filled ? ' · 已填入释文框' : ' · 释文框非空，未覆盖'))
          : (r.note || '未识别到文字'),
        (r.texts || []).length ? 'ok' : 'err');
      var auto = !!($('tab3-corr-auto') && $('tab3-corr-auto').checked);
      return call('tab3_correct', { text: srcText, mode: auto ? 'auto' : 'suggest' })
        .then(function (c) {
          if (ver !== ST.tab3.versions) { return; }
          if (!c || !c.ok) { corrHide(); return; }              // 纠错不可用 ⇒ 静默，不影响主流程
          if (auto && c.corrected && c.corrected !== srcText) {  // auto 只在显式勾选时改**输入框**
            box.value = c.corrected;
            box.dispatchEvent(new Event('input', { bubbles: true }));
            ST.tab3.ocrRaw = c.corrected;
            setMsg('tab3-ocr-msg', '自动应用已核定纠错 ' + ((c.stats || {}).n_applied || 0) +
              ' 处（仅改输入框）', 'ok');
          }
          renderCorrections(c);
        });
    }).catch(function () {
      $('tab3-ocr-out').hidden = true;
      setMsg('tab3-ocr-msg', '后端不可用', 'err');
    }).then(function () {
      btn.disabled = (ST.tab3.ocrAvailable === false);   // **成败都复原**（缺引擎则保持禁用）
    });
  }

  function renderLog() {
    call('tab3_log', { limit: 20 }).then(function (r) {
      var tb = $('tab3-log-body');
      tb.innerHTML = '';
      if (!r || !r.ok) { $('tab3-log-path').textContent = (r && r.msg) || '本地记录读取失败'; return; }
      var rows = (r.rows || []).slice().reverse();
      rows.forEach(function (rec) {
        var tr = document.createElement('tr');
        [rec.timestamp, rec.old_filename, rec.new_filename, rec['印面释文'], rec['朝代'],
          rec['作者'], rec.operator, rec.status].forEach(function (v) {
            var td = document.createElement('td');
            td.textContent = (v === undefined || v === null) ? '' : String(v);
            tr.appendChild(td);
          });
        tb.appendChild(tr);
      });
      if (!rows.length) { tb.innerHTML = '<tr><td colspan="8" class="muted">（本地暂无记录）</td></tr>'; }
      $('tab3-log-path').textContent = '本地记录：' + r.path + '（' + r.count +
        ' 条）·日志同步（腾讯文档）=' + r.cloud_log + ' · 云盘锁=' + r.cloud_lock;
      $('tab3-log-badge').textContent = '日志同步（腾讯文档）：' +
        (r.cloud_log === 'not_connected' ? '暂未接入' : r.cloud_log) + ' ／ 云盘锁：' +
        (r.cloud_lock === 'not_connected' ? '暂未接入' : r.cloud_lock);
    });
  }

  // 键盘导航（旧版四键均 ±1；新版按视图列数做**几何**导航：list 档列数=1 ⇒ 与旧版等价）
  function tab3Keydown(e) {
    if (!document.querySelector('.panel.active[data-panel="3_Cropped_Tiff"]')) { return; }
    var tag = (document.activeElement && document.activeElement.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') { return; }  // 输入框里不抢键
    var cfg = t3cfg();
    var n = ST.tab3.files.length;
    if (!n) { return; }
    var step;
    if (e.key === 'ArrowRight') { step = 1; }
    else if (e.key === 'ArrowLeft') { step = -1; }
    else if (e.key === 'ArrowDown') { step = (cfg.cols > 1 ? cfg.cols : 1); }
    else if (e.key === 'ArrowUp') { step = (cfg.cols > 1 ? -cfg.cols : -1); }
    else { return; }
    var idx = -1;
    ST.tab3.files.forEach(function (f, i) { if (f.name === ST.tab3.selected) { idx = i; } });
    var next = (idx < 0) ? 0 : idx + step;
    if (next < 0) { next = 0; }
    if (next > n - 1) { next = n - 1; }
    e.preventDefault();
    var wantPage = Math.floor(next / (cfg.per_page || 50));
    if (wantPage !== ST.tab3.page) { ST.tab3.page = wantPage; renderGrid(); }   // 选中项跟随翻页
    selectFile(ST.tab3.files[next].name);
  }

  function genTestTab3() {
    if (!ST.tab3.curSubdir) { setMsg('tab3-msg', '请先选择子目录', 'err'); return; }
    if (!ST.tab3.isAdmin) { setMsg('tab3-msg', '仅管理员可生成测试 TIFF', 'err'); return; }
    call('tab3_generate_test', { subdir: ST.tab3.curSubdir }).then(function (r) {
      setMsg('tab3-msg', (r && r.msg) || '', r && r.ok ? 'ok' : 'err');
      if (r && r.ok) { loadTab3(ST.tab3.curSubdir); }
    });
  }

  // ───────────── yinyuan（印源）接入：弹窗 / 连接 / 候选补全 ─────────────
  var yyTimer = null;

  // 渲染连接态：**只显示 prefix**，完整 key 永不进 DOM
  function renderYinyuan(st) {
    var connected = !!(st && st.connected);
    var pill = $('yy-pill');
    if (pill) {
      pill.hidden = !connected;
      if (connected) {
        pill.textContent = '🔗 ' + (st.prefix || 'yinyuan');
        pill.title = (st.label || '') + '（' + (st.base_url || '') + '）';
      }
    }
    var open = $('btn-yy-open');
    if (open) { open.textContent = connected ? '🔗 yinyuan 已连接' : '🔗 连接 yinyuan'; }
    $('yy-connected').hidden = !connected;
    $('yy-form').hidden = connected;
    if (!connected) { return; }
    $('yy-prefix').textContent = st.prefix || '—';
    $('yy-label').textContent = st.label || '—';
    var c = st.cache || {};
    var parts = ['dynasties', 'authors', 'inscriptions'].map(function (k) {
      var v = c[k];
      if (!v) { return k + ' 未同步'; }
      return k + ' ' + (v.count === null || v.count === undefined ? '已缓存' : v.count + ' 条');
    });
    $('yy-cache-line').textContent = '缓存（24h）：' + parts.join(' · ');
    ST.yy = { connected: true, prefix: st.prefix || '', label: st.label || '' };
  }

  function yyOpen() {
    $('yy-msg').textContent = '';
    $('yinyuan-modal').hidden = false;
    call('yinyuan_status').then(function (r) {
      if (r && r.ok) { renderYinyuan(r); } else { setMsg('yy-msg', (r && r.msg) || '取连接态失败', 'err'); }
    }).catch(function () { setMsg('yy-msg', '后端不可用', 'err'); });
  }

  function yyClose() { $('yinyuan-modal').hidden = true; }

  function yyConnect() {
    var ident = $('yy-identifier').value.trim();
    var pwd = $('yy-password').value;          // ⚠️ 口令**不 trim**（与 yinyuan B1 口径一致）
    if (!ident || !pwd) { setMsg('yy-msg', '请填写手机号/邮箱与口令', 'err'); return; }
    setMsg('yy-msg', '连接中…', '');
    $('btn-yy-connect').disabled = true;
    call('yinyuan_connect', { identifier: ident, password: pwd }).then(function (r) {
      $('btn-yy-connect').disabled = false;
      if (!r || !r.ok) { setMsg('yy-msg', (r && r.msg) || '连接失败', 'err'); return; }
      $('yy-password').value = '';
      setMsg('yy-msg', (r.msg || '已连接') + '（前缀 ' + (r.prefix || '') + '）', 'ok');
      renderYinyuan({ ok: true, connected: true, prefix: r.prefix, label: r.label, cache: {} });
      // 再取一次连接态（拿到缓存读数；后台预热可能还在跑）
      call('yinyuan_status').then(function (s) { if (s && s.ok) { renderYinyuan(s); } }).catch(function () { });
      loadTab1();                              // 值域可能已换成远端（缓存面）
      toast('yinyuan：' + (r.msg || '已连接'));
    }).catch(function () {
      $('btn-yy-connect').disabled = false;
      setMsg('yy-msg', '后端不可用', 'err');
    });
  }

  function yyDisconnect() {
    call('yinyuan_disconnect').then(function (r) {
      setMsg('yy-msg', (r && r.msg) || '已断开', r && r.ok ? 'ok' : 'err');
      call('yinyuan_status').then(function (s) { if (s && s.ok) { renderYinyuan(s); } });
      loadTab1();
    });
  }

  function yySync() {
    setMsg('yy-msg', '同步中（朝代 / 作者 / 印文）…', '');
    call('yinyuan_sync', { force: true }).then(function (r) {
      if (!r || !r.ok) { setMsg('yy-msg', '同步失败', 'err'); return; }
      setMsg('yy-msg', '已同步：作者 ' + (r.authors === undefined ? '—' : r.authors) +
        ' 条 · 印文 ' + (r.inscriptions === undefined ? '—' : r.inscriptions) + ' 条 · 朝代 ' +
        (r.dynasties || '—'), 'ok');
      call('yinyuan_status').then(function (s) { if (s && s.ok) { renderYinyuan(s); } });
      loadTab1();
    }).catch(function () { setMsg('yy-msg', '同步失败', 'err'); });
  }

  // 候选补全：tab3 的「印面释文」← /inscriptions（seal_name/transcription）
  //                      「作者」← /authors（name/art_names/courtesy_names）
  // 拿不到 / 未连接 ⇒ 静默不显示候选，输入框仍可自由手输（不阻塞重命名）
  function yySuggestBox(kind) {
    return $(kind === 'author' ? 'tab3-author-suggest' : 'tab3-shiwen-suggest');
  }

  function yySuggestFetch(kind, value) {
    var box = yySuggestBox(kind);
    if (!box) { return; }
    if (!value) { box.hidden = true; box.innerHTML = ''; return; }
    call('yinyuan_suggest', { kind: kind, query: value, limit: 8 }).then(function (r) {
      var items = (r && r.items) || [];
      box.innerHTML = '';
      if (!items.length) { box.hidden = true; return; }
      items.forEach(function (it) {
        var d = document.createElement('div');
        d.className = 'suggest-item';
        d.dataset.value = it.value;
        var s1 = document.createElement('span'); s1.textContent = it.value; d.appendChild(s1);
        var hint = it.hint || it.dynasty || '';
        if (hint) { var s2 = document.createElement('span'); s2.className = 'hint';
          s2.textContent = hint; d.appendChild(s2); }
        d.addEventListener('click', function () { yyPick(kind, it.value); });
        box.appendChild(d);
      });
      box.hidden = false;
    }).catch(function () { box.hidden = true; });
  }

  function yyPick(kind, value) {
    var input = $(kind === 'author' ? 'tab3-author' : 'tab3-shiwen');
    if (input) { input.value = value; }
    var box = yySuggestBox(kind);
    if (box) { box.hidden = true; box.innerHTML = ''; }
    doCheck();                                 // 立即走原有校验/新名预览
  }

  function bindYinyuan() {
    $('btn-yy-open').addEventListener('click', yyOpen);
    $('btn-yy-close').addEventListener('click', yyClose);
    $('btn-yy-connect').addEventListener('click', yyConnect);
    $('btn-yy-disconnect').addEventListener('click', yyDisconnect);
    $('btn-yy-sync').addEventListener('click', yySync);
    $('yy-password').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { yyConnect(); }
    });
    [['tab3-author', 'author'], ['tab3-shiwen', 'inscription']].forEach(function (pair) {
      var input = $(pair[0]);
      if (!input) { return; }
      var kind = pair[1];
      input.addEventListener('input', function () {
        var v = input.value.trim();
        if (yyTimer) { clearTimeout(yyTimer); }
        yyTimer = setTimeout(function () { yySuggestFetch(kind, v); }, 180);
      });
      input.addEventListener('blur', function () {
        setTimeout(function () { var b = yySuggestBox(kind); if (b) { b.hidden = true; } }, 180);
      });
      input.addEventListener('keydown', function (e) {
        var b = yySuggestBox(kind);
        if (!b || b.hidden) { return; }
        var first = b.querySelector('.suggest-item');
        if (e.key === 'Escape') { b.hidden = true; }
        else if (e.key === 'Enter' && first) { e.preventDefault(); yyPick(kind, first.dataset.value); }
      });
    });
  }

  // ───────────── 事件绑定 ─────────────
  function bindAll() {
    bindLogin(); bindTabs(); bindYinyuan();
    $('btn-home').addEventListener('click', browseHome);
    $('btn-up').addEventListener('click', browseUp);
    $('btn-verify').addEventListener('click', verifyDir);
    $('btn-ensure').addEventListener('click', ensureSubdirs);
    $('btn-tab1-rescan').addEventListener('click', function () { loadTab1($('tab1-force').checked); });
    $('btn-tab1-save').addEventListener('click', saveTab1);
    // tab1 · ⚡ 一键高清化（三档 dpi / 页区间 / 开始 / 取消 / 去 tab2）
    $('btn-tab1-hr-start').addEventListener('click', hrStart);
    $('btn-tab1-hr-cancel').addEventListener('click', hrCancel);
    $('btn-tab1-hr-goto2').addEventListener('click', function () { activateTab('2_HighRes_PDF'); });
    ctBind();                               // tab2 切图台（画布 / 检测 / 裁切 / 选页）
    $('btn-tab2-refresh').addEventListener('click', loadTab2);
    $('btn-tab2-generate').addEventListener('click', generateTab2);
    $('btn-tab2-cancel').addEventListener('click', cancelTab2);
    $('btn-tab2-open').addEventListener('click', openInFinder);
    $('btn-tab3-refresh').addEventListener('click', function () { loadTab3(ST.tab3.curSubdir); });
    $('btn-tab3-test').addEventListener('click', genTestTab3);
    // tab3：视图四档 / 分页 / 三输入框即时校验 / 执行重命名 / 本地记录
    Array.prototype.forEach.call(document.querySelectorAll('#tab3-views .view-btn'), function (b) {
      b.addEventListener('click', function () { setView(b.dataset.view); });
    });
    $('btn-tab3-prev').addEventListener('click', function () {
      if (ST.tab3.page > 0) { ST.tab3.page -= 1; renderGrid(); }
    });
    $('btn-tab3-next').addEventListener('click', function () { ST.tab3.page += 1; renderGrid(); });
    ['tab3-shiwen', 'tab3-dynasty', 'tab3-author'].forEach(function (id) {
      $(id).addEventListener('input', checkFields);
    });
    $('btn-tab3-rename').addEventListener('click', doRenameTab3);
    // OCR 试试看 ＋「全部应用」纠错建议（只改输入框，不改文件）
    $('btn-tab3-ocr').addEventListener('click', doOcr);
    $('btn-tab3-corr-apply').addEventListener('click', applyAllCorrections);
    document.addEventListener('keydown', tab3Keydown);
    Array.prototype.forEach.call(document.querySelectorAll('[data-action="logout"]'), function (b) {
      b.addEventListener('click', function () {
        call('logout').then(function () { ST.user = null; ST.root = ''; show('view-login'); });
      });
    });
    Array.prototype.forEach.call(document.querySelectorAll('[data-action="change-dir"]'), function (b) {
      b.addEventListener('click', changeDir);
    });
  }

  function boot() {
    bindAll();
    setModeLabel(hasBridge());
    var t = 0;
    var iv = setInterval(function () {           // 等桥就绪后再问会话
      t += 1;
      if (!hasBridge()) { if (t > 40) { clearInterval(iv); setModeLabel(false); } return; }
      clearInterval(iv); setModeLabel(true);
      call('session_state').then(function (r) {
        if (r && r.logged_in) {
          ST.user = { username: r.username, is_admin: r.is_admin, feicui_root: r.feicui_root };
          if (r.feicui_root) { ST.root = r.feicui_root; show('view-main'); enterMain(); }
          else { show('view-dir'); browseHome(); }
        } else { show('view-login'); }
      });
    }, 250);
  }

  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', boot); }
  else { boot(); }
})();
