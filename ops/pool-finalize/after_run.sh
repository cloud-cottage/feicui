#!/bin/bash
# AFTER 对照：起池 → 等它**自行退出**（期望一轮落终态后 drain 退出）→ 报退出码
set -u
REPO=/Users/kevin/bistro/xiai/feicui
S=/Users/kevin/.hermes/profiles/zang/cache/scratch/feicui_tpl_unusable
LOG=$S/after.log
: >"$LOG"

export FEICUI_DB="$S/test.db"
export FEICUI_FACES_DIR="$S/faces"
export FEICUI_POOL_STATE="$S/run/pool.state.json"
export FEICUI_WORKER_LOG_DIR="$S/wlogs"
export FEICUI_ALLOW_PROD_MIGRATE=1
export FEICUI_WORKERS=1
export FEICUI_POOL_POLL=0.3

cd "$REPO/server" || exit 1
./.venv/bin/python -m app.pool --workers 1 --drain >>"$LOG" 2>&1 &
PID=$!
echo "POOL_PID=$PID"
for _ in $(seq 1 240); do
  kill -0 "$PID" 2>/dev/null || break
  sleep 0.5
done
if kill -0 "$PID" 2>/dev/null; then
  echo "TIMEOUT: 池 120s 内未自行退出（不符合预期）"
  W=$(/usr/bin/python3 -c "
import json
try:
    d=json.load(open('$S/run/pool.state.json'))
    print(' '.join(str(w['pid']) for w in d.get('workers',[]) if w.get('pid')))
except Exception: pass")
  kill -TERM "$PID" 2>/dev/null; sleep 2; kill -9 "$PID" 2>/dev/null
  for w in $W; do kill -9 "$w" 2>/dev/null; done
  exit 1
fi
wait "$PID"; RC=$?
echo "池自行退出：exit_code=$RC（uptime 见日志最后一行）"
