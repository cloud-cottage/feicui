<script setup>
// E2 的 counters 原样展示（spec §3.1 E2：detected/inserted/updated/skipped/ocr_empty）。
// **不做任何派生计算**：后端没给的键显示 `—`，不补 0。
import { E2_COUNTER_KEYS } from '@/config/constants'
import { isNil } from '@/utils/format'

defineProps({
  counters: { type: Object, default: null },
})
</script>

<template>
  <table class="kv">
    <tbody>
      <tr v-for="k in E2_COUNTER_KEYS" :key="k">
        <th><code>counters.{{ k }}</code></th>
        <td>{{ counters && !isNil(counters[k]) ? counters[k] : '—' }}</td>
      </tr>
    </tbody>
  </table>
</template>
