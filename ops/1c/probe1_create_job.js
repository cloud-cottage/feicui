(async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const out = {};
  out.href = location.href;
  out.title = document.title;
  // ① 横幅（探针是否生效：应与 API 同源、显示「后端已连接」）
  out.banner = (document.querySelector('.banner') || {}).innerText || null;
  out.bannerClass = (document.querySelector('.banner') || {}).className || null;
  // ② 探针与 API 同源的直接证据：在页面上下文里各自打一次
  out.probePath_fetch = await (async () => {
    const r = await fetch('/feicui/__feicui/backend-probe');
    return { status: r.status, ct: r.headers.get('content-type'), body: (await r.text()).slice(0, 200) };
  })();
  out.apiPath_fetch = await (async () => {
    const r = await fetch('/feicui/api/jobs?limit=1');
    return { status: r.status, ct: r.headers.get('content-type'), body: (await r.text()).slice(0, 200) };
  })();
  // ③ 建 job（真书：tmp.pdf 13–19）
  const setVal = (el, v) => {
    const d = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
    d.set.call(el, v);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  };
  const pdf = document.querySelector('input[placeholder*="绝对或相对路径"]');
  const from = document.querySelector('input[placeholder="如 1"]');
  const to = document.querySelector('input[placeholder="如 544"]');
  out.formFound = { pdf: !!pdf, from: !!from, to: !!to };
  setVal(pdf, 'tmp.pdf');
  setVal(from, '13');
  setVal(to, '19');
  await sleep(300);
  out.lastPayloadShown = (document.querySelector('.actions .muted') || {}).innerText || null;
  const btn = document.querySelector('form button[type="submit"]');
  btn.click();
  await sleep(4000);
  const notices = [...document.querySelectorAll('.notice, [class*=notice]')].map(e => e.innerText);
  out.notices = notices.slice(0, 6);
  out.bodyHead = document.body.innerText.slice(0, 1200);
  out.localJobs = localStorage.getItem('feicui.localJobs') || localStorage.getItem('feicui_local_jobs');
  out.allLocalKeys = Object.keys(localStorage);
  return JSON.stringify(out);
})()
