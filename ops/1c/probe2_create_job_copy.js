(async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const out = {};
  localStorage.clear();               // 清掉上一轮（正式库那单）的本机记录，避免混淆
  out.href = location.href;
  out.banner = (document.querySelector('.banner') || {}).innerText || null;
  out.bannerClass = (document.querySelector('.banner') || {}).className || null;
  const setVal = (el, v) => {
    const d = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
    d.set.call(el, v);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  };
  const pdf = document.querySelector('input[placeholder*="绝对或相对路径"]');
  const from = document.querySelector('input[placeholder="如 1"]');
  const to = document.querySelector('input[placeholder="如 544"]');
  setVal(pdf, 'tmp.pdf');
  setVal(from, '13');
  setVal(to, '19');
  await sleep(300);
  out.payloadShown = (document.querySelector('.actions .muted') || {}).innerText || null;
  out.beforeCreate = await (async () => {
    const r = await fetch('/feicui/api/jobs?limit=5');
    return await r.json();
  })();
  document.querySelector('form button[type="submit"]').click();
  await sleep(3500);
  out.notices = [...document.querySelectorAll('.notice')].map(e => e.innerText).slice(0, 5);
  out.localJobsRaw = localStorage.getItem('feicui.local-jobs.v1');
  out.hrefAfter = location.href;
  return JSON.stringify(out);
})()
