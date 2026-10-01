(async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const JOB = 'job-de324032aa4c4601afd5cb165e7950a0';
  const out = { href: location.href, samples: [] };
  for (let i = 0; i < 40; i++) {
    const st = await (async () => {
      const r = await fetch('/feicui/api/jobs/' + JOB);
      return await r.json();
    })();
    const dom = document.body.innerText.replace(/\s+/g, ' ');
    // 进度条宽度（前端只按后端 done/total 派生）
    const bar = document.querySelector('.progress__bar, [class*=progress] div, progress');
    out.samples.push({
      t: new Date().toISOString().slice(11, 19),
      state: st.state, done: st.done_pages, total: st.total_pages,
      cursor: st.cursor, detected: st.counters.detected, inserted: st.counters.inserted,
      domState: (dom.match(/state\s+(QUEUED|RUNNING|PAUSED|DONE|FAILED_PARTIAL)/) || [])[1] || null,
      domDone: (dom.match(/done_pages\s+(\d+)/) || [])[1] || null,
      domProgress: (dom.match(/进度（后端复算值，S-1）\s*([^\s]+)/) || [])[1] || null,
      barWidth: bar ? (bar.style && bar.style.width) || null : null,
    });
    if (st.state === 'DONE' || st.state === 'FAILED_PARTIAL') break;
    await sleep(2000);
  }
  out.hrefEnd = location.href;
  out.uniqueProgress = Array.from(new Set(out.samples.map(s => `${s.domState}/${s.domDone}/${s.domProgress}`)));
  return JSON.stringify(out);
})()
