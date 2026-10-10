import { createRouter, createWebHistory } from 'vue-router'
import JobsPage from '@/pages/JobsPage.vue'
import JobDetailPage from '@/pages/JobDetailPage.vue'
import ResultsPage from '@/pages/ResultsPage.vue'
import MissingPage from '@/pages/MissingPage.vue'
import PersonsPage from '@/pages/PersonsPage.vue'
import ItemsPage from '@/pages/ItemsPage.vue'
import SealsPage from '@/pages/SealsPage.vue'

// 路由对应 spec §3 的页面职责：
//   /                     印谱解析（E1）
//   /persons              印人采集页（批 1：复旦印藏「印人」标签页）
//   /jobs/:job_id         任务详情（E2，真实进度 S-1）
//   /jobs/:job_id/results 结果页（E3，6 字段信封；预留）
//   /jobs/:job_id/missing 缺失清单（E5）
// 阶段 1c 修复（G-1）：history 必须**带 base**。
// feicui 前端被 shu/web（5164）以 `/feicui` 反代直达，vite.config.js 的 base = '/feicui/'，
// 故取 import.meta.env.BASE_URL（= '/feicui/'）作为 history base。
// 若用无参 createWebHistory()（= '/'），则 `/feicui/**` 在路由表里视为未匹配，
// 被下方 `{ path: '/:pathMatch(.*)*', redirect: '/' }` 归一化 → replaceState('/')，
// 结果「地址栏掉回 5164 根、刷新落回印索营销页」（G-1 实测）。
// 注意：路由表条目**一律未动**，仅 base 一处。
export default createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'jobs', component: JobsPage },
    { path: '/persons', name: 'persons', component: PersonsPage },
    { path: '/items', name: 'items', component: ItemsPage },
    { path: '/seals', name: 'seals', component: SealsPage },
    { path: '/jobs/:job_id', name: 'job-detail', component: JobDetailPage },
    { path: '/jobs/:job_id/results', name: 'job-results', component: ResultsPage },
    { path: '/jobs/:job_id/missing', name: 'job-missing', component: MissingPage },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
