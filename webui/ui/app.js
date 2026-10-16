/* webui/ui/app.js —— 斐萃 本地电脑版：三 tab UI 逻辑（纯本地 JS，无 CDN 依赖）
 *
 * 桥：window.pywebview.api[method](payload) —— 由 pywebview 注入（唯一形态＝原生窗口）。
 * 进度：Python 端 `window.evaluate_js('window.onProgress(…)')` 推；另有 1.5 s 轮询兜底。
 */
(function () {
  'use strict';

  var ST = {                     // 页面状态（单页应用的手写小 store）
    user: null, root: '', navPath: '', curSubdir: '',
    tab1: { rows: [], items: [], selected: null, options: [] },
    tab2: { sources: [], job: null, lastPath: '' },
    tab3: { subdirs: [], files: [] }
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
    call('app_info').then(function (r) {
      if (r && r.ok) { $('app-version').textContent = 'v' + r.version; }
    });
    loadTab1();
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

  // ── tab3 ──
  function loadTab3(subdir) {
    call('tab3_list', { subdir: subdir || ST.curSubdir || '' }).then(function (r) {
      if (!r || !r.ok) { setMsg('tab3-msg', (r && r.msg) || '加载失败', 'err'); return; }
      ST.tab3.subdirs = r.subdirs || []; ST.curSubdir = r.current || '';
      $('tab3-template').textContent = r.template || '—';
      var ul = $('tab3-subdirs'); ul.innerHTML = '';
      if (!ST.tab3.subdirs.length) { ul.innerHTML = '<li class="muted">（3_Cropped_Tiff 下无子目录）</li>'; }
      ST.tab3.subdirs.forEach(function (d) {
        var li = document.createElement('li');
        li.textContent = '📁 ' + d;
        li.classList.toggle('active', d === ST.curSubdir);
        li.addEventListener('click', function () { loadTab3(d); });
        ul.appendChild(li);
      });
      $('tab3-title').textContent = '文件（' + ST.curSubdir + '，' + (r.files || []).length + ' 个）';
      var tb = $('tab3-files'); tb.innerHTML = '';
      (r.files || []).forEach(function (f) {
        var tr = document.createElement('tr');
        [f.name, f.size_mb, f.shiwen, f.dynasty, f.author, f.standard ? '✔' : '✘', f.mtime]
          .forEach(function (v) { var td = document.createElement('td'); td.textContent = v; tr.appendChild(td); });
        tb.appendChild(tr);
      });
      setMsg('tab3-msg', '');
    });
  }
  function genTestTab3() {
    if (!ST.curSubdir) { setMsg('tab3-msg', '请先选择子目录', 'err'); return; }
    call('tab3_generate_test', { subdir: ST.curSubdir }).then(function (r) {
      setMsg('tab3-msg', (r && r.msg) || '', r && r.ok ? 'ok' : 'err');
      if (r && r.ok) loadTab3(ST.curSubdir);
    });
  }

  // ───────────── 事件绑定 ─────────────
  function bindAll() {
    bindLogin(); bindTabs();
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
    $('btn-tab3-refresh').addEventListener('click', function () { loadTab3(ST.curSubdir); });
    $('btn-tab3-test').addEventListener('click', genTestTab3);
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
