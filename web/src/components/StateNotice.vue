<script setup>
// 统一状态块：把「后端未启动 / 后端尚未提供该接口 / 接口报错 / 无数据」与「有数据」严格区分开。
// 空白与假数据都是禁止的（README §1）；这里保证任何非数据分支都有明确文案。
defineProps({
  kind: { type: String, default: 'info' }, // backend-down | not-implemented | error | empty | info | loading
  title: { type: String, default: '' },
  detail: { type: String, default: '' },
  rawText: { type: String, default: '' },
  statusCode: { type: [Number, String], default: '' },
})
</script>

<template>
  <div class="notice" :class="`notice--${kind}`">
    <div class="notice__head">
      <strong>{{ title }}</strong>
      <span v-if="statusCode !== ''" class="notice__code">HTTP {{ statusCode }}</span>
    </div>
    <p v-if="detail" class="notice__detail">{{ detail }}</p>
    <slot />
    <details v-if="rawText" class="notice__raw">
      <summary>原始响应体（原样展示，未改写）</summary>
      <pre>{{ rawText }}</pre>
    </details>
  </div>
</template>
