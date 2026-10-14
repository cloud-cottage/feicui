<script setup>
// 站点外壳：固定页眉（品牌＋标题）＋ 全局后端状态横幅 ＋ 页签条 ＋ 路由出口。
// 页脚登记本前端所依据的规范版本与 md5，便于对照（只读引用，不改规范）。
import BackendBanner from '@/components/BackendBanner.vue'

const SPEC_PATH = 'feicui/docs/feicui.spec.md'
const SPEC_VERSION = 'v1.1'
const SPEC_MD5 = '4264927baf24bb7f48e12366cd861fe7'
</script>

<template>
  <div class="shell">
    <header class="shell__head">
      <div class="brand">
        <strong>斐萃</strong>
        <span class="muted">印谱解析任务台</span>
      </div>
    </header>

    <BackendBanner />

    <main class="shell__main">
      <nav class="shell__tabs">
        <RouterLink to="/">印谱解析</RouterLink>
        <RouterLink to="/persons">印人采集</RouterLink>
        <RouterLink to="/items">印谱采集</RouterLink>
        <RouterLink to="/seals">印章采集</RouterLink>
        <RouterLink to="/pdf-records">PDF 资料</RouterLink>
      </nav>
      <RouterView />
    </main>

    <footer class="shell__foot">
      <span>
        契约依据：<code>{{ SPEC_PATH }}</code> {{ SPEC_VERSION }}（md5 <code>{{ SPEC_MD5 }}</code>）— 前端只读引用，
        未修改规范文件。
      </span>
      <span class="muted">
        本工程＝阶段 1a 前端骨架；后端接口在另一路。零 CDN / 零外链资源。
      </span>
    </footer>
  </div>
</template>
