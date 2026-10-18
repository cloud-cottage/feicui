/* webui/ui/app.js —— 斐萃 本地电脑版：三 tab UI 逻辑（纯本地 JS，无 CDN 依赖）
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
    tab2: { sources: [], job: null, lastPath: '' },
    // tab3：curSubdir / files / view(四档) / page(分页) / selected / 解析回填与本地记录
    tab3: {
      subdirs: [], files: [], curSubdir: '', view: '', page: 0, selected: '',
      cfg: null, limits: null, isAdmin: false, els: {}, pageNames: [],
      thumbStat: null, previewStat: null, lastCheck: null, versions: 0
    }
  };

  // ───────────── 桥：就绪检测 + 调用 ─────────────
  var bridgeReady = false;
  window.addEventListener('pywebviewready', function () { bridgeReady = true; setModeLabel(true); });
  setTimeout(function () { setModeLabel(!!(window.pywebview && window.pywebview.api)); }, 400);

  function hasBridge() { return !!(window.pywebview && window.pywebview.api); }

  function call(method, payload) {
    if (!hasBridge()) {
      return Promise.reject(new Error('pywebview 桥未就绪（应以 ./venv/bin/python webui/app.py 启动）'));
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
  }
  function saveTab1() {
    if (!ST.tab1.selected) { setMsg('tab1-msg', '请先选中一行', 'err'); return; }
    call('tab1_save_meta', {
      filename: ST.tab1.selected.filename,
      dynasty: $('tab1-dynasty').value,
      author: $('tab1-author').value,
      notes: $('tab1-notes').value
    }).then(function (r) {
      setMsg('tab1-msg', (r && r.msg) || '', r && r.ok ? 'ok' : 'err');
      if (r && r.ok) loadTab1(false);
    });
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
    if (!ST.tab2.job || ST.tab2.job.job_id === job.job_id) { renderJob(job); }
  };
  function openInFinder() {
    var first = document.querySelector('#tab2-products .file span');
    call('open_in_finder', { path: ST.tab2.lastPath }).then(function (r) {
      setMsg('tab2-msg', (r && r.msg) || '', r && r.ok ? 'ok' : 'err');
    });
  }

  // ── tab3：3_Cropped_Tiff —— 缩略图网格（四档视图/分页/键盘导航）+ 选件解析 + 重命名 ──
  // 口径来源：旧版 `webui/src/webui.py` L528–881（view_cfg：large 5×20 / medium 10×50 /
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
