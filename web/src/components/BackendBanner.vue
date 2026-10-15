<script setup>
// 顶部状态横幅：① 后端未启动（硬要求：必须显式显示，绝不用假数据顶替）
//              ② DEV FIXTURE 已启用（默认关闭，开启时醒目告警）
//              ③ 后端已连接（一行小字，供对照）
import { FIXTURE_ENABLED } from '@/config/env'
import { useBackendStatus } from '@/composables/useBackendStatus'

const { state, isDown, isUp, target } = useBackendStatus()
</script>

<template>
  <div class="banner-stack">
    <div v-if="FIXTURE_ENABLED" class="banner banner--fixture" role="alert">
      <strong>DEV FIXTURE 已启用 —— 以下为示例数据，非后端真实数据。</strong>
      <span class="banner__hint">
        仅供离线自测 UI 骨架，不得作为任何验收依据。关闭方式：去掉环境变量
        <code>VITE_FEICUI_DEV_FIXTURE</code>。
      </span>
    </div>

    <div v-if="isDown" class="banner banner--down" role="alert">
      <strong>后端未启动 / 未连接</strong>
      <span class="banner__hint">
        目标 <code>{{ target }}</code> 连不上（
        <code>{{ state.detail || 'ECONNREFUSED' }}</code> ）。本页不展示任何示例或估算数据。
      </span>
      <span class="banner__hint">
        启动提示：<code>cd /Users/kevin/bistro/feicui/server &amp;&amp; ./.venv/bin/python -m app.main</code>
      </span>
      <span class="banner__hint">最后探测时点：{{ state.lastCheck || '—' }}</span>
    </div>

    <div v-else-if="isUp" class="banner banner--up">
      后端已连接（<code>{{ target }}</code>）· 最后探测 {{ state.lastCheck || '—' }}
    </div>

    <div v-else class="banner banner--unknown">
      后端连通性未知（dev 探测端点不可用，例如 preview / 生产构建）；后端数据一律以接口响应为准。
    </div>
  </div>
</template>
