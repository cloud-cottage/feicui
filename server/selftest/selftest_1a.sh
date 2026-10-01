#!/usr/bin/env bash
# =============================================================================
# feicui API 阶段 1a 自测（Kong）—— 全程只用 yinpu.db 的**临时副本**
#
# 覆盖（对应派单五条必测）：
#   ① 同一 pdf_path 建 job 两次 ⇒ 第二次 409 + 回既有 job_id
#   ② done_pages 由**库内复算**得出（手工插假 job_pages 行验证；非内存计数器）
#   ③ E5 缺失清单形状与计数 = 副本库独立复算
#   ④ 迁移脚本连跑两次 ⇒ 幂等（第二次 applied=0、schema 指纹不变、不重复建表）
#   ⑤ 正式 yinpu.db md5 前后一致（另有 prod 安全闸用例）
#
# 纪律：**严禁 pkill / killall 宽匹配**；停服务只用本脚本记录的精确 PID。
# 规范：../docs/feicui.spec.md v1.1（§3 E1/E2/E5、§3.2 S-1/S-2/S-4/S-5/S-6、§4.1 D-1/D-2）
# =============================================================================
set -uo pipefail

SERVER_DIR="/Users/kevin/bistro/shu/feicui/server"
FEICUI_DIR="/Users/kevin/bistro/shu/feicui"
PROD_DB="$FEICUI_DIR/yinpu.db"
EV="$SERVER_DIR/selftest/evidence"
PY="$SERVER_DIR/.venv/bin/python"
PORT="${FEICUI_SELFTEST_PORT:-5196}"
BASE="http://127.0.0.1:$PORT"
TMPDB="$EV/selftest.db"
PDF="$FEICUI_DIR/tmp.pdf"
PAGE_FROM=13
PAGE_TO=19

FAILS=0
note() { printf '\n=== %s ===\n' "$*"; }
ok()   { printf '  [PASS] %s\n' "$*"; }
bad()  { printf '  [FAIL] %s\n' "$*"; FAILS=$((FAILS+1)); }
chk()  { # chk <条件命令...> <描述>
  if eval "$1" >/dev/null 2>&1; then ok "$2"; else bad "$2"; fi
}

mkdir -p "$EV"
: > "$EV/run_1a.txt"
echo "时点（Asia/Shanghai）: $(date '+%Y-%m-%d %H:%M:%S %z')" | tee -a "$EV/run_1a.txt"

# ---------------------------------------------------------------- 0 前置
note "0 前置：端口空闲检查（不得冒占他人端口；PORTS.md 制度 c）"
lsof -nP -iTCP:"$PORT" -sTCP:LISTEN > "$EV/00_port_before.txt" 2>&1 || true
if [ -s "$EV/00_port_before.txt" ]; then
  bad "$PORT 已被占用，脚本中止（不 kill 任何进程）"
  cat "$EV/00_port_before.txt"
  exit 9
fi
ok "端口 $PORT 无监听"

note "0b 正式库 md5（前）"
md5 "$PROD_DB" | tee "$EV/01_prod_db_md5_before.txt"
stat -f 'size=%z mtime=%Sm inode=%i' "$PROD_DB" | tee -a "$EV/01_prod_db_md5_before.txt"

note "0c 主 venv 快照（证明未装/未改任何依赖；尤其 OCR 栈）"
"$FEICUI_DIR/venv/bin/python" -m pip freeze > "$EV/02_main_venv_freeze.txt" 2>&1
wc -l < "$EV/02_main_venv_freeze.txt" | sed 's/^/  main venv 依赖行数=/' | tee -a "$EV/run_1a.txt"
grep -Ei '^(fastapi|uvicorn|streamlit|paddleocr|paddlepaddle|pymupdf|numpy|opencv-python)==' \
  "$EV/02_main_venv_freeze.txt" | tee "$EV/02_main_venv_key_versions.txt"
chk "! grep -qi '^fastapi==' '$EV/02_main_venv_freeze.txt'" "主 venv 中不存在 fastapi（未被污染）"

# ---------------------------------------------------------------- 1 临时副本
note "1 建立临时副本库（唯一真源只读复制）"
rm -f "$TMPDB" "$TMPDB-wal" "$TMPDB-shm"
rm -f "$EV"/state_*.db
cp "$PROD_DB" "$TMPDB"
md5 "$TMPDB" | tee "$EV/03_copy_md5.txt"
chk "[ \"\$(md5 -q '$PROD_DB')\" = \"\$(md5 -q '$TMPDB')\" ]" "副本与正式库逐字节一致（cp 未改源）"

# ---------------------------------------------------------------- 2 迁移幂等
note "2 迁移入口：连跑两次（幂等）"
FEICUI_DB="$TMPDB" "$PY" -m app.migrations > "$EV/10_migrate_run1.txt" 2>&1; R1=$?
FEICUI_DB="$TMPDB" "$PY" -m app.migrations > "$EV/11_migrate_run2.txt" 2>&1; R2=$?
cat "$EV/10_migrate_run1.txt"; echo "--- run2 ---"; cat "$EV/11_migrate_run2.txt"
chk "[ $R1 -eq 0 ]" "第一次迁移 exit=0"
chk "[ $R2 -eq 0 ]" "第二次迁移 exit=0（不报错）"
FP1=$(sed -n 's/^schema_sha256= //p' "$EV/10_migrate_run1.txt")
FP2=$(sed -n 's/^schema_sha256= //p' "$EV/11_migrate_run2.txt")
AP1=$(sed -n 's/^applied *= *//p' "$EV/10_migrate_run1.txt")
AP2=$(sed -n 's/^applied *= *//p' "$EV/11_migrate_run2.txt")
SK2=$(sed -n 's/^skipped *= *//p' "$EV/11_migrate_run2.txt")
echo "fingerprint run1=$FP1 run2=$FP2 applied run1=$AP1 run2=$AP2 skipped run2=$SK2" \
  | tee "$EV/12_migrate_idempotency.txt"
chk "[ -n \"$FP1\" ] && [ \"$FP1\" = \"$FP2\" ]" "两次迁移后 sqlite_master 指纹一致（未重复建表）"
chk "[ \"$AP1\" = '2' ]" "第一次 applied=2（两条迁移各落一次）"
chk "[ \"$AP2\" = '0' ]" "第二次 applied=0（全部跳过）"
chk "[ \"$SK2\" = '2' ]" "第二次 skipped=2（未重复建表/建索引）"
FEICUI_DB="$TMPDB" "$PY" -m app.migrations --status > "$EV/13_migrate_status.txt" 2>&1
cat "$EV/13_migrate_status.txt" | tee -a "$EV/12_migrate_idempotency.txt"

note "2b 安全闸：默认不得对正式库执行迁移"
"$PY" -m app.migrations > "$EV/14_prod_guard.txt" 2>&1; RG=$?
echo "exit=$RG" >> "$EV/14_prod_guard.txt"
cat "$EV/14_prod_guard.txt"
chk "[ $RG -eq 3 ]" "正式库迁移被拒（exit=3）"

# ---------------------------------------------------------------- 3 启服务
note "3 启动 API（精确 PID；测完放开端口）"
cd "$SERVER_DIR" || exit 9
FEICUI_DB="$TMPDB" FEICUI_API_PORT="$PORT" "$PY" -m app.main > "$EV/20_server.log" 2>&1 &
SRV_PID=$!
echo "$SRV_PID" > "$EV/20_server_pid.txt"
echo "SRV_PID=$SRV_PID" | tee -a "$EV/run_1a.txt"

READY=0
i=0
while [ $i -lt 80 ]; do
  if curl -sf "$BASE/api/health" -o "$EV/21_health.json" 2>/dev/null; then READY=1; break; fi
  sleep 0.5
  i=$((i+1))
done
if [ $READY -ne 1 ]; then
  bad "服务未就绪（$BASE/api/health）"; cat "$EV/20_server.log"
  kill -TERM "$SRV_PID" 2>/dev/null
  exit 9
fi
ok "服务就绪（$(( i / 2 )) s 内）"
ps -o pid,lstart,command -p "$SRV_PID" | tee "$EV/22_server_ps.txt"
lsof -nP -iTCP:"$PORT" -sTCP:LISTEN | tee "$EV/23_port_after_start.txt"
"$PY" -m json.tool "$EV/21_health.json" | tee "$EV/21_health.pretty.json"

# ---------------------------------------------------------------- 4 E1
note "4 E1 建 job ×2（同书第二次必须 409 + 既有 job_id）"
CODE1=$(curl -s -o "$EV/30_e1_job1.json" -w '%{http_code}' -X POST "$BASE/api/jobs" \
  -H 'Content-Type: application/json' \
  -d "{\"pdf_path\":\"$PDF\",\"page_range\":[$PAGE_FROM,$PAGE_TO]}")
echo "POST #1 -> HTTP $CODE1" | tee -a "$EV/30_e1_job1.json.status"
echo "$CODE1" > "$EV/30_e1_job1.code"
"$PY" -m json.tool "$EV/30_e1_job1.json" | tee "$EV/30_e1_job1.pretty.json"
chk "[ \"$CODE1\" = '201' ]" "第一次建 job 返回 201"

CODE2=$(curl -s -o "$EV/31_e1_job2.json" -w '%{http_code}' -X POST "$BASE/api/jobs" \
  -H 'Content-Type: application/json' \
  -d "{\"pdf_path\":\"$PDF\",\"page_range\":[$PAGE_FROM,$PAGE_TO]}")
echo "$CODE2" > "$EV/31_e1_job2.code"
ps -o pid,lstart,command -p "$SRV_PID" >/dev/null 2>&1 && pid_alive=yes || pid_alive=no
"$PY" -m json.tool "$EV/31_e1_job2.json" | tee "$EV/31_e1_job2.pretty.json"
chk "[ \"$CODE2\" = '409' ]" "第二次建 job 返回 409（不得静默起第二个）"
JOB1=$(grep -o '"job_id":"[^"]*"' "$EV/30_e1_job1.json" | head -1 | cut -d'"' -f4)
JOB2=$(grep -o '"job_id":"[^"]*"' "$EV/31_e1_job2.json" | head -1 | cut -d'"' -f4)
echo "job_id#1=$JOB1  job_id#2(409 体内)=$JOB2" | tee "$EV/32_job_ids.txt"
chk "[ -n \"$JOB1\" ] && [ \"$JOB1\" = \"$JOB2\" ]" "409 响应体回的是**既有** job_id"

CODE3=$(curl -s -o "$EV/33_e1_badpdf.json" -w '%{http_code}' -X POST "$BASE/api/jobs" \
  -H 'Content-Type: application/json' -d '{"pdf_path":"/no/such/book.pdf"}')
echo "$CODE3" > "$EV/33_e1_badpdf.code"
chk "[ \"$CODE3\" = '400' ]" "pdf_path 不存在 ⇒ 400（S-6 参数非法）"

# ---------------------------------------------------------------- 5 E2 复算
note "5 E2 进度＝库内复算（手工插假 job_pages 行）"
DBQ() { "$PY" - "$TMPDB" "$@" <<'PYEOF'
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
for row in conn.execute(sys.argv[2], tuple(sys.argv[3:])):
    print("|".join("" if v is None else str(v) for v in row))
PYEOF
}

# 快照：用 SQLite backup API（WAL 感知）在**响应同刻**冻结副本库，
# 供 verify_1a.py 做「同一时刻」的独立复算（避免事后读取被后续步骤改动）。
snap() { "$PY" - "$TMPDB" "$EV/state_$1.db" <<'PYEOF'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1]); dst = sqlite3.connect(sys.argv[2])
src.backup(dst); dst.close(); src.close()
print(f"snapshot -> {sys.argv[2]}")
PYEOF
}

# 5a 建 job 后的初态
curl -s "$BASE/api/jobs/$JOB1" -o "$EV/40_e2_initial.json" -w '%{http_code}' > "$EV/40_e2_initial.code"
snap 40
"$PY" -m json.tool "$EV/40_e2_initial.json" | tee "$EV/40_e2_initial.pretty.json"

# 5b 手工推进：2 页 DONE / 1 页 FAILED / 1 页 RUNNING；并把 jobs.state 强行写 DONE（验 S-2 下行）
"$PY" - "$TMPDB" "$JOB1" <<'PYEOF'
import sqlite3, sys
db, job = sys.argv[1], sys.argv[2]
conn = sqlite3.connect(db)
conn.execute("UPDATE job_pages SET state='DONE', detected=10, inserted=10, updated=0, skipped=0, ocr_empty=7, finished_at='2026-09-20T12:00:00+08:00' WHERE job_id=? AND page IN (13,14)", (job,))
conn.execute("UPDATE job_pages SET state='FAILED', detected=3, error='selftest fake failure' WHERE job_id=? AND page=15", (job,))
conn.execute("UPDATE job_pages SET state='RUNNING', started_at='2026-09-20T12:00:01+08:00' WHERE job_id=? AND page=16", (job,))
conn.execute("UPDATE jobs SET state='DONE', started_at='2026-09-20T11:59:00+08:00' WHERE job_id=?", (job,))
conn.commit()
print("fake rows written")
PYEOF

curl -s "$BASE/api/jobs/$JOB1" -o "$EV/41_e2_after_fake.json" -w '%{http_code}' > "$EV/41_e2_after_fake.code"
snap 41
"$PY" -m json.tool "$EV/41_e2_after_fake.json" | tee "$EV/41_e2_after_fake.pretty.json"
note "5b 同刻库内独立复算（SQL）"
DBQ "SELECT COUNT(*) AS total, SUM(state='DONE') AS done, SUM(state='FAILED') AS failed FROM job_pages WHERE job_id='$JOB1'" || true
DBQ "SELECT GROUP_CONCAT(page) FROM job_pages WHERE job_id='$JOB1' AND state='FAILED'" || true

# 5c 再推进一页 ⇒ 复算值必须跟着变（证明不是估算/计数器）
"$PY" - "$TMPDB" "$JOB1" <<'PYEOF'
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
conn.execute("UPDATE job_pages SET state='DONE', detected=5, inserted=5, ocr_empty=5 WHERE job_id=? AND page=16", (sys.argv[2],))
conn.commit()
PYEOF
curl -s "$BASE/api/jobs/$JOB1" -o "$EV/42_e2_after_more.json" -w '%{http_code}' > "$EV/42_e2_after_more.code"
snap 42
"$PY" -m json.tool "$EV/42_e2_after_more.json" | tee "$EV/42_e2_after_more.pretty.json"

CODE404=$(curl -s -o "$EV/43_e2_unknown.json" -w '%{http_code}' "$BASE/api/jobs/job-does-not-exist")
echo "$CODE404" > "$EV/43_e2_unknown.code"
chk "[ \"$CODE404\" = '404' ]" "未知 job_id ⇒ 404"

# ---------------------------------------------------------------- 6 E5
note "6 E5 缺失清单（形状 + 计数对账）"
snap 50
curl -s "$BASE/api/jobs/$JOB1/missing?kind=image" -o "$EV/50_e5_image.json" -w '%{http_code}' > "$EV/50_e5_image.code"
curl -s "$BASE/api/jobs/$JOB1/missing?kind=text"  -o "$EV/51_e5_text.json"  -w '%{http_code}' > "$EV/51_e5_text.code"
curl -sD "$EV/52_e5_headers.txt" "$BASE/api/jobs/$JOB1/missing?kind=image" -o /dev/null
"$PY" -m json.tool "$EV/50_e5_image.json" | head -20
"$PY" -m json.tool "$EV/51_e5_text.json" | head -20
grep -i '^x-feicui-scope' "$EV/52_e5_headers.txt" | tee "$EV/52_e5_scope.txt"

note "6b 向副本库插入 2 条假 stamps 行（影像文件不存在）以验非空清单"
"$PY" - "$TMPDB" <<'PYEOF'
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
rows = conn.execute("SELECT pdf_name, page FROM stamps WHERE pdf_name LIKE 'tmp.pdf' ORDER BY page LIMIT 1").fetchone()
pdf_name, page = rows[0], rows[1]
conn.executemany(
    "INSERT OR REPLACE INTO stamps(id, pdf_name, page, idx, text, img_path, x1,y1,x2,y2) VALUES (?,?,?,?,?,?,?,?,?,?)",
    [
        (900001, pdf_name, page, 900, None, "output/__selftest_missing__/p0001_900.webp", 0,0,1,1),
        (900002, pdf_name, page, 901, "fake text", "output/__selftest_missing__/p0001_901.webp", 0,0,1,1),
    ],
)
conn.commit()
print("fake stamps rows written:", pdf_name, page)
PYEOF
curl -s "$BASE/api/jobs/$JOB1/missing?kind=image" -o "$EV/53_e5_image_after_fake.json" -w '%{http_code}' > "$EV/53_e5_image_after_fake.code"
snap 53
"$PY" -m json.tool "$EV/53_e5_image_after_fake.json" | tee "$EV/53_e5_image_after_fake.pretty.json"

CODEBADKIND=$(curl -s -o "$EV/54_e5_badkind.json" -w '%{http_code}' "$BASE/api/jobs/$JOB1/missing")
echo "$CODEBADKIND" > "$EV/54_e5_badkind.code"
chk "[ \"$CODEBADKIND\" = '400' ]" "kind 缺失 ⇒ 400（S-6 参数非法）"

note "6c 1b 端点必须不存在（E3/E4 未按本单验收）"
CODE_E3=$(curl -s -o "$EV/55_e3_unimplemented.json" -w '%{http_code}' "$BASE/api/jobs/$JOB1/stamps?page=1&limit=2")
CODE_E4=$(curl -s -o "$EV/56_e4_unimplemented.json" -w '%{http_code}' -X POST "$BASE/api/jobs/$JOB1/export" -H 'Content-Type: application/json' -d '{}')
echo "$CODE_E3" > "$EV/55_e3_unimplemented.code"; echo "$CODE_E4" > "$EV/56_e4_unimplemented.code"
echo "E3 -> HTTP $CODE_E3 ; E4 -> HTTP $CODE_E4" | tee "$EV/57_1b_endpoints.txt"

# ---------------------------------------------------------------- 6d E1 派生 total_pages
note "6d E1 无 page_range ⇒ total_pages 由 PDF 页数派生（PyMuPDF 走 feicui venv 回退路径）"
PDF2="/Users/kevin/Downloads/秦汉印典 上海书画 金怀英  1997 ok.pdf"
if [ -f "$PDF2" ]; then
  "$FEICUI_DIR/venv/bin/python" -c "import fitz,sys;print(fitz.open(sys.argv[1]).page_count)" "$PDF2" \
    | grep -E '^[0-9]+$' | tail -1 > "$EV/59_pdf2_pages.txt"
  PAGES2=$(cat "$EV/59_pdf2_pages.txt")
  echo "独立读数：$PDF2 -> $PAGES2 页" | tee "$EV/59_pdf2_pages.note"
  CODE4=$(curl -s -o "$EV/58_e1_norange.json" -w '%{http_code}' -X POST "$BASE/api/jobs" \
    -H 'Content-Type: application/json' --data-binary "@-" <<JSONEOF
{"pdf_path":"$PDF2"}
JSONEOF
  )
  echo "$CODE4" > "$EV/58_e1_norange.code"
  snap 58
  "$PY" -m json.tool "$EV/58_e1_norange.json" | tee "$EV/58_e1_norange.pretty.json"
  chk "[ \"$CODE4\" = '201' ]" "无 page_range 建 job = 201（total_pages 由 PDF 派生）"
else
  echo "SKIP：$PDF2 不存在，未做无 page_range 用例" | tee "$EV/59_pdf2_pages.note"
fi

note "6e E1 必填不可派生 ⇒ 422（S-6）"
# 注意：PyMuPDF 对**垃圾字节**是宽容的（实测 `fitz.open('not a pdf')` ⇒ **1 页**，见 5B 证据），
# 故 422 用例要用**不可读文件**（chmod 000）才能可靠命中「读不出页数」。
printf 'not a pdf' > "$EV/fake_unreadable.bin"; chmod 000 "$EV/fake_unreadable.bin"
CODE5=$(curl -s -o "$EV/5A_e1_422.json" -w '%{http_code}' -X POST "$BASE/api/jobs" \
  -H 'Content-Type: application/json' --data-binary "@-" <<JSONEOF
{"pdf_path":"$EV/fake_unreadable.bin"}
JSONEOF
)
chmod 644 "$EV/fake_unreadable.bin"
echo "$CODE5" > "$EV/5A_e1_422.code"
"$PY" -m json.tool "$EV/5A_e1_422.json" | tee "$EV/5A_e1_422.pretty.json"
chk "[ \"$CODE5\" = '422' ]" "读不出页数且未给 page_range ⇒ 422（S-6 必填不可派生）"

note "6f 附：PyMuPDF 对非 PDF 输入的宽容度实测（解释用例选择，见 REPORT_1a.md G-6）"
printf 'not a pdf' > "$EV/fake_garbage.bin"
"$FEICUI_DIR/venv/bin/python" -c "
import fitz,sys
try:
    d=fitz.open(sys.argv[1]); print('fitz.open(垃圾字节) -> OK, page_count =', d.page_count)
except Exception as e:
    print('fitz.open(垃圾字节) -> FAILED', type(e).__name__, e)
" "$EV/fake_garbage.bin" | tee "$EV/5B_pymupdf_lenient.txt"

# ---------------------------------------------------------------- 7 停服务
note "7 停服务（精确 PID，TERM；测完放开 5196）"
kill -TERM "$SRV_PID" 2>/dev/null
WAIT_TICKS=0
# 等待被 TERM 的子进程结束并回收（避免僵尸态误判）；同时以端口释放为准绳
while [ $WAIT_TICKS -lt 40 ]; do
  if ! lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then break; fi
  sleep 0.5
  WAIT_TICKS=$((WAIT_TICKS+1))
done
wait "$SRV_PID" 2>/dev/null
WAIT_RC=$?
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  bad "服务仍在监听 $PORT（PID ${SRV_PID}）"
else
  ok "服务已退出、端口已释放（PID ${SRV_PID}，wait_rc=${WAIT_RC}）"
fi
lsof -nP -iTCP:"$PORT" -sTCP:LISTEN > "$EV/60_port_after_stop.txt" 2>&1 || true
chk "[ ! -s '$EV/60_port_after_stop.txt' ]" "端口 $PORT 已释放"
echo "SRV_PID=$SRV_PID wait_ticks=$WAIT_TICKS wait_rc=$WAIT_RC" >> "$EV/60_port_after_stop.txt"

# ---------------------------------------------------------------- 8 判定
note "8 复算与断言（副本库 + 落盘响应）"
"$PY" "$SERVER_DIR/selftest/verify_1a.py" "$EV" "$JOB1" | tee "$EV/70_verify.txt"
VRC=${PIPESTATUS[0]}
if [ "$VRC" -ne 0 ]; then bad "verify_1a.py 断言未全过（exit=${VRC}）"; else ok "verify_1a.py 全部断言通过"; fi

note "9 正式库 md5（后）+ 未变判定"
md5 "$PROD_DB" | tee "$EV/80_prod_db_md5_after.txt"
stat -f 'size=%z mtime=%Sm inode=%i' "$PROD_DB" | tee -a "$EV/80_prod_db_md5_after.txt"
if diff <(grep -v 'mtime' "$EV/01_prod_db_md5_before.txt") <(grep -v 'mtime' "$EV/80_prod_db_md5_after.txt") >/dev/null; then
  ok "正式 yinpu.db md5/size/inode 前后一致（未被写入）"
else
  bad "正式 yinpu.db 发生变化！"
fi
ls -l "$PROD_DB"* | tee "$EV/81_prod_db_files.txt"
chk "[ ! -e '$PROD_DB-wal' ] && [ ! -e '$PROD_DB-shm' ]" "正式库旁无 -wal / -shm 残留"

note "小结"
echo "FAILS=$FAILS" | tee "$EV/90_summary.txt"
if [ "$FAILS" -eq 0 ]; then echo "ALL PASS" | tee -a "$EV/90_summary.txt"; else echo "HAS FAILURES" | tee -a "$EV/90_summary.txt"; fi
exit "$FAILS"
