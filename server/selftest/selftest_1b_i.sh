#!/usr/bin/env bash
# =============================================================================
# 阶段 1b-i 自测（执行层：常驻 4-worker 池 / 页级 chunk 并行 / 游标推进 / 断点续跑 / 幂等）
#   Kong · 2026-09-20 · 规范 = ../docs/feicui.spec.md v1.2
#
# 纪律（硬约束）：
#   * **只用副本库**：正式 feicui/yinpu.db 全程只读，末尾比对 md5；
#   * 影像一律落 `server/selftest/evidence/1b_i/faces/<arm>/…`（**不动 output/ 既有产物**）；
#   * 端口只用 **5301–5305**（非登记端口），停进程**只用精确 PID**（严禁 pkill/killall 宽匹配）；
#   * 性能类读数一律标注「同机可能有并发任务、非受控基线」，不作验收依据。
#
# 实现注记（踩过的坑，勿回退）：
#   * 起 daemon（API / 池）**不得**放在 `$( … )` 命令替换里——后台进程会继承替换管道的写端，
#     `$( )` 会一直等不到 EOF 而挂死（实测）。故 daemon 一律以「直接后台作业」启动，
#     PID 立刻由 `$!` 取得并写进 `run/*.pids`（这就是后面精确 kill 的依据）。
#
# 跑法：  bash selftest/selftest_1b_i.sh
# =============================================================================
set -u

SRV=/Users/kevin/bistro/shu/feicui/server
FE=/Users/kevin/bistro/shu/feicui
EVID=$SRV/selftest/evidence/1b_i
RUN=$EVID/run
PY="$SRV/.venv/bin/python"
VERIFY="$PY $SRV/selftest/verify_1b_i.py"
PDF="$FE/tmp.pdf"
BOOK="tmp.pdf"

cd "$SRV" || exit 9
rm -rf "$EVID"; mkdir -p "$EVID/db" "$RUN" "$EVID/faces"
: > "$RUN/api.pids"

PASS=0; FAIL=0
ck()   { if [ "$2" = "$3" ]; then echo "PASS  $1：$2"; PASS=$((PASS+1)); else echo "FAIL  $1：expect=$2 got=$3"; FAIL=$((FAIL+1)); fi; }
ckne() { if [ "$2" != "$3" ]; then echo "PASS  $1：$2 (≠ $3)"; PASS=$((PASS+1)); else echo "FAIL  $1：不应等于 $3"; FAIL=$((FAIL+1)); fi; }
ckgt() { if [ "$2" -gt "$3" ] 2>/dev/null; then echo "PASS  $1：$2 > $3"; PASS=$((PASS+1)); else echo "FAIL  $1：$2 未 > $3"; FAIL=$((FAIL+1)); fi; }
ceq()  { if [ "$2" = "$3" ]; then echo "PASS  $1：$2"; PASS=$((PASS+1)); else echo "FAIL  $1：expect=$2 got=$3"; FAIL=$((FAIL+1)); fi; }

cleanup() {
  while read -r pid; do
    [ -n "$pid" ] || continue
    kill -TERM "$pid" 2>/dev/null; sleep 0.2; kill -KILL "$pid" 2>/dev/null
  done < "$RUN/api.pids"
  # 中途崩掉时别留孤儿池（精确 PID，来自脚本自己记的 pid 文件）
  for f in "$RUN"/pool_*.pid; do
    [ -f "$f" ] || continue
    pp=$(cat "$f" 2>/dev/null)
    [ -n "$pp" ] || continue
    kill -TERM "$pp" 2>/dev/null
  done
  sleep 1
  for f in "$RUN"/pool_*.pid; do
    [ -f "$f" ] || continue
    pp=$(cat "$f" 2>/dev/null)
    [ -n "$pp" ] || continue
    kill -0 "$pp" 2>/dev/null && kill -KILL "$pp" 2>/dev/null
  done
}
trap cleanup EXIT

J() { $PY -c "import json,sys;d=json.load(open(sys.argv[1]));print(eval(sys.argv[2]))" "$1" "$2"; }
qs() { # <db> <sql> → 单值（独立只读连接）
  $PY -c "
import sqlite3,sys
c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True)
print(c.execute(sys.argv[2]).fetchone()[0])
" "$1" "$2"
}
jl() { # <json> <expr>，读最后一行的 json 文件（imgman 的 "# files=N root=…"）
  $PY -c "import json,sys;print(json.load(open(sys.argv[1])))" "$1" "$2" 2>/dev/null || true
}

# ---------------------------------------------------------------- daemon 管控（精确 PID）
API_PID=""; API_CODE=""
api_start() { # <db> <port> <tag>
  local db=$1 port=$2 tag=$3 i code=""
  FEICUI_DB="$db" FEICUI_API_PORT="$port" nohup "$PY" -m app.main > "$RUN/api_$tag.log" 2>&1 &
  API_PID=$!
  echo "$API_PID" >> "$RUN/api.pids"
  for i in $(seq 1 60); do
    code=$(curl -s -m 3 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/api/health" || true)
    [ "$code" = "200" ] && break
    sleep 0.4
  done
  API_CODE="$code"
  echo "  [api_start] db=$db port=$port pid=$API_PID health=$code"
}
api_stop() { # <pid> → 回显 gone / STILL_ALIVE
  kill -TERM "$1" 2>/dev/null; sleep 0.7; kill -KILL "$1" 2>/dev/null
  if kill -0 "$1" 2>/dev/null; then echo "STILL_ALIVE"; else echo "gone"; fi
}
POOL_PID=""
pool_run() { # <db> <workers> <tag> <faces> <drain 0|1> <mode fg|bg>
  local db=$1 w=$2 tag=$3 faces=$4 drain=$5 mode=${6:-fg}
  local -a args=(--workers "$w")
  [ "$drain" = "1" ] && args+=(--drain)
  if [ "$mode" = "bg" ]; then
    FEICUI_DB="$db" FEICUI_FACES_DIR="$faces" \
      FEICUI_POOL_STATE="$RUN/pool_$tag.state.json" FEICUI_WORKER_LOG_DIR="$RUN/wlog_$tag" \
      nohup "$PY" -m app.pool "${args[@]}" > "$RUN/pool_$tag.log" 2>&1 &
    POOL_PID=$!
    echo "$POOL_PID" > "$RUN/pool_$tag.pid"
    echo "  [pool_run bg] tag=$tag workers=$w pid=$POOL_PID"
  else
    FEICUI_DB="$db" FEICUI_FACES_DIR="$faces" \
      FEICUI_POOL_STATE="$RUN/pool_$tag.state.json" FEICUI_WORKER_LOG_DIR="$RUN/wlog_$tag" \
      "$PY" -m app.pool "${args[@]}" > "$RUN/pool_$tag.log" 2>&1
    return $?
  fi
}
e1() { # <port> <lo> <hi> <chunk> <outfile> → http code
  curl -s -m 30 -o "$5" -w '%{http_code}' -X POST "http://127.0.0.1:$1/api/jobs" \
    -H 'Content-Type: application/json' \
    -d "{\"pdf_path\":\"$PDF\",\"page_range\":[$2,$3],\"chunk_size\":$4}"
}
e2() { # <port> <job> <outfile> → http code
  curl -s -m 30 -o "$3" -w '%{http_code}' "http://127.0.0.1:$1/api/jobs/$2"
}
worker_pids() { # <statefile>
  $PY -c "
import json,sys
d=json.load(open(sys.argv[1]))
print(' '.join(str(w['pid']) for w in d['workers'] if w.get('pid')))" "$1"
}

echo "==================== 0. 前置证据 ===================="
{
  echo "核验时点 $(date '+%Y-%m-%d %H:%M:%S')（Asia/Shanghai）"
  md5 "$FE/yinpu.db"; ls -l "$FE/yinpu.db"; stat -f 'inode=%i size=%z mtime=%Sm' "$FE/yinpu.db"
  echo "--- 正式库目录内 yinpu.db* 旁文件（应无 wal/shm）---"
  ls -1 "$FE" | grep -E 'yinpu\.db' || true
} > "$EVID/01_prod_db_md5_before.txt" 2>&1
cat "$EVID/01_prod_db_md5_before.txt"

"$FE/venv/bin/python" -m pip freeze > "$EVID/02_main_venv_freeze.txt" 2>&1
$PY -m pip freeze > "$EVID/03_server_venv_freeze.txt" 2>&1
wc -l "$EVID/02_main_venv_freeze.txt" "$EVID/03_server_venv_freeze.txt"
{
  echo "== 关键包版本（worker 侧，必须与 spike 基线一致）=="
  "$FE/venv/bin/python" -c "
import importlib.metadata as md
for p in ['paddleocr','paddlepaddle','pymupdf','numpy','opencv-python','streamlit']:
    try: print(f'{p}=={md.version(p)}')
    except Exception as e: print(f'{p}: {e}')
"
  echo "== feicui/venv 内是否存在 fastapi（应为 ModuleNotFoundError）=="
  "$FE/venv/bin/python" -c "import fastapi" 2>&1 | tail -1
  echo "== server/.venv 内是否存在 OCR 栈 / pymupdf（应为 ModuleNotFoundError，§6.5）=="
  $PY -c "import paddleocr" 2>&1 | tail -1
  $PY -c "import fitz" 2>&1 | tail -1
} > "$EVID/04_main_venv_key_versions.txt" 2>&1
cat "$EVID/04_main_venv_key_versions.txt"

md5 "$FE/processor.py" "$FE/export.py" "$FE/app.py" > "$EVID/05_untouched_files_before.txt"
{ echo "== 端口（5301-5305，应全 0 监听）=="
  for p in 5301 5302 5303 5304 5305; do echo -n "$p: "; lsof -nP -iTCP:$p -sTCP:LISTEN 2>/dev/null | tail -n +2 | wc -l | tr -d ' '; done; } > "$EVID/06_port_before.txt" 2>&1
cat "$EVID/06_port_before.txt"

echo "==================== 1. 建副本 + 迁移（每臂独立副本）===================="
for arm in A_main B_serial C_parallel D_resume E_sep; do cp "$FE/yinpu.db" "$EVID/db/copy_$arm.db"; done
# T4 / T2 / T5 需要「空库」口径 ⇒ 在**副本**里清空 stamps（正式库一字未动）
for arm in B_serial C_parallel D_resume E_sep; do
  $PY - "$EVID/db/copy_$arm.db" <<'PYEOF'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1]); c.execute("DELETE FROM stamps"); c.commit()
print(f"{sys.argv[1]}: 清空后 stamps =", c.execute("select count(*) from stamps").fetchone()[0])
PYEOF
done > "$EVID/09_empty_copies.txt" 2>&1
cat "$EVID/09_empty_copies.txt"
for arm in A_main B_serial C_parallel D_resume E_sep; do
  FEICUI_DB="$EVID/db/copy_$arm.db" $PY -m app.migrations > "$EVID/10_migrate_$arm.txt" 2>&1
  echo "--- $arm ---"; grep -E 'applied|skipped|journal_mode' "$EVID/10_migrate_$arm.txt"
done
A="$EVID/db/copy_A_main.db"; B="$EVID/db/copy_B_serial.db"; C="$EVID/db/copy_C_parallel.db"
D="$EVID/db/copy_D_resume.db"; E="$EVID/db/copy_E_sep.db"

echo "==================== ② 基础：E1 → 池真执行（4 worker）→ E2 真推进 ===================="
api_start "$A" 5301 t1; AP1=$API_PID
ck "API(5301) 就绪" "200" "$API_CODE"
$VERIFY counts "$A" "$BOOK" 20 26 > "$EVID/31_counts_before_run.txt"
cat "$EVID/31_counts_before_run.txt"
code=$(e1 5301 20 26 2 "$EVID/30_e1_job1.json"); ck "E1 建 job（页 20-26, chunk=2）HTTP" "201" "$code"
cat "$EVID/30_e1_job1.json"; echo
JOB1=$(J "$EVID/30_e1_job1.json" "d['job_id']")
echo "job1=$JOB1"
SECONDS=0
pool_run "$A" 4 t1 "$EVID/faces/t1" 1 fg
echo "池（4 worker, --drain）耗时 ${SECONDS}s  ← 同机可能有并发任务、非受控基线"
tail -12 "$RUN/pool_t1.log"
ck "job1 终态" "DONE" "$(qs "$A" "select state from jobs where job_id='$JOB1'")"
code=$(e2 5301 "$JOB1" "$EVID/33_e2_job1.json"); ck "E2 HTTP" "200" "$code"
$PY -m json.tool "$EVID/33_e2_job1.json" > "$EVID/33_e2_job1.pretty.json"; cat "$EVID/33_e2_job1.pretty.json"
$VERIFY recompute "$A" "$JOB1" > "$EVID/34_recompute_job1.json"
$VERIFY e2check "$A" "$JOB1" "$EVID/33_e2_job1.json" > "$EVID/35_e2check_job1.txt" 2>&1; RC=$?
cat "$EVID/35_e2check_job1.txt"
ceq "E2 ↔ 库内复算 逐字段一致" "0" "$RC"
ck "E2 done_pages == total_pages" "$(J "$EVID/33_e2_job1.json" "d['done_pages']")" "$(J "$EVID/33_e2_job1.json" "d['total_pages']")"
ck "E2 failed_pages 空（不得假完成，S-2）" "[]" "$(J "$EVID/33_e2_job1.json" "d['failed_pages']")"
ckgt "E2 counters.detected 非零" "$(J "$EVID/33_e2_job1.json" "d['counters']['detected']")" 0
ckgt "E2 counters.inserted 非零（真写库）" "$(J "$EVID/33_e2_job1.json" "d['counters']['inserted']")" 0
$VERIFY counts "$A" "$BOOK" 20 26 > "$EVID/36_counts_after_run.txt"; cat "$EVID/36_counts_after_run.txt"
INS=$(J "$EVID/33_e2_job1.json" "d['counters']['inserted']")
ck "库内 20-26 行数 == counters.inserted" "$(J "$EVID/36_counts_after_run.txt" "d['scope_rows']")" "$INS"
$VERIFY imgman "$EVID/faces/t1" > "$EVID/37_imgman_after_run.txt"
NFILES=$(tail -1 "$EVID/37_imgman_after_run.txt" | sed 's/.*files=//;s/ .*//')
ck "影像文件数 == counters.inserted" "$NFILES" "$INS"
$VERIFY pages "$A" "$JOB1" > "$EVID/38_job1_pages.json"
ck "chunks 全部完成" "$(J "$EVID/38_job1_pages.json" "d['chunks_done']")" "$(J "$EVID/38_job1_pages.json" "d['chunks_total']")"
ck "chunk 数 == ceil(7/2)" "$(J "$EVID/38_job1_pages.json" "d['chunks_total']")" "4"

echo "==================== ③ 幂等：同书同区间重跑（AC-01 / AC-02）===================="
$VERIFY counts "$A" "$BOOK" 20 26 > "$EVID/40_unique_before_rerun.txt"
$VERIFY rowsig "$A" "$BOOK" 20 26 > "$EVID/41_rowsig_before_rerun.txt"
$VERIFY export "$A" "$BOOK" 20 26 "$EVID/42_rows_before_rerun.csv" > /dev/null
$VERIFY imgman "$EVID/faces/t1" > "$EVID/43_imgman_before_rerun.txt"
cat "$EVID/41_rowsig_before_rerun.txt"; cat "$EVID/40_unique_before_rerun.txt"
code=$(e1 5301 20 26 2 "$EVID/44_e1_job2_rerun.json"); ck "E1 第二次同书同区间（job1 已终态 ⇒ 允许新 job）HTTP" "201" "$code"
cat "$EVID/44_e1_job2_rerun.json"; echo
JOB2=$(J "$EVID/44_e1_job2_rerun.json" "d['job_id']")
ckne "第二次建单得到新 job_id（§2.1 G-4：不得复用旧游标）" "$JOB2" "$JOB1"
SECONDS=0; pool_run "$A" 4 t3 "$EVID/faces/t1" 1 fg; echo "重跑池耗时 ${SECONDS}s（非受控基线）"
tail -6 "$RUN/pool_t3.log"
code=$(e2 5301 "$JOB2" "$EVID/45_e2_job2.json"); ck "E2(job2) HTTP" "200" "$code"
$PY -m json.tool "$EVID/45_e2_job2.json" > "$EVID/45_e2_job2.pretty.json"
$VERIFY e2check "$A" "$JOB2" "$EVID/45_e2_job2.json" > "$EVID/46_e2check_job2.txt" 2>&1; RC=$?
cat "$EVID/46_e2check_job2.txt"
ceq "E2(job2) ↔ 库内复算 逐字段一致" "0" "$RC"
ck "重跑 counters.inserted == 0（AC-01 判据）" "$(J "$EVID/45_e2_job2.json" "d['counters']['inserted']")" "0"
ckgt "重跑 counters.skipped 非零（旧行被跳过而非改写）" "$(J "$EVID/45_e2_job2.json" "d['counters']['skipped']")" 0
$VERIFY rowsig "$A" "$BOOK" 20 26 > "$EVID/47_rowsig_after_rerun.txt"; cat "$EVID/47_rowsig_after_rerun.txt"
ck "行集指纹重跑前后一致（旧行零改写）" "$(cat "$EVID/41_rowsig_before_rerun.txt")" "$(cat "$EVID/47_rowsig_after_rerun.txt")"
$VERIFY export "$A" "$BOOK" 20 26 "$EVID/48_rows_after_rerun.csv" > /dev/null
$VERIFY diffcsv "$EVID/42_rows_before_rerun.csv" "$EVID/48_rows_after_rerun.csv" > "$EVID/49_diff_before_after_rerun.txt" 2>&1; RC=$?
cat "$EVID/49_diff_before_after_rerun.txt"
ceq "逐字段 CSV diff（重跑前后，0 差异）" "0" "$RC"
$VERIFY imgman "$EVID/faces/t1" > "$EVID/4A_imgman_after_rerun.txt"
ck "影像清单（路径+sha256）重跑前后完全一致（AC-02）" "$(cat "$EVID/43_imgman_before_rerun.txt")" "$(cat "$EVID/4A_imgman_after_rerun.txt")"
$VERIFY counts "$A" "$BOOK" 20 26 > "$EVID/4B_unique_after_rerun.txt"; cat "$EVID/4B_unique_after_rerun.txt"
ck "行数不变（无重复插入）" "$(J "$EVID/40_unique_before_rerun.txt" "d['scope_rows']")" "$(J "$EVID/4B_unique_after_rerun.txt" "d['scope_rows']")"
ck "唯一性：scope_rows == distinct_keys" "$(J "$EVID/4B_unique_after_rerun.txt" "d['scope_rows']")" "$(J "$EVID/4B_unique_after_rerun.txt" "d['scope_distinct_keys']")"
ck "唯一性：全表 rows == distinct_keys" "$(J "$EVID/4B_unique_after_rerun.txt" "d['table_rows']")" "$(J "$EVID/4B_unique_after_rerun.txt" "d['table_distinct_keys']")"
echo "API-stop(t1/t3)=$(api_stop "$AP1")"

echo "==================== ④ 并行 == 串行（AC-04：空库副本 w=1 vs w=4）===================="
api_start "$B" 5302 t4a; AP4A=$API_PID
code=$(e1 5302 27 33 2 "$EVID/50_e1_serial.json"); ck "E1（w=1 臂，页 27-33）HTTP" "201" "$code"
SECONDS=0; pool_run "$B" 1 t4_serial "$EVID/faces/w1" 1 fg; echo "串行臂耗时 ${SECONDS}s（非受控基线）"
$VERIFY counts "$B" "$BOOK" 27 33 > "$EVID/51_serial_counts.txt"
$VERIFY export "$B" "$BOOK" 27 33 "$EVID/52_serial_rows.csv" > /dev/null
$VERIFY rowsig "$B" "$BOOK" 27 33 > "$EVID/53_serial_rowsig.txt"
$VERIFY imgman "$EVID/faces/w1" > "$EVID/54_serial_imgman.txt"
e2 5302 "$(J "$EVID/50_e1_serial.json" "d['job_id']")" "$EVID/55_e2_serial.json" > /dev/null
echo "串行臂 行数=$(J "$EVID/51_serial_counts.txt" "d['scope_rows']")"
echo "API-stop=$API_PID -> $(api_stop "$AP4A")"

api_start "$C" 5303 t4b; AP4B=$API_PID
code=$(e1 5303 27 33 2 "$EVID/56_e1_parallel.json"); ck "E1（w=4 臂，同页区间）HTTP" "201" "$code"
SECONDS=0; pool_run "$C" 4 t4_parallel "$EVID/faces/w4" 1 fg; echo "并行臂耗时 ${SECONDS}s（非受控基线）"
$VERIFY counts "$C" "$BOOK" 27 33 > "$EVID/57_parallel_counts.txt"
$VERIFY export "$C" "$BOOK" 27 33 "$EVID/58_parallel_rows.csv" > /dev/null
$VERIFY rowsig "$C" "$BOOK" 27 33 > "$EVID/59_parallel_rowsig.txt"
$VERIFY imgman "$EVID/faces/w4" > "$EVID/5A_parallel_imgman.txt"
e2 5303 "$(J "$EVID/56_e1_parallel.json" "d['job_id']")" "$EVID/5B_e2_parallel.json" > /dev/null
echo "并行臂 行数=$(J "$EVID/57_parallel_counts.txt" "d['scope_rows']")"
$VERIFY diffcsv "$EVID/52_serial_rows.csv" "$EVID/58_parallel_rows.csv" > "$EVID/5C_diff_serial_vs_parallel.txt" 2>&1; RC=$?
cat "$EVID/5C_diff_serial_vs_parallel.txt"
ceq "AC-04：两臂全字段逐条 diff（0 差异）" "0" "$RC"
ck "两臂行数一致" "$(J "$EVID/51_serial_counts.txt" "d['scope_rows']")" "$(J "$EVID/57_parallel_counts.txt" "d['scope_rows']")"
ck "两臂行集指纹一致" "$(cat "$EVID/53_serial_rowsig.txt")" "$(cat "$EVID/59_parallel_rowsig.txt")"
ck "两臂影像内容一致（bonus：仅比 sha256+相对路径+字节数，注释行含臂特有 root 故排除）" \
   "$(grep -v '^#' "$EVID/54_serial_imgman.txt")" "$(grep -v '^#' "$EVID/5A_parallel_imgman.txt")"
ck "并行臂唯一性" "$(J "$EVID/57_parallel_counts.txt" "d['scope_rows']")" "$(J "$EVID/57_parallel_counts.txt" "d['scope_distinct_keys']")"
echo "API-stop=$API_PID -> $(api_stop "$AP4B")"

echo "==================== ① 断点续跑（AC-03：精确 PID SIGKILL 全部 worker + 池 → 重启续跑）===================="
api_start "$D" 5304 t2; AP2=$API_PID
code=$(e1 5304 27 33 2 "$EVID/60_e1_resume.json"); ck "E1（续跑臂，页 27-33，空库）HTTP" "201" "$code"
JD=$(J "$EVID/60_e1_resume.json" "d['job_id']")
pool_run "$D" 4 t2_resume "$EVID/faces/resume" 0 bg
POOLPID=$POOL_PID
echo "池 PID=${POOLPID}（state=$RUN/pool_t2_resume.state.json）"
MID=0
for i in $(seq 1 400); do
  DONE_C=$(qs "$D" "select count(*) from job_pages where job_id='$JD' and state='DONE'")
  TOT_C=$(qs "$D" "select count(*) from job_pages where job_id='$JD'")
  if [ "${DONE_C:-0}" -ge 2 ] && [ "${DONE_C:-0}" -lt "${TOT_C:-0}" ]; then MID=1; break; fi
  sleep 0.2
done
ck "捕捉到中途窗口（已提交页 ≥2 且 < 总页数）" "1" "$MID"
DONE_MID=$(qs "$D" "select count(*) from job_pages where job_id='$JD' and state='DONE'")
ROWS_MID=$(qs "$D" "select count(*) from stamps where pdf_name='$BOOK'")
KILL_AT=$(date '+%Y-%m-%d %H:%M:%S')
WPIDS=$(worker_pids "$RUN/pool_t2_resume.state.json")
echo "kill 时点 $KILL_AT | 已提交页=$DONE_MID 行=$ROWS_MID | worker PIDs=[$WPIDS] pool=$POOLPID"
{ echo "== SIGKILL 前 ps（精确 PID）=="; ps -o pid,ppid,pgid,lstart,command -p $WPIDS $POOLPID 2>&1 | cut -c1-150; } > "$EVID/64_ps_before_kill.txt"
cat "$EVID/64_ps_before_kill.txt"
kill -KILL $WPIDS $POOLPID 2>/dev/null
sleep 1
{ echo "== SIGKILL 后 kill -0 逐 PID（非零＝确已死）=="
  for p in $WPIDS $POOLPID; do kill -0 "$p" 2>/dev/null; echo "pid=$p kill -0 -> $?"; done
  echo "== ps 复查（应无这些 PID）=="; ps -o pid,command -p $WPIDS $POOLPID 2>&1 | cut -c1-120; } > "$EVID/65_kill_verify.txt"
cat "$EVID/65_kill_verify.txt"
DEAD=1; for p in $WPIDS $POOLPID; do kill -0 "$p" 2>/dev/null && DEAD=0; done
ck "全部 worker + 池确已被精确 PID SIGKILL（kill -0 全非零）" "1" "$DEAD"
# 断点冻结态快照（**在 SIGKILL 之后取**：此刻已无写者，读数即崩溃瞬间的库内真相）
$VERIFY pages "$D" "$JD" > "$EVID/61_pages_at_kill.json"
$VERIFY rowsig "$D" "$BOOK" > "$EVID/62_rowsig_at_kill.json"
$VERIFY export "$D" "$BOOK" 27 33 "$EVID/62_rows_at_kill.csv" > "$EVID/62_rows_at_kill.txt"
$VERIFY counts "$D" "$BOOK" > "$EVID/63_counts_at_kill.txt"
echo "断点冻结态：$($PY -c "
import json;d=json.load(open('$EVID/61_pages_at_kill.json'))
print('已完成 chunk', d['chunks_done'], '/', d['chunks_total'], '| 页状态', {p['state'] for p in d['pages']})")"
{
  echo "== 崩溃后库内游标（页状态保留、无「半页」：提交点=chunk 边界）=="
  $PY - "$D" "$JD" <<'PYEOF'
import sqlite3, sys
c = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
print("job_pages 状态分布:", c.execute("select state,count(*) from job_pages where job_id=? group by state", (sys.argv[2],)).fetchall())
print("jobs.state:", c.execute("select state from jobs where job_id=?", (sys.argv[2],)).fetchone()[0])
print("stamps 行数:", c.execute("select count(*) from stamps").fetchone()[0])
print("chunk 级状态:", c.execute("select chunk_index, group_concat(state) from job_pages where job_id=? group by chunk_index", (sys.argv[2],)).fetchall())
PYEOF
} > "$EVID/66_after_kill_db.txt" 2>&1
cat "$EVID/66_after_kill_db.txt"
SECONDS=0
pool_run "$D" 4 t2_resume2 "$EVID/faces/resume" 1 fg
echo "续跑耗时 ${SECONDS}s（非受控基线）"
grep -E "断点续跑入口|认领 job|收尾" "$RUN/pool_t2_resume2.log" | head -6 | tee "$EVID/67_resume_log.txt"
ck "续跑后 job 终态" "DONE" "$(qs "$D" "select state from jobs where job_id='$JD'")"
code=$(e2 5304 "$JD" "$EVID/68_e2_resume.json"); ck "E2(续跑) HTTP" "200" "$code"
$PY -m json.tool "$EVID/68_e2_resume.json" > "$EVID/68_e2_resume.pretty.json"
$VERIFY e2check "$D" "$JD" "$EVID/68_e2_resume.json" > "$EVID/69_e2check_resume.txt" 2>&1; RC=$?
cat "$EVID/69_e2check_resume.txt"
ceq "E2(续跑) ↔ 库内复算 逐字段一致" "0" "$RC"
$VERIFY counts "$D" "$BOOK" 27 33 > "$EVID/6A_resume_counts.txt"; cat "$EVID/6A_resume_counts.txt"
$VERIFY export "$D" "$BOOK" 27 33 "$EVID/6B_resume_rows.csv" > /dev/null
ck "AC-03：续跑终态行数 == 串行一次跑完的行数" "$(J "$EVID/51_serial_counts.txt" "d['scope_rows']")" "$(J "$EVID/6A_resume_counts.txt" "d['scope_rows']")"
$VERIFY diffcsv "$EVID/52_serial_rows.csv" "$EVID/6B_resume_rows.csv" > "$EVID/6C_diff_serial_vs_resume.txt" 2>&1; RC=$?
cat "$EVID/6C_diff_serial_vs_resume.txt"
ceq "AC-03：续跑终态 vs 串行 全字段 diff（0 差异）" "0" "$RC"
ck "AC-03：重复性 count == count(distinct pdf||page||idx)" "$(J "$EVID/6A_resume_counts.txt" "d['scope_rows']")" "$(J "$EVID/6A_resume_counts.txt" "d['scope_distinct_keys']")"
$VERIFY rowsig "$D" "$BOOK" > "$EVID/6D_resume_rowsig.txt"
$VERIFY subset "$EVID/62_rows_at_kill.csv" "$EVID/6B_resume_rows.csv" > "$EVID/6E_subset_killrows.txt" 2>&1; RC=$?
cat "$EVID/6E_subset_killrows.txt"
ceq "AC-03：断点前已提交行在终态里逐字节未变（判负项反面）" "0" "$RC"
echo "API-stop=$AP2 -> $(api_stop "$AP2")"

echo "==================== ⑤ 进程分离（AC-11：kill 接口层后 worker 仍推进游标）===================="
api_start "$E" 5305 t5; AP5=$API_PID
code=$(e1 5305 20 70 2 "$EVID/70_e1_sep.json"); ck "E1（进程分离臂，页 20-70，26 chunk）HTTP" "201" "$code"
JE=$(J "$EVID/70_e1_sep.json" "d['job_id']")
pool_run "$E" 4 t5 "$EVID/faces/sep" 1 bg
POOLPID5=$POOL_PID
echo "池 PID=$POOLPID5"
C1=0
for i in $(seq 1 400); do
  C1=$(qs "$E" "select count(distinct chunk_index) from job_pages where job_id='$JE' and state='DONE'")
  [ "${C1:-0}" -ge 1 ] && break
  sleep 0.2
done
echo "已完成 chunk=$C1 ⇒ 现在 SIGKILL 接口层（精确 PID ${AP5}）"
kill -KILL "$AP5" 2>/dev/null; sleep 0.5
ck "接口层已被 SIGKILL（kill -0 非零）" "gone" "$(kill -0 "$AP5" 2>/dev/null && echo alive || echo gone)"
WPIDS5=$(worker_pids "$RUN/pool_t5.state.json")
{
  echo "== 接口层死后（$(date '+%H:%M:%S')）worker 存活核查 =="
  for p in $WPIDS5; do kill -0 "$p" 2>/dev/null; echo "worker pid=$p kill -0 -> $? (0=存活)"; done
  echo "== worker ps =="; ps -o pid,ppid,lstart,command -p $WPIDS5 2>&1 | cut -c1-140
  echo "== 池 ps =="; ps -o pid,lstart,command -p "$POOLPID5" 2>&1 | cut -c1-140
} > "$EVID/71_after_api_kill.txt"
cat "$EVID/71_after_api_kill.txt"
ALIVE=1; for p in $WPIDS5; do kill -0 "$p" 2>/dev/null || ALIVE=0; done
ck "接口层死后全部 worker 仍存活（kill -0 全 0）" "1" "$ALIVE"
S1=$(qs "$E" "select count(distinct chunk_index) from job_pages where job_id='$JE' and state='DONE'")
T1S=$(date '+%H:%M:%S'); sleep 6
S2=$(qs "$E" "select count(distinct chunk_index) from job_pages where job_id='$JE' and state='DONE'")
T2S=$(date '+%H:%M:%S')
{ echo "采样1 $T1S 已完成 chunk=$S1"; echo "采样2 ${T2S}（+6s）已完成 chunk=$S2"; } > "$EVID/72_cursor_advance.txt"
cat "$EVID/72_cursor_advance.txt"
ckgt "AC-11：接口层死后 cursor 单调推进（已完成 chunk 数增长）" "$S2" "$S1"
echo "等池跑完（--drain）…"
for i in $(seq 1 900); do kill -0 "$POOLPID5" 2>/dev/null || break; sleep 1; done
kill -0 "$POOLPID5" 2>/dev/null && echo "池仍在跑（超时，见日志）" || echo "池已退出"
ck "进程分离臂 job 终态" "DONE" "$(qs "$E" "select state from jobs where job_id='$JE'")"
api_start "$E" 5305 t5b; AP5B=$API_PID
code=$(e2 5305 "$JE" "$EVID/73_e2_after_restart.json"); ck "重启后 E2 HTTP" "200" "$code"
$PY -m json.tool "$EVID/73_e2_after_restart.json" > "$EVID/73_e2_after_restart.pretty.json"; cat "$EVID/73_e2_after_restart.pretty.json"
$VERIFY recompute "$E" "$JE" > "$EVID/74_recompute_sep.json"
$VERIFY e2check "$E" "$JE" "$EVID/73_e2_after_restart.json" > "$EVID/75_e2check_sep.txt" 2>&1; RC=$?
cat "$EVID/75_e2check_sep.txt"
ceq "AC-11：重启后 E2 ↔ 库内复算 逐字段一致" "0" "$RC"
echo "API-stop=$AP5B -> $(api_stop "$AP5B")"

echo "==================== ⑨ 收尾：端口 / 正式库未变 / 汇总 ===================="
{ echo "== 端口（5301-5305 应收敛为 0 监听）=="
  for p in 5301 5302 5303 5304 5305; do echo -n "$p: "; lsof -nP -iTCP:$p -sTCP:LISTEN 2>/dev/null | tail -n +2 | wc -l | tr -d ' '; done; } > "$EVID/80_port_after.txt" 2>&1
cat "$EVID/80_port_after.txt"
{ echo "核验时点 $(date '+%Y-%m-%d %H:%M:%S')（Asia/Shanghai）"; md5 "$FE/yinpu.db"; ls -l "$FE/yinpu.db"
  stat -f 'inode=%i size=%z mtime=%Sm' "$FE/yinpu.db"
  echo "--- yinpu.db* 旁文件（应无 wal/shm）---"; ls -1 "$FE" | grep -E 'yinpu\.db' || true; } > "$EVID/81_prod_db_md5_after.txt" 2>&1
cat "$EVID/81_prod_db_md5_after.txt"
ck "正式库 md5 前后一致" "$(grep -E '^MD5' "$EVID/01_prod_db_md5_before.txt")" "$(grep -E '^MD5' "$EVID/81_prod_db_md5_after.txt")"
md5 "$FE/processor.py" "$FE/export.py" "$FE/app.py" > "$EVID/82_untouched_files_after.txt"
ck "processor/export/app 未改动（md5 前后一致）" "$(cat "$EVID/05_untouched_files_before.txt")" "$(cat "$EVID/82_untouched_files_after.txt")"
ck "output/ 未被写入（无 faces 子目录）" "0" "$(ls -d "$FE/output/faces" 2>/dev/null | wc -l | tr -d ' ')"
{
  echo "== 池日志关键行 =="
  for f in "$RUN"/pool_*.log; do echo "--- $f ---"; grep -E "池启动|ready pid|派 chunk|提交 chunk|收尾|退回 PENDING" "$f" | head -8; done
  echo "== worker 日志（每臂 worker0 末尾）=="
  for d in "$RUN"/wlog_*; do echo "--- $d ---"; tail -2 "$d"/worker0.log 2>/dev/null | cut -c1-160; done
} > "$EVID/83_pool_logs_key_lines.txt" 2>&1
head -60 "$EVID/83_pool_logs_key_lines.txt"

{
  echo "==================== 1b-i 自测汇总 $(date '+%Y-%m-%d %H:%M:%S') ===================="
  echo "PASS=$PASS  FAIL=$FAIL"
  [ "$FAIL" -eq 0 ] && echo "结论：ALL PASS" || echo "结论：存在 FAIL（见上方 FAIL 行）"
} | tee "$EVID/90_summary.txt"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
