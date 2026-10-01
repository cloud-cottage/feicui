(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const out = { url: location.href, title: document.title };

  // ① 等 E3 表格渲染出 items 行
  let deadline = Date.now() + 20000;
  while (Date.now() < deadline) {
    if (document.querySelectorAll('table.table tbody tr').length > 0) break;
    await sleep(400);
  }
  out.rows = document.querySelectorAll('table.table tbody tr').length;

  // ② 点每一行的「取裁图」（E6）—— 页面按需取图，不点不会触发
  const btns = Array.from(document.querySelectorAll('button')).filter(
    (b) => b.textContent.trim() === '取裁图'
  );
  out.e6Buttons = btns.length;
  btns.forEach((b) => b.click());

  // ③ 等真实字节到位（naturalWidth > 0 才叫「真实渲染出裁图」）
  deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    const im = Array.from(document.querySelectorAll('img.stampimg'));
    if (im.length && im.every((i) => i.complete && i.naturalWidth > 0)) break;
    await sleep(400);
  }

  const imgs = Array.from(document.querySelectorAll('img.stampimg'));
  out.imgCount = imgs.length;
  out.imgs = imgs.map((i) => ({
    src: i.getAttribute('src'),
    natW: i.naturalWidth,
    natH: i.naturalHeight,
    complete: i.complete,
    bytesHint: i.getAttribute('src') ? '' : '',
  }));
  out.renderedOk = imgs.filter((i) => i.naturalWidth > 0).length;

  const txt = document.body.innerText;
  out.hasUnavailableText = /裁图不可用/.test(txt);
  out.unavailableSnippets = (txt.match(/裁图不可用[^\n]{0,160}/g) || []).slice(0, 6);
  out.okSnippets = (txt.match(/真实裁图[^\n]{0,160}/g) || []).slice(0, 6);
  out.contractNoteShown = /E6（\*\*正式契约\*\*|正式契约/.test(txt);
  out.e6TemplateShown = /\/api\/jobs\/\{job_id\}\/stamps\/\{page\}\/\{idx\}\/image/.test(txt);
  return JSON.stringify(out);
})()
