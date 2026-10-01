(async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const JOB = 'job-b87c4878f9914400b1f86a13613041c2';
  const out = { href: location.href, samples: [] };
  for (let i = 0; i < 18; i++) {
    const st = await (async () => {
      const r = await fetch('/feicui/api/jobs/' + JOB);
      return await r.json();
    })();
    const dom = document.body.innerText.replace(/\s+/g, ' ');
    out.samples.push({
      t: new Date().toISOString().slice(11, 19),
      api: { state: st.state, done: st.done_pages, total: st.total_pages, cursor: st.cursor, counters: st.counters },
      domSnippet: dom.slice(120, 360),
    });
    if (st.state === 'DONE' || st.state === 'FAILED_PARTIAL') break;
    await sleep(2500);
  }
  const hits = document.body.innerText.match(/排队中|运行中|已暂停|完成|部分失败/g);
  out.stateTextSeen = hits ? Array.from(new Set(hits)) : [];
  out.hrefEnd = location.href;
  return JSON.stringify(out);
})()
