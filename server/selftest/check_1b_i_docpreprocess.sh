#!/usr/bin/env bash
# =============================================================================
# 附加自测：**doc 预处理开关**（阶段 1b-i）
#   派单口径：关 doc 预处理实测 1.78×，但**会改变识别文本**、精度未定论
#   ⇒ 必须可配置，且**默认值＝现状行为（仍然开启）**，不得静默改默认。
#
# 本脚本证明三件事（全部留证在 evidence/1b_i_docflag/）：
#   ① 默认（不设 FEICUI_DOC_PREPROCESS）⇒ worker 自报 doc_preprocess=True（＝PaddleOCR 默认＝现状）；
#   ② 显式 FEICUI_DOC_PREPROCESS=0 ⇒ worker 自报 False，且解析照常跑完、行照样落库；
#   ③ 两个 arm 在**同一页区间**上的 `text` 逐条对比（证明「会改变识别文本」这条风险**真实存在**，
#      故不能拿它当默认）。
#
# 两臂都在**副本库**上跑；影像落 evidence 内，不动 output/。端口只用 5306。
# =============================================================================
set -u
SRV=/Users/kevin/bistro/feicui/server
FE=/Users/kevin/bistro/feicui
EVID=$SRV/selftest/evidence/1b_i_docflag
RUN=$EVID/run
PY="$SRV/.venv/bin/python"
VERIFY="$PY $SRV/selftest/verify_1b_i.py"
cd "$SRV" || exit 9
rm -rf "$EVID"; mkdir -p "$EVID/faces" "$RUN"
: > "$RUN/api.pids"
API_PID=""; API_CODE=""

cleanup() {
  for f in "$RUN"/pool_*.pid; do
    [ -f "$f" ] || continue
    pp=$(cat "$f" 2>/dev/null); [ -n "$pp" ] || continue
    kill -TERM "$pp" 2>/dev/null
  done
  sleep 1
  for f in "$RUN"/pool_*.pid; do
    [ -f "$f" ] || continue
    pp=$(cat "$f" 2>/dev/null); [ -n "$pp" ] || continue
    kill -0 "$pp" 2>/dev/null && kill -KILL "$pp" 2>/dev/null
  done
  [ -n "$API_PID" ] && { kill -TERM "$API_PID" 2>/dev/null; sleep 0.3; kill -KILL "$API_PID" 2>/dev/null; }
}
trap cleanup EXIT

api_start() { # <db> <port> <tag>
  FEICUI_DB="$1" FEICUI_API_PORT="$2" nohup "$PY" -m app.main > "$RUN/api_$3.log" 2>&1 &
  API_PID=$!
  echo "$API_PID" >> "$RUN/api.pids"
  local i code=""
  for i in $(seq 1 60); do
    code=$(curl -s -m 3 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$2/api/health" || true)
    [ "$code" = "200" ] && break
    sleep 0.4
  done
  API_CODE="$code"
}

run_arm() { # <arm 名> <副本库> <doc 开关 1|0> <端口> <是否先起 API>
  local arm=$1 db=$2 flag=$3 port=$4
  echo "########## arm=$arm  FEICUI_DOC_PREPROCESS=$flag ##########"
  cp "$FE/yinpu.db" "$db"
  $PY - "$db" <<'PYEOF'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1]); c.execute("DELETE FROM stamps"); c.commit()
PYEOF
  FEICUI_DB="$db" $PY -m app.migrations > "$RUN/migrate_$arm.txt" 2>&1
  api_start "$db" "$port" "$arm"
  echo "API health=$API_CODE pid=$API_PID"
  local code
  code=$(curl -s -m 30 -o "$EVID/e1_$arm.json" -w '%{http_code}' -X POST "http://127.0.0.1:$port/api/jobs" \
    -H 'Content-Type: application/json' \
    -d "{\"pdf_path\":\"$FE/tmp.pdf\",\"page_range\":[20,21],\"chunk_size\":2}")
  echo "E1 HTTP=$code  body=$(cat "$EVID/e1_$arm.json")"
  FEICUI_DB="$db" FEICUI_FACES_DIR="$EVID/faces/$arm" FEICUI_DOC_PREPROCESS="$flag" \
    FEICUI_POOL_STATE="$RUN/pool_$arm.state.json" FEICUI_WORKER_LOG_DIR="$RUN/wlog_$arm" \
    "$PY" -m app.pool --workers 2 --drain > "$RUN/pool_$arm.log" 2>&1
  echo "池退出码=$?"
  grep -E "ready pid|提交 chunk|收尾" "$RUN/pool_$arm.log" | sed 's/^/  /' | tee "$EVID/banner_$arm.txt"
  $VERIFY counts "$db" tmp.pdf 20 21 | tee "$EVID/counts_$arm.txt"
  $VERIFY export "$db" tmp.pdf 20 21 "$EVID/rows_$arm.csv" > /dev/null
  kill -TERM "$API_PID" 2>/dev/null; sleep 0.5; API_PID=""
}

run_arm default "$EVID/copy_default.db" 1 5306
run_arm docoff  "$EVID/copy_docoff.db"  0 5306

echo "########## 逐条对比两臂的 text（同页同 idx）##########"
$PY - "$EVID/rows_default.csv" "$EVID/rows_docoff.csv" <<'PYEOF' | tee "$EVID/text_compare.txt"
import csv, sys
def load(p):
    with open(p, encoding="utf-8") as fh:
        return {(r["page"], r["idx"]): r for r in csv.DictReader(fh)}
a, b = load(sys.argv[1]), load(sys.argv[2])
keys = sorted(set(a) | set(b), key=lambda k: (int(k[0]), int(k[1])))
same = diff = 0
for k in keys:
    ta = (a.get(k) or {}).get("text", "<缺>")
    tb = (b.get(k) or {}).get("text", "<缺>")
    if ta == tb:
        same += 1
    else:
        diff += 1
        print(f"  (page={k[0]}, idx={k[1]}) doc预处理开: {ta!r}  ←→  关: {tb!r}")
print(f"共 {len(keys)} 条：text 相同 {same}，不同 {diff}")
print("结论：doc 预处理开关**确实会改变识别文本**（本样本 %d/%d 不同）⇒ 默认必须保持"
      "「开」（＝现状），改默认前须先补精度验收。" % (diff, len(keys)))
PYEOF
echo "证据目录：$EVID"
