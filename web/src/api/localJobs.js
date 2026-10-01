// 浏览器本地记录（localStorage）—— 仅用于「E1 建 job 成功」后的本机留痕。
// 用途：spec §3 未定义 job 列表端点（README §4 G-2），页面需要一份**来源明确**的
// 本机记录；这份记录**不是后端真值**，界面上必须与后端数据分栏并标注来源。
const KEY = 'feicui.local-jobs.v1'

export function readLocalJobs() {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function rememberLocalJob({ job_id, pdf_path, state, created_at }) {
  if (!job_id) return readLocalJobs()
  const list = readLocalJobs().filter((j) => j && j.job_id !== job_id)
  list.unshift({
    job_id,
    pdf_path: pdf_path || null,
    state: state || null,
    created_at: created_at || null,
    recorded_at: new Date().toISOString(),
    source: 'localStorage（本浏览器；来源＝E1 的响应，非后端列表接口）',
  })
  try {
    localStorage.setItem(KEY, JSON.stringify(list.slice(0, 50)))
  } catch {
    /* 存储不可用时静默放弃（不因此造假） */
  }
  return readLocalJobs()
}

export function forgetLocalJob(jobId) {
  const list = readLocalJobs().filter((j) => j && j.job_id !== jobId)
  try {
    localStorage.setItem(KEY, JSON.stringify(list))
  } catch {
    /* noop */
  }
  return list
}

export function clearLocalJobs() {
  try {
    localStorage.removeItem(KEY)
  } catch {
    /* noop */
  }
  return []
}
