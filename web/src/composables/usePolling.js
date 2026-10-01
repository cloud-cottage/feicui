// 轮询取数（**只重新取数，不推进任何本地进度**）。
// S-1 纪律：这里的定时器唯一作用是「再次调用后端接口」。界面上的任何进度值
// 都必须来自后端返回（done_pages / total_pages），前端**不得**在定时器里自增。
import { onBeforeUnmount, ref } from 'vue'

export function usePolling(task, { interval = 2000 } = {}) {
  const running = ref(false)
  const lastRunAt = ref(null)
  const runCount = ref(0)
  let timer = null
  let inFlight = false

  function stamp() {
    const d = new Date()
    const p = (n) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(
      d.getMinutes()
    )}:${p(d.getSeconds())}`
  }

  async function tick() {
    if (inFlight) return
    inFlight = true
    try {
      await task()
      lastRunAt.value = stamp()
      runCount.value += 1
    } finally {
      inFlight = false
    }
  }

  function start() {
    if (timer) return
    running.value = true
    tick()
    timer = setInterval(tick, interval)
  }

  function stop() {
    if (timer) clearInterval(timer)
    timer = null
    running.value = false
  }

  onBeforeUnmount(stop)

  return { start, stop, tick, running, lastRunAt, runCount, interval }
}
