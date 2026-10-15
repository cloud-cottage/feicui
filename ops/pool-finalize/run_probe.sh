#!/bin/bash
# 池侧「模板不可用 ⇒ 落终态 / 停止重试」对照探针脚本（用 scratch 库，绝不碰生产库）
# 用法： run_probe.sh <before|after>
set -u
PHASE="${1:?before|after}"
REPO=/Users/kevin/bistro/feicui
S=/Users/kevin/.hermes/profiles/zang/cache/scratch/feicui_tpl_unusable
DB=$S/test.db
LOG=$S/${PHASE}.log
SECS="${SECS:-55}"

: >"$LOG"

export FEICUI_DB="$DB"
export FEICUI_FACES_DIR="$S/faces"
export FEICUI_POOL_STATE="$S/run/pool.state.json"
export FEICUI_WORKER_LOG_DIR="$S/wlogs"
export FEICUI_ALLOW_PROD_MIGRATE=1
export FEICUI_WORKERS=1
export FEICUI_POOL_POLL=0.3

cd "$REPO/server" || exit 1
./.venv/bin/python -m app.pool --workers 1 --drain >>"$LOG" 2>&1 &
POOL_PID=$!
echo "POOL_PID=$POOL_PID"

# 记录本次池的 worker PID（从状态文件读，精确收尾；绝不用宽匹配 kill）
sleep "$SECS"

WORKERS=""
if [ -f "$S/run/pool.state.json" ]; then
  WORKERS=$(/usr/bin/python3 -c "
import json,sys
try:
    d=json.load(open('$S/run/pool.state.json'))
    print(' '.join(str(w['pid']) for w in d.get('workers',[]) if w.get('pid')))
except Exception as e:
    print('', end='')
")
fi

ALIVE=0
kill -0 "$POOL_PID" 2>/dev/null && ALIVE=1
echo "PHASE=$PHASE SECS=$SECS POOL_PID=$POOL_PID POOL_STILL_ALIVE=$ALIVE WORKERS_PIDS='$WORKERS'"
echo "=== 池是否自行退出：$([ $ALIVE -eq 1 ] && echo 否（仍在跑，需人工停） || echo 是（自行退出）) ==="
