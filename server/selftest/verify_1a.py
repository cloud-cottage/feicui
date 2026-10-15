#!/usr/bin/env python3
"""阶段 1a 自测**断言器**（Kong）——读 `selftest/evidence/` 落盘的响应 + **同刻库快照**独立复算。

用法： `server/.venv/bin/python selftest/verify_1a.py <evidence_dir> <job_id>`

原则：
  * **不 import 被测应用代码**——只读 JSON 与快照库，期望值一律由 SQL / `os.path.exists` **独立复算**；
  * 每个 API 响应都配一份**响应同刻**的库快照（`state_<编号>.db`，SQLite backup API 冻结、WAL 感知），
    避免「事后读库」与被测步骤之间的时序错配（§7 AC-05 要求「E2 响应快照 + 同刻库内复算**并排给出**」）。

任一断言失败 ⇒ 退出码非 0。
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

EV = Path(sys.argv[1])
JOB1 = sys.argv[2]
ROOT = Path("/Users/kevin/bistro/feicui")  # §4.2：影像相对路径的解析根

FAILS: list[str] = []


def snap(name: str) -> str:
    p = EV / f"state_{name}.db"
    if not p.is_file():
        FAILS.append(f"缺少同刻快照 {p}")
    return str(p)


def read_json(name: str):
    p = EV / name
    if not p.is_file():
        FAILS.append(f"缺少证据文件 {p}")
        return None
    raw = p.read_text(encoding="utf-8").strip()
    if not raw:
        FAILS.append(f"证据文件为空 {p}")
        return None
    try:
        return json.loads(raw)
    except Exception as exc:
        FAILS.append(f"{p} 不是合法 JSON：{exc}")
        return None


def code(name: str) -> str:
    return (EV / name).read_text().strip() if (EV / name).is_file() else ""


def check(cond: bool, label: str, detail: str = "") -> None:
    if cond:
        print(f"  [PASS] {label}")
    else:
        print(f"  [FAIL] {label}{' :: ' + detail if detail else ''}")
        FAILS.append(label)


def q(db: str, sql: str, params: tuple = ()) -> list[tuple]:
    conn = sqlite3.connect(db)
    try:
        return list(conn.execute(sql, params))
    finally:
        conn.close()


def one(db: str, sql: str, params: tuple = ()):
    rows = q(db, sql, params)
    return rows[0][0] if rows else None


def scope(db: str, job_id: str) -> tuple[str, int, int]:
    """独立复算 E5 的判定范围：书名 + 该 job 的页区间下上界。"""
    pdf_name = one(db, "SELECT pdf_name FROM jobs WHERE job_id=?", (job_id,))
    lo = one(db, "SELECT MIN(page) FROM job_pages WHERE job_id=?", (job_id,))
    hi = one(db, "SELECT MAX(page) FROM job_pages WHERE job_id=?", (job_id,))
    return pdf_name, int(lo), int(hi)


def missing_recompute(db: str, kind: str) -> list[tuple]:
    pdf_name, lo, hi = scope(db, JOB1)
    rows = q(
        db,
        "SELECT page,idx,img_path,text FROM stamps WHERE pdf_name=? AND page BETWEEN ? AND ? ORDER BY page,idx",
        (pdf_name, lo, hi),
    )
    if kind == "image":
        return [
            (p, i, path)
            for (p, i, path, _text) in rows
            if path is None or str(path).strip() == "" or not os.path.exists(os.path.join(str(ROOT), str(path)))
        ]
    return [(p, i) for (p, i, _path, text) in rows if text is None or str(text).strip() == ""]


E2_KEYS = {
    "job_id",
    "state",
    "total_pages",
    "done_pages",
    "failed_pages",
    "cursor",
    "counters",
    "started_at",
    "updated_at",
}
COUNTER_KEYS = {"detected", "inserted", "updated", "skipped", "ocr_empty"}

# ---------------------------------------------------------------- E1
print("== E1 形状与状态码（§3.1 E1 / §3.2 S-5 / S-6） ==")
db40 = snap("40")
e1 = read_json("30_e1_job1.json") or {}
check(code("30_e1_job1.code") == "201", "POST /api/jobs 第一次 = 201", code("30_e1_job1.code"))
check(set(e1) == {"job_id", "state", "total_pages", "created_at"}, "E1 201 形状 = 4 字段", str(sorted(e1)))
check(e1.get("state") == "QUEUED", "E1 入队语义 ⇒ state=QUEUED", str(e1.get("state")))
check(e1.get("total_pages") == 7, "E1 total_pages = page_range 宽度 7", str(e1.get("total_pages")))
check(e1.get("job_id") == JOB1, "E1 job_id 与脚本记录一致")
check(
    one(db40, "SELECT COUNT(*) FROM job_pages WHERE job_id=?", (JOB1,)) == 7,
    "入队即落 7 行 job_pages（页级断点游标落盘，§2.3）",
)

e1b = read_json("31_e1_job2.json") or {}
check(code("31_e1_job2.code") == "409", "同书第二次 = 409", code("31_e1_job2.code"))
check(e1b.get("job_id") == JOB1, "409 响应体回既有 job_id（不得静默起第二个）", str(e1b.get("job_id")))
check(one(db40, "SELECT COUNT(*) FROM jobs") == 1, "库内 job 行数 = 1（未起第二个）", str(one(db40, "SELECT COUNT(*) FROM jobs")))
check(code("33_e1_badpdf.code") == "400", "pdf_path 不存在 ⇒ 400（S-6 参数非法）", code("33_e1_badpdf.code"))

# ---------------------------------------------------------------- E2
print("== E2 形状与「库内复算」（§3.2 S-1 / S-2） ==")
init = read_json("40_e2_initial.json") or {}
check(set(init) == E2_KEYS, "E2 形状 = §3.1 E2 逐字段（9 字段）", str(sorted(init)))
check(set(init.get("cursor") or {}) == {"chunk_lo", "chunk_hi"}, "E2 cursor = {chunk_lo,chunk_hi}")
check(set(init.get("counters") or {}) == COUNTER_KEYS, "E2 counters = 5 项", str(sorted(init.get("counters") or {})))
check(init.get("done_pages") == 0 and init.get("failed_pages") == [], "初态 done_pages=0 / failed_pages=[]")
check(
    init.get("total_pages") == one(db40, "SELECT COUNT(*) FROM job_pages WHERE job_id=?", (JOB1,)),
    "初态 total_pages = 库内 job_pages 行数",
)

db41 = snap("41")
after = read_json("41_e2_after_fake.json") or {}
done_sql = one(db41, "SELECT COUNT(*) FROM job_pages WHERE job_id=? AND state='DONE'", (JOB1,))
failed_sql = [r[0] for r in q(db41, "SELECT page FROM job_pages WHERE job_id=? AND state='FAILED' ORDER BY page", (JOB1,))]
sums = q(
    db41,
    """SELECT COALESCE(SUM(detected),0),COALESCE(SUM(inserted),0),COALESCE(SUM(updated),0),
              COALESCE(SUM(skipped),0),COALESCE(SUM(ocr_empty),0)
         FROM job_pages WHERE job_id=?""",
    (JOB1,),
)[0]
print(f"  同刻库内复算：total={one(db41, 'SELECT COUNT(*) FROM job_pages WHERE job_id=?', (JOB1,))} "
      f"done={done_sql} failed={failed_sql} counters={list(sums)}")
check(after.get("done_pages") == done_sql, f"done_pages 由库内复算（API={after.get('done_pages')} / SQL={done_sql}）")
check(after.get("failed_pages") == failed_sql, f"failed_pages 由库内复算（API={after.get('failed_pages')} / SQL={failed_sql}）")
check(after.get("total_pages") == one(db41, "SELECT COUNT(*) FROM job_pages WHERE job_id=?", (JOB1,)), "total_pages 由库内复算")
check(len(after.get("failed_pages") or []) > 0, "样本确有 failed_pages（非空才能验 S-2）")
check(after.get("state") != "DONE", "S-2：有 failed_pages 时 state 不得为 DONE", str(after.get("state")))
check(after.get("state") == "FAILED_PARTIAL", "S-2：库内 state=DONE 被下行报为 FAILED_PARTIAL", str(after.get("state")))
check(list((after.get("counters") or {}).values()) == list(sums), f"counters 由库内 SUM() 复算（API={list((after.get('counters') or {}).values())} / SQL={list(sums)}）")
check(set(after.get("cursor") or {}) == {"chunk_lo", "chunk_hi"}, "cursor 形状合法")

db42 = snap("42")
more = read_json("42_e2_after_more.json") or {}
done_sql2 = one(db42, "SELECT COUNT(*) FROM job_pages WHERE job_id=? AND state='DONE'", (JOB1,))
check(more.get("done_pages") == done_sql2, f"再推一页后 done_pages 跟随复算变化（API={more.get('done_pages')} / SQL={done_sql2}）")
check(more.get("done_pages") == done_sql + 1, "done_pages 增量 = 库内 DONE 行增量（非估算 / 非计时器）")
check(more.get("failed_pages") == after.get("failed_pages"), "failed_pages 不受其它页推进影响（仍 = 库内 FAILED 集）")
check(code("43_e2_unknown.code") == "404", "未知 job_id ⇒ 404", code("43_e2_unknown.code"))

# ---------------------------------------------------------------- E5
print("== E5 形状与计数对账（§3.1 E5 / AC-06 / AC-07） ==")
db50 = snap("50")
db53 = snap("53")
pdf_name, lo, hi = scope(db50, JOB1)
print(f"  独立复算范围：pdf_name={pdf_name!r} pages=[{lo},{hi}] root={ROOT}")

img0 = read_json("50_e5_image.json") or {}
check(set(img0) == {"kind", "count", "items"}, "E5 形状 = {kind,count,items}", str(sorted(img0)))
check(img0.get("kind") == "image", "E5 kind 回显 image")
exp_missing0 = missing_recompute(db50, "image")
check(
    img0.get("count") == len(exp_missing0),
    f"E5 image count = 独立复算 os.path.exists 缺失数（API={img0.get('count')} / 复算={len(exp_missing0)}）",
)
check(len(img0.get("items") or []) == img0.get("count"), "items 长度 = count")
item_keys = set((img0.get("items") or [{}])[0]) if img0.get("items") else {"pdf_name", "page", "idx", "reason"}
check(item_keys <= {"pdf_name", "page", "idx", "img_path", "reason"}, "E5 item 字段 ⊆ 规范字段集", str(sorted(item_keys)))

txt0 = read_json("51_e5_text.json") or {}
exp_text = len(missing_recompute(db50, "text"))
check(txt0.get("kind") == "text", "E5 kind 回显 text")
check(txt0.get("count") == exp_text, f"E5 text count = 独立复算 SQL（API={txt0.get('count')} / 复算={exp_text}）")
check(len(txt0.get("items") or []) == txt0.get("count"), "text items 长度 = count")
global_text = one(db50, "SELECT COUNT(*) FROM stamps WHERE text IS NULL OR trim(text)=''")
print(
    "  （附）AC-07 的 SQL 全文＝**全表口径（无书名过滤）**"
    f"＝{global_text}，本次 job 区间口径＝{exp_text} ⇒ 两者不等是口径差异，见 REPORT_1a.md 规范缺口 G-3"
)

img1 = read_json("53_e5_image_after_fake.json") or {}
exp_missing1 = missing_recompute(db53, "image")
check(
    img1.get("count") == len(exp_missing1),
    f"插入 2 条假缺失行后 count 跟随复算（API={img1.get('count')} / 复算={len(exp_missing1)}）",
)
check(img1.get("count") == img0.get("count") + 2, "count 增量 = 2（与插入的假行数一致）")
check(any(i.get("reason") == "file_missing" for i in (img1.get("items") or [])), "假缺失行 reason=file_missing")
scope_hdr = (EV / "52_e5_scope.txt").read_text().strip() if (EV / "52_e5_scope.txt").is_file() else ""
check(f"page_from={lo};page_to={hi}" in scope_hdr, "响应头 x-feicui-scope 与库内范围一致", scope_hdr)
check(code("54_e5_badkind.code") == "400", "kind 缺失 ⇒ 400（S-6 参数非法）", code("54_e5_badkind.code"))

# ---------------------------------------------------------------- E1 派生 / 422
print("== E1 total_pages 派生 / 422（§3.2 S-6） ==")
p2 = EV / "59_pdf2_pages.txt"
if p2.is_file() and p2.read_text().strip():
    db58 = snap("58")
    e1c = read_json("58_e1_norange.json") or {}
    exp_pages = int(p2.read_text().strip())
    check(code("58_e1_norange.code") == "201", "无 page_range 建 job = 201", code("58_e1_norange.code"))
    check(
        e1c.get("total_pages") == exp_pages,
        f"total_pages = 独立读数 PDF 页数（API={e1c.get('total_pages')} / 独立={exp_pages}）",
    )
    check(
        one(db58, "SELECT COUNT(*) FROM job_pages WHERE job_id=?", (e1c.get("job_id"),)) == exp_pages,
        "入队落 job_pages 行数 = PDF 页数",
    )
else:
    print("  [SKIP] 无 page_range 用例未执行（第二本书 PDF 不在位）")
check(code("5A_e1_422.code") == "422", "读不出页数且未给 page_range ⇒ 422", code("5A_e1_422.code"))
check(
    "total_pages" in json.dumps(read_json("5A_e1_422.json") or {}, ensure_ascii=False),
    "422 响应体指明不可派生的字段名 total_pages",
)

# ---------------------------------------------------------------- 1b 边界
print("== 1b 端点必须不存在（E3/E4 未按本单验收） ==")
check(code("55_e3_unimplemented.code") == "404", "E3 未注册（404）", code("55_e3_unimplemented.code"))
check(code("56_e4_unimplemented.code") == "404", "E4 未注册（404）", code("56_e4_unimplemented.code"))

print()
if FAILS:
    print(f"VERIFY FAILED：{len(FAILS)} 条未过")
    for f in FAILS:
        print("   -", f)
    sys.exit(1)
print("VERIFY OK：全部断言通过")
sys.exit(0)
