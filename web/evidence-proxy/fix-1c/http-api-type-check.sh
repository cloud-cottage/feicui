#!/bin/bash
# 阶段 1c-修复 证据①：API 路径的响应体类型对照（真跑，不解释）。
# 断言：经 5164 与直连 5195 的 /feicui/api/** 都必须是 JSON（5196 未启动 ⇒ 代理层 503 JSON），
#       绝不得是 text/html。
probe() {
  local url="$1"
  local hdr body ct st
  hdr=$(curl -s -D- -o /tmp/f1c.body --max-time 6 "$url")
  body=$(cat /tmp/f1c.body)
  st=$(printf '%s' "$hdr" | awk 'NR==1{print $2}')
  ct=$(printf '%s' "$hdr" | grep -i '^content-type:' | head -1 | tr -d '\r' | cut -d' ' -f2-)
  local kind
  if printf '%s' "$body" | /usr/bin/python3 -c 'import json,sys; json.load(sys.stdin)' 2>/dev/null; then kind=JSON; else kind=NOT_JSON; fi
  printf '%-42s status=%-4s content-type=%-32s body=%s\n' "$url" "$st" "$ct" "$kind"
  printf '    body: %s\n' "$(printf '%s' "$body" | head -c 220)"
  printf '    html-marker(<title>印索): %s\n' "$(printf '%s' "$body" | grep -c '<title>印索' || true)"
}
echo "### ①-1 经 5164 的 API 路径（页面实际走的路径）"
probe "http://localhost:5164/feicui/api/jobs"
echo "### ①-2 直连 5195 同一路径（对照）"
probe "http://127.0.0.1:5195/feicui/api/jobs"
echo "### ①-3 直连 5195 旧路径（兼容键 '/api' 仍在）"
probe "http://127.0.0.1:5195/api/jobs"
echo "### ①-4 旧缺陷路径对照：5164 根下的 /api（原 API_BASE='/api' 会打到这）"
probe "http://localhost:5164/api/jobs"
echo "### ①-5 页面壳（应当仍是 text/html，与上面区隔）"
probe "http://localhost:5164/feicui/"
echo "### ①-6 5195 上的探针端点（dev-only，直连可用）"
probe "http://127.0.0.1:5195/__feicui/backend-probe"
echo "### ①-7 探针端点经 5164（已知缺口，记录真实行为）"
probe "http://localhost:5164/__feicui/backend-probe"
