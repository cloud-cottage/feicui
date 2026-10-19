<script setup>
// 站点外壳（v1.41 对齐 webui/ui 顶栏形态）：白底圆角顶栏 ＝ 56px 圆角 logo ＋
// h1.brand 全串（「斐萃」玺印解析任务台 ＋ hostname 动态后缀）＋ 页签 ＋ 右侧动作区。
// 后缀判定走纯函数 `editionSuffix()`（见 composables/useEdition.js；可单测）：
//   localhost / 127.0.0.1 / ::1 / *.local ⇒ 「 · 本地服务私有版」（feicui-local-private）
//   其它（公网域名）⇒ 无后缀（feicui-web）。`web/index.html` 静态兜底 title 保持公网版
//   （无后缀）——公网页面零闪变；本地页仅首帧前短暂无后缀、挂载即更正。
// 页脚登记本前端所依据的规范版本与 md5，便于对照（只读引用，不改规范）。
import { onMounted } from 'vue'
import BackendBanner from '@/components/BackendBanner.vue'
import { BASE_TITLE, useEdition } from '@/composables/useEdition'
import logoUrl from '@/assets/feicui.png'

const SPEC_PATH = 'feicui/docs/feicui.spec.md'
const SPEC_VERSION = 'v1.1'
const SPEC_MD5 = '4264927baf24bb7f48e12366cd861fe7'

// 版本后缀与全串标题（运行时一次性判定；不随路由变化）
const { suffix, fullTitle } = useEdition()
// 右侧动作区 pill（webui .pill 形态）：文案由同一纯函数派生，非独立真源
const editionLabel = suffix ? '本地服务私有版' : '公网版'

onMounted(() => {
  document.title = fullTitle
})
</script>

<template>
  <div class="shell">
    <header class="shell__head">
      <div class="shell__head-left">
        <img class="brand-logo" :src="logoUrl" width="56" height="56" alt="斐萃 logo" title="斐萃" />
        <div class="brand-block">
          <h1 class="brand">{{ BASE_TITLE }}{{ suffix }}</h1>
          <span class="brand-sub">数字玺印生成工具</span>
        </div>
        <nav class="shell__tabs" aria-label="页面导航">
          <RouterLink to="/">印谱解析</RouterLink>
          <RouterLink to="/persons">印人采集</RouterLink>
          <RouterLink to="/items">印谱采集</RouterLink>
          <RouterLink to="/seals">印章采集</RouterLink>
          <RouterLink to="/pdf-records">PDF 资料</RouterLink>
        </nav>
      </div>
      <div class="shell__head-right">
        <span class="pill" data-edition>{{ editionLabel }}</span>
      </div>
    </header>

    <BackendBanner />

    <main class="shell__main">
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
