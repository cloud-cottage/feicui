#!/bin/bash
# 印章影像台账「分片续跑」器（Kong 接手单）。
# 口径：每片 --img-limit 2500 / workers 8 / delay 0.1；单片墙钟硬上限 500s（看门狗 kill）；
#       片间停 25s；幂等 resume（已存在且 sha256 一致 + TIFF 就绪的跳过）。
# 终止：ok + source_no_image（终态）达到 6765，或连续 2 片零进展，或达到 30 片上限。
# 只写 ops/seal-ingest/** 与 var/**；不提交、不 push。
set -u
ROOT=/Users/kevin/bistro/xiai/feicui
cd "$ROOT/server" || exit 1
PY="$ROOT/server/.venv/bin/python"
DB="$ROOT/var/seal_ingest.db"
LOG="$ROOT/ops/seal-ingest/11_shard.log"
PROG="$ROOT/ops/seal-ingest/11_shard_progress.json"
TARGET=6765
SHARD_CAP=500
GAP=25
MAX_SHARDS=30

counts() { "$PY" "$ROOT/ops/seal-ingest/_ledger_counts.py" "$DB"; }

zero=0
for i in $(seq 1 $MAX_SHARDS); do
  before=$(counts)
  term_before=$(printf '%s' "$before" | "$PY" -c 'import sys,json;d=json.load(sys.stdin);print(d.get("ok",0)+d.get("source_no_image",0))')
  if [ "$term_before" -ge "$TARGET" ]; then
    echo "[runner] 终态已达 $term_before/$TARGET，停。" >>"$LOG"; break
  fi
  echo "=== shard $i start $(date -Iseconds) term=$term_before ===" >>"$LOG"
  "$PY" -u -m app.seals sync-images --db "$DB" --batch-id seal_20261010_01 \
      --img-workers 8 --img-delay 0.1 --img-limit 2500 >>"$LOG" 2>&1 &
  pid=$!
  ( sleep $SHARD_CAP; kill -TERM "$pid" 2>/dev/null; sleep 8; kill -9 "$pid" 2>/dev/null ) &
  wd=$!
  wait "$pid" 2>/dev/null
  kill "$wd" 2>/dev/null; wait "$wd" 2>/dev/null
  after=$(counts)
  term_after=$(printf '%s' "$after" | "$PY" -c 'import sys,json;d=json.load(sys.stdin);print(d.get("ok",0)+d.get("source_no_image",0))')
  echo "[runner] shard $i end $(date -Iseconds) before=$before after=$after" >>"$LOG"
  printf '{"shard":%s,"at":"%s","before":%s,"after":%s,"terminal":%s,"target":%s}\n' \
     "$i" "$(date -Iseconds)" "$before" "$after" "$term_after" "$TARGET" >"$PROG"
  if [ "$term_after" -le "$term_before" ]; then
    zero=$((zero+1))
  else
    zero=0
  fi
  if [ "$term_after" -ge "$TARGET" ]; then
    echo "[runner] 全部终态 $term_after/$TARGET，完成。" >>"$LOG"; break
  fi
  if [ "$zero" -ge 2 ]; then
    echo "[runner] 连续 2 片零进展，停手。" >>"$LOG"; break
  fi
  sleep $GAP
done
echo "[runner] DONE $(date -Iseconds) $(counts)" >>"$LOG"
