set -u
S=/Users/kevin/.hermes/profiles/zang/cache/scratch/feicui_tpl_unusable
export FEICUI_DB="$S/test.db" FEICUI_FACES_DIR="$S/faces" FEICUI_POOL_STATE="$S/run/pool.state.json" \
       FEICUI_WORKER_LOG_DIR="$S/wlogs" FEICUI_ALLOW_PROD_MIGRATE=1 FEICUI_WORKERS=1 FEICUI_POOL_POLL=0.3
cd /Users/kevin/bistro/xiai/feicui/server || exit 1
: >"$S/after2.log"
./.venv/bin/python -m app.pool --workers 1 --drain >>"$S/after2.log" 2>&1 &
PID=$!
for _ in $(seq 1 240); do kill -0 "$PID" 2>/dev/null || break; sleep 0.5; done
if kill -0 "$PID" 2>/dev/null; then echo "TIMEOUT: 未自行退出"; exit 1; fi
wait "$PID"; RC=${?}
echo "池自行退出：exit_code=${RC}"
