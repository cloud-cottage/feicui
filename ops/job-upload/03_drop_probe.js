/* 拖曳上传 · 真浏览器 drop 全链路探针（Kong）——在页面里 `Runtime.evaluate(awaitPromise)` 执行。
 *
 * 断言链（**真 File + 真 DataTransfer + 真 drop 事件**，不调用后端私有钩子）：
 *   ① 结构：pdf_path 的可见输入框已被拖放区取代；折叠块 `<details>` 默认**收起**、内含原输入框；
 *   ② 拖动高亮：`dragover` ⇒ `.dropzone--over`；
 *   ③ drop 真 `File`（`%PDF-` 合法 1 页 PDF）⇒ 记录 `POST …/api/jobs/upload` 的**真实状态码**；
 *   ④ 上传成功后：表单拿到服务器侧 `pdf_path`、只读回显、进度条出现（体积小 ⇒ 一次读满）；
 *   ⑤ 填页范围 → 点「建 job」⇒ 记录 `POST …/api/jobs`（**E1**）的状态码与既有 job_id（409 时）；
 *   ⑥ 非 PDF 内容（名字伪装成 .pdf）⇒ 服务器 `400 NOT_A_PDF` ⇒ 页面上**可见**错误文案；
 *   ⑦ 非 .pdf 扩展名 ⇒ 前端先拦下（**不发请求**）⇒ 可见错误文案。
 *
 * 用法：本文件内容即表达式；两个源各跑一次（`http://127.0.0.1:5195/feicui/` 与
 * `http://localhost:5164/feicui/`），返回值为 JSON 字符串。
 */
(async () => {
  const B64 =
    'JVBERi0xLjcKJcK1wrYKJSBXcml0dGVuIGJ5IE11UERGIDEuMjguMgoKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFIvSW5mbzw8L1Byb2R1Y2VyKE11UERGIDEuMjguMik+Pj4+CmVuZG9iagoKMiAwIG9iago8PC9UeXBlL1BhZ2VzL0NvdW50IDEvS2lkc1s0IDAgUl0+PgplbmRvYmoKCjMgMCBvYmoKPDwvRm9udDw8L2hlbHYgNSAwIFI+Pj4+CmVuZG9iagoKNCAwIG9iago8PC9UeXBlL1BhZ2UvTWVkaWFCb3hbMCAwIDU5NSA4NDJdL1JvdGF0ZSAwL1Jlc291cmNlcyAzIDAgUi9QYXJlbnQgMiAwIFIvQ29udGVudHNbNiAwIFJdPj4+CmVuZG9iagoKNSAwIG9iago8PC9UeXBlL0ZvbnQvU3VidHlwZS9UeXBlMS9CYXNlRm9udC9IZWx2ZXRpY2EvRW5jb2RpbmcvV2luQW5zaUVuY29kaW5nPj4KZW5kb2JqCgo2IDAgb2JqCjw8L0xlbmd0aCA5MC9GaWx0ZXIvRmxhdGVEZWNvZGU+PgpzdHJlYW0KeDrjKuRyCuEyVDAAQkMFcyMFc3MDhZBcLv2M1JwyBUNDhZA0hWgbMzMzUzNLM2NzIGlkkGSOgEYGJoYgESMDcwMzQzNzM1MjA2NDu9gQLy7XEK5ALgAOXhW+CmVuZHN0cmVhbQplbmRvYmoKCnhyZWYKMCA3CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDA0MiAwMDAwMCBuIAowMDAwMDAwMTIwIDAwMDAwIG4gCjAwMDAwMDAxNzIgMDAwMDAgbiAKMDAwMDAwMDIxMyAwMDAwMCBuIAowMDAwMDAwMzIwIDAwMDAwIG4gCjAwMDAwMDA0MDkgMDAwMDAgbiAKCnRyYWlsZXIKPDwvU2l6ZSA3L1Jvb3QgMSAwIFIvSURbPEMyOEU2MDJBMzFDM0IwQzI5MkMyODk0RUMzOUE1NDY4PjxBMzIxRThCNTcyNTk0OTFENUExRDdBNzQ4M0M5QUJCRT5dPj4Kc3RhcnR4cmVmCjU2NwolJUVPRgo='

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
  const out = { href: location.href, origin: location.origin, checks: {} }
  const net = []
  const wrap = (proto) => {
    const open = proto.open
    const send = proto.send
    proto.open = function (m, u, ...rest) {
      this.__url = u
      return open.call(this, m, u, ...rest)
    }
    proto.send = function (...args) {
      this.addEventListener('loadend', () =>
        net.push({ url: String(this.__url), status: this.status, body: String(this.responseText || '').slice(0, 300) })
      )
      return send.apply(this, args)
    }
  }
  wrap(XMLHttpRequest.prototype)
  const origFetch = window.fetch
  window.fetch = async (...a) => {
    const res = await origFetch(...a)
    try {
      const clone = res.clone()
      const txt = await clone.text()
      net.push({ url: String(typeof a[0] === 'string' ? a[0] : (a[0] && a[0].url) || ''), status: res.status, body: txt.slice(0, 300) })
    } catch (e) {
      net.push({ url: 'fetch', status: res.status, body: `<clone 失败 ${e}>` })
    }
    return res
  }

  const bytes = Uint8Array.from(atob(B64), (c) => c.charCodeAt(0))
  const mkFile = (name, data, type) => new File([data], name, { type })
  const zone = document.querySelector('.dropzone')
  const waitFor = async (fn, timeout = 60000, step = 250) => {
    const t0 = Date.now()
    while (Date.now() - t0 < timeout) {
      const v = fn()
      if (v) return v
      await sleep(step)
    }
    return null
  }
  const setByPlaceholder = (ph, val) => {
    const el = [...document.querySelectorAll('input[type=text]')].find((i) => i.placeholder === ph)
    if (!el) return false
    el.value = val
    el.dispatchEvent(new Event('input', { bubbles: true }))
    return true
  }

  // ① 结构
  const det = document.querySelector('details.advanced')
  out.checks.structure = {
    dropzone_present: !!zone,
    dropzone_roles: zone ? { role: zone.getAttribute('role'), tabindex: zone.getAttribute('tabindex') } : null,
    file_input_inside: !!(zone && zone.querySelector('input[type=file]')),
    file_input_accept: zone && zone.querySelector('input[type=file]') ? zone.querySelector('input[type=file]').accept : null,
    visible_text_inputs_outside_details: [...document.querySelectorAll('input[type=text]')].filter(
      (i) => !i.closest('details')
    ).length,
    placeholder_text_inputs_outside_details: [...document.querySelectorAll('input[type=text]')]
      .filter((i) => !i.closest('details'))
      .map((i) => i.placeholder),
    details_present: !!det,
    details_open_by_default: det ? det.open : null,
    details_summary_text: det ? det.querySelector('summary').innerText.trim() : null,
    advanced_input_inside_details: !!(det && det.querySelector('input[type=text]')),
    advanced_input_value_after_drop: null,
  }

  // ② 拖动高亮
  const dt0 = new DataTransfer()
  dt0.items.add(mkFile('hover.pdf', bytes, 'application/pdf'))
  zone.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: dt0 }))
  await sleep(60)
  out.checks.dragover_highlight = zone.className.includes('dropzone--over')
  zone.dispatchEvent(new DragEvent('dragleave', { bubbles: true, cancelable: true, dataTransfer: dt0 }))
  await sleep(60)
  out.checks.dragleave_clears_highlight = !zone.className.includes('dropzone--over')

  // ③ drop 真 File（合法 PDF）
  const tag = location.port
  const probeName = `拖曳测试-${tag}-${Date.now()}.pdf`
  const dt = new DataTransfer()
  dt.items.add(mkFile(probeName, bytes, 'application/pdf'))
  zone.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }))
  out.checks.drop_dispatched = { name: probeName, fileBytes: bytes.length }

  const okBox = await waitFor(() => document.querySelector('.uploadbox--ok'), 60000)
  out.checks.upload_ok_box = !!okBox
  out.checks.upload_box_text = okBox ? okBox.innerText.replace(/\s+/g, ' ').trim() : null
  out.checks.upload_error_text = (document.querySelector('.uploadbox--err') || { innerText: null }).innerText
  out.checks.upload_request = net.find((r) => r.url.includes('/api/jobs/upload')) || null
  out.checks.form_pdf_path_after_drop = det ? (det.querySelector('input[type=text]') || {}).value : null
  out.checks.form_row_placeholders = [...document.querySelectorAll('.field-row input[type=text]')].map((i) => i.placeholder)

  // ④ 提交 E1（页范围 1..1 保证可派生 total_pages）
  out.checks.set_page_from = setByPlaceholder('如 1', '1')
  out.checks.set_page_to = setByPlaceholder('如 544', '1')
  const submitBtn = document.querySelector('.actions button[type=submit]')
  out.checks.submit_disabled_before_click = submitBtn ? submitBtn.disabled : null
  if (submitBtn) submitBtn.click()
  const notice = await waitFor(
    () => [...document.querySelectorAll('.notice')].find((n) => /201 已建 job|409 冲突/.test(n.innerText)),
    90000
  )
  out.checks.e1_notice_text = notice ? notice.innerText.replace(/\s+/g, ' ').trim().slice(0, 400) : null
  out.checks.e1_request = net.find((r) => /\/api\/jobs$/.test(r.url)) || null
  out.checks.local_jobs_row = (() => {
    try {
      const list = JSON.parse(localStorage.getItem('feicui.local-jobs.v1') || '[]')
      return list[0] ? { job_id: list[0].job_id, pdf_path: list[0].pdf_path } : null
    } catch {
      return null
    }
  })()

  // ⑤ 非 PDF 内容（名字伪装 .pdf）⇒ 服务器 400 NOT_A_PDF
  const dt2 = new DataTransfer()
  dt2.items.add(mkFile('伪装成PDF的文本.pdf', 'this is not a pdf at all\n'.repeat(3), 'application/pdf'))
  zone.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt2 }))
  const errBox = await waitFor(() => document.querySelector('.uploadbox--err'), 30000)
  out.checks.fake_pdf_error_text = errBox ? errBox.innerText.replace(/\s+/g, ' ').trim().slice(0, 300) : null

  // ⑥ 非 .pdf 扩展名 ⇒ 前端先拦（不发请求）
  const before = net.length
  const dt3 = new DataTransfer()
  dt3.items.add(mkFile('notes.txt', 'plain text', 'text/plain'))
  zone.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt3 }))
  await sleep(600)
  out.checks.txt_error_text = (document.querySelector('.uploadbox--err') || { innerText: null }).innerText
  out.checks.txt_requests_sent = net.length - before

  out.net = net
  out.upload_requests = net.filter((r) => r.url.includes('/api/jobs/upload'))
  return JSON.stringify(out)
})()
