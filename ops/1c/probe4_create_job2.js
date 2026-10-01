(async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const out = {};
  localStorage.clear();
  const setVal = (el, v) => {
    const d = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
    d.set.call(el, v);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  };
  setVal(document.querySelector('input[placeholder*="绝对或相对路径"]'), 'tmp.pdf');
  setVal(document.querySelector('input[placeholder="如 1"]'), '20');
  setVal(document.querySelector('input[placeholder="如 544"]'), '39');
  await sleep(300);
  out.payloadShown = (document.querySelector('.actions .muted') || {}).innerText || null;
  document.querySelector('form button[type="submit"]').click();
  await sleep(3000);
  out.notices = [...document.querySelectorAll('.notice')].map(e => e.innerText.replace(/\s+/g, ' ')).slice(0, 4);
  out.created = new Date().toISOString();
  return JSON.stringify(out);
})()
