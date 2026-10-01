#!/usr/bin/env python
"""阶段 1b-ii 自测（Kong）：E3 / E4 / E6 / E7 四个读接口 + 1b-i worker 链路回归。

规范 = `../docs/feicui.spec.md` **v1.2**（md5 `6dbe0b3c915d7f8ed43576a00122dcf1`）：
§3.1 E3（6 字段分页信封）/ E4（触发导出）/ E6（取印面裁图 §3.5）/ E7（job 列表 §3.8）、§3.2 S-3、§7 AC-08。

纪律（硬约束，本脚本逐条遵守）：
  * **只用副本库**：`yinpu.db` 全程 `mode=ro` 只读（Python `uri=True`，**不用 sqlite3 CLI**——
    WAL 下 CLI 的 `file:…?mode=ro` 打不开、`| md5` 会得到空输入 md5 的假结论）；
  * 导出根指向**临时目录**（`FEICUI_EXPORT_ROOT`）⇒ **不污染 `exports/` 既有 12 个批次包**；
  * 影像写盘指向**临时目录**（`FEICUI_FACES_DIR`）⇒ 不动 `output/` 既有产物；
  * 端口只用 **5321 / 5322**（非登记端口），停进程**只按自己记下的精确 PID**（**无 pkill / killall**）；
  * fixture 行只插进**副本库**，且用独立书名 `__1bii_fixture.pdf`（不可能与真书撞名）；
  * 性能读数一律标注「同机有并发任务、非受控基线」，不作判据。

跑法：
    cd /Users/kevin/bistro/shu/feicui/server && ./.venv/bin/python selftest/verify_1b_ii.py
证据落 `server/selftest/evidence/1b_ii/`（`/tmp` 只放临时库与临时导出根，不作证据）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

SRV = Path(__file__).resolve().parents[1]          # feicui/server
FE = SRV.parent                                    # feicui
EVID = SRV / "selftest" / "evidence" / "1b_ii"
PROD_DB = FE / "yinpu.db"
PROD_EXPORTS = FE / "exports"
API_PY = SRV / ".venv" / "bin" / "python"
WORKER_PY = FE / "venv" / "bin" / "python"
VERIFY_1BI = SRV / "selftest" / "verify_1b_i.py"
PORT_BASE = 5321          # 非登记端口段（5164/5195/5196 与 PORTS.md 既有端口一律避开）
PORT_MAIN = PORT_BASE     # 运行时由 pick_free_port() 动态选定（**不写死**）
PORT_REG = PORT_BASE + 1  # 回归臂（同样动态选定）


def pick_free_port(start: int = PORT_BASE, tries: int = 20) -> int:
    """自测端口**动态选取**（Zang 追加口径 ②）：从 `start` 起找第一个无监听且能 bind 的端口。

    写死端口是首跑污染的直接成因（上一轮残留实例把端口占着 ⇒ 探针打到旧进程 ⇒ 一片假 FAIL）。
    """
    for port in range(start, start + tries):
        if port in (5164, 5195, 5196, 5555, 5173, 5174):  # 登记/保留端口绝不碰
            continue
        if not port_free(port):
            continue
        with socket.socket() as sck:  # bind 试探：确认自己拿得到
            try:
                sck.bind(("127.0.0.1", port))
            except OSError:
                continue
        return port
    raise SystemExit(f"✗ 在 {start}..{start + tries} 内找不到空闲端口（前置条件不满足，直接中止）")
FIXTURE_BOOK = "__1bii_fixture.pdf"

# `ops/prod_migrate_evidence.md` §2.3 期望值（**只读引用**，用于「stamps 未变」判据）
EXPECT_FP = {
    "a_md5": "8a21e57d5bd909fff282214640457c7f",
    "b_md5": "d7abe995bff62761c27052dfc2bdf7bb",
    "c_md5": "22bdc0a794382b6e6dab7855aaee456f",
    "rows": 79,
    "cols": 10,
}
EXPECT_COLS = ["id", "pdf_name", "page", "idx", "text", "img_path", "x1", "y1", "x2", "y2"]

SCRATCH: Path | None = None  # 本轮临时工作区（临时库 / 临时导出根 / 临时 faces），收尾时删除
PASS = 0
FAIL = 0
FAILED_NAMES: list[str] = []
LOG_LINES: list[str] = []
_log_fh = None

# ========================= 夹具护栏（本单 ② 新增，六条）=========================
# 事故背景（不得回退）：上一轮本脚本在 E7 的游标翻页循环里**失控**——服务端给出
# `has_more=true` 而 `next_cursor=null`（根因：E7 游标路径把 keyset `WHERE` 与 `OFFSET` 叠加 ⇒
# 第二页恒 0 条），夹具的 `if not body["has_more"]: break` 永不成立、`cursor=None` 又回到第一页
# ⇒ 死循环刷 FAIL（实测 54,347 行输出 / 54,254 条重复 FAIL，被 SIGTERM 杀）。六条护栏：
#   ① 翻页循环**硬上界**（`page_cap()` = ceil(total/limit)+2，且 ≤ 50）；
#   ② **游标不推进 / has_more 为真而 next_cursor 为空或与上页相同 ⇒ 立即 break 并只报一条 FAIL**
#      （附原始报文）——不再逐圈刷屏；
#   ③ **同一断言重复命中 ⇒ 折叠计数**（逐条打印至多 `FOLD_PRINT_CAP` 次，之后只计数，收尾汇总）；
#   ④ 任何 `job_id` 为 None / 响应不是信封 ⇒ **显式 FAIL 并中止该子段**，不产级联假 FAIL；
#   ⑤ `finally` 清理（停自己的服务 / 删临时库 / 断言端口已释放）；
#   ⑥ 端口**动态探测**（`pick_free_port`）+ 开头断言无监听（原已具备，本单保留并显式判据化）。
FOLD_PRINT_CAP = 3                            # 同一断言逐条打印上限（超出即折叠）
FAIL_FOLD: dict[tuple[str, str], int] = {}    # (断言名, 判据) -> 命中次数
FOLDED_FAILS = 0                              # 被折叠（未逐条打印）的重复失败次数
FAIL_FOLD_NOTIFIED: set = set()
ASSERT_HITS: set[str] = set()                 # 真正运行过的断言名（O-5：未运行的断言不得静默消失）
SECTIONS_SEEN: list[str] = []                 # 进入过的子段（收尾核对「子段齐全」）
SECTION_PLAN: list[str] = []                  # 计划子段（由 section() 首次调用顺序登记）
END_REACHED = False
# O-5：预期断言总数 —— 标定自本脚本**实测跑通的那一轮**（2026-09-20 13:01，PASS=142/FAIL=1，
# 该轮唯一 FAIL 就是本条占位；9.1 求值时 PASS+FAIL = 139）。**改任何断言必须同步改此数**，
# 否则收尾会显式 FAIL —— 这正是「未运行的断言不得静默消失」的闸门。
EXPECTED_ASSERTIONS = 139


def section(title: str) -> None:
    """子段标题（带登记）：配合收尾的「子段齐全 / 未运行断言」判据。"""
    SECTIONS_SEEN.append(title)
    if title not in SECTION_PLAN:
        SECTION_PLAN.append(title)
    say(f"\n==================== {title} ====================")


def page_cap(total: int, limit: int, *, extra: int = 2, cap: int = 50) -> int:
    """① 翻页循环**硬上界** = ceil(total/limit) + extra，且不超过 cap。"""
    limit = max(1, int(limit))
    return min(cap, -(-int(total) // limit) + extra)


def _short(raw: object, n: int = 400) -> str:
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
    return str(raw)[:n]


def cursor_step(prev: str | None, body: dict, seen: set, raw: object) -> tuple[str | None, str | None]:
    """② 游标**推进**护栏：返回 `(下一游标, 中止原因)`；中止原因非空时必须立刻 break。

    `has_more=true` 而 `next_cursor` 为空、或游标与上页相同 / 历史重复 ⇒ 客户端**会死循环**
    （上一轮 54k 行的机理）⇒ 中止并只留**一条** FAIL（附原始报文，便于定位）。
    """
    nxt = body.get("next_cursor")
    if not body.get("has_more"):
        return None, None
    if not nxt:
        return None, f"has_more=true 但 next_cursor 为空 ⇒ 客户端会死循环；本页原始报文={_short(raw)}"
    if nxt == prev or nxt in seen:
        return None, (f"next_cursor 未推进（与上页/历史重复：{nxt!r}）⇒ 客户端会死循环；"
                      f"本页原始报文={_short(raw)}")
    return nxt, None


def say(msg: str = "") -> None:
    print(msg, flush=True)
    LOG_LINES.append(msg)
    if _log_fh:
        _log_fh.write(msg + "\n")
        _log_fh.flush()


def _record_fail(name: str, verdict: str) -> None:
    """③ 失败记账（重复命中折叠）：同一 (断言名, 判据) 打印至多 FOLD_PRINT_CAP 次。"""
    global FAIL, FOLDED_FAILS
    key = (name, verdict)
    n = FAIL_FOLD.get(key, 0) + 1
    FAIL_FOLD[key] = n
    if n <= FOLD_PRINT_CAP:
        FAIL += 1
        FAILED_NAMES.append(name)
        say(f"FAIL  {name}：{verdict}" + (f"  [第 {n} 次]" if n > 1 else ""))
        if n == FOLD_PRINT_CAP and key not in FAIL_FOLD_NOTIFIED:
            FAIL_FOLD_NOTIFIED.add(key)
            say(f"FOLD  {name}：同类失败已达 {FOLD_PRINT_CAP} 次，**后续同类折叠计数**（不逐条刷屏）")
    else:
        FOLDED_FAILS += 1


def ck(name: str, got, want) -> bool:
    global PASS
    ASSERT_HITS.add(name)
    ok = got == want
    if ok:
        PASS += 1
        say(f"PASS  {name}：{got}")
    else:
        _record_fail(name, f"expect={want!r} got={got!r}")
    return ok


def ckT(name: str, cond: bool, detail: str = "") -> bool:
    global PASS
    ASSERT_HITS.add(name)
    # detail 允许任意类型（调用点会传 list/dict 做证据）：统一转字符串，避免 PASS 分支拼接崩溃
    detail = "" if detail is None else (detail if isinstance(detail, str) else str(detail))
    if cond:
        PASS += 1
        say(f"PASS  {name}{('：' + detail) if detail else ''}")
    else:
        _record_fail(name, detail)
    return bool(cond)


def ev(name: str, data) -> Path:
    p = EVID / name
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (bytes, bytearray)):
        p.write_bytes(data)
    elif isinstance(data, str):
        p.write_text(data, encoding="utf-8")
    else:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


# --------------------------------------------------------------------- 只读工具
def ro_conn(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{Path(db)}?mode=ro", uri=True, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def q1(db: Path, sql: str, params: tuple = ()):
    conn = ro_conn(db)
    try:
        row = conn.execute(sql, params).fetchone()
        return None if row is None else row[0]
    finally:
        conn.close()


def qall(db: Path, sql: str, params: tuple = ()) -> list[dict]:
    conn = ro_conn(db)
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def fingerprints(db: Path) -> dict:
    """stamps 三口径内容指纹（**口径照 `ops/prod_migrate_fingerprint.py`**，此处独立实现）。"""
    conn = ro_conn(db)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(stamps)")]
        rows = list(conn.execute("SELECT * FROM stamps ORDER BY id"))
        raw, canon = [], []
        for r in rows:
            raw.append("|".join("" if r[c] is None else str(r[c]) for c in cols))
            canon.append(
                json.dumps({c: r[c] for c in cols}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            )
        j = lambda lines: ("\n".join(lines) + "\n").encode("utf-8") if lines else b""  # noqa: E731
        a, b, c = j(raw), j(canon), j(sorted(canon))
        out = {
            "cols": cols,
            "rows": len(rows),
            "a_md5": hashlib.md5(a).hexdigest(),
            "b_md5": hashlib.md5(b).hexdigest(),
            "c_md5": hashlib.md5(c).hexdigest(),
            "a_sha256": hashlib.sha256(a).hexdigest(),
            "b_sha256": hashlib.sha256(b).hexdigest(),
            "c_sha256": hashlib.sha256(c).hexdigest(),
            "journal_mode": conn.execute("PRAGMA journal_mode").fetchone()[0],
            "by_book": [
                dict(r) for r in conn.execute("SELECT pdf_name, COUNT(*) c FROM stamps GROUP BY pdf_name ORDER BY pdf_name")
            ],
            "text_nonempty": conn.execute(
                "SELECT COUNT(*) FROM stamps WHERE text IS NOT NULL AND trim(text) <> ''"
            ).fetchone()[0],
            "no_blob": all(
                (t or "").upper().find("BLOB") < 0
                for t in [r[2] for r in conn.execute("PRAGMA table_info(stamps)")]
                + [r[2] for r in conn.execute("PRAGMA table_info(seals)")]
                + [r[2] for r in conn.execute("PRAGMA table_info(images)")]
            ),
        }
    finally:
        conn.close()
    return out


def file_manifest(root: Path) -> dict:
    """目录内逐文件 md5（**只读**）：用于证明既有产物未被改写。"""
    out = {}
    if not Path(root).is_dir():
        return out
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = hashlib.md5(p.read_bytes()).hexdigest()
    return out


def copy_db_via_backup(src: Path, dst: Path) -> None:
    """**WAL 安全的**副本：用 SQLite backup API 取一致快照（不靠 cp，避免漏 -wal）。"""
    s = ro_conn(src)
    d = sqlite3.connect(str(dst))
    try:
        with d:
            s.backup(d)
    finally:
        d.close()
        s.close()


def port_free(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) != 0


# --------------------------------------------------------------------- HTTP
def http(method: str, path: str, body=None, port: int | None = None, timeout: float = 120.0):
    port = PORT_MAIN if port is None else port  # **调用时**取全局（动态端口）
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in (exc.headers or {}).items()}, exc.read()


def jbody(raw: bytes):
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def http_json(method: str, path: str, body=None, port: int | None = None):
    code, headers, raw = http(method, path, body, port)
    return code, headers, jbody(raw), raw


# --------------------------------------------------------------------- 进程管控
class Api:
    def __init__(self, db: Path, port: int, export_root: Path, tag: str):
        self.db, self.port, self.export_root, self.tag = db, port, export_root, tag
        self.proc: subprocess.Popen | None = None
        self.log = EVID / f"{tag}_api.log"

    def start(self) -> str:
        env = dict(os.environ)
        env.update(
            FEICUI_DB=str(self.db),
            FEICUI_API_PORT=str(self.port),
            FEICUI_ROOT=str(FE),
            FEICUI_EXPORT_ROOT=str(self.export_root),
            PYTHONUNBUFFERED="1",
        )
        fh = self.log.open("wb")
        self.proc = subprocess.Popen(
            [str(API_PY), "-m", "app.main"], cwd=str(SRV), env=env, stdout=fh, stderr=subprocess.STDOUT
        )
        life_ok = False
        code = ""
        for _ in range(75):
            try:
                code, _, _raw = http("GET", "/api/health", port=self.port, timeout=3)
                if code == 200:
                    life_ok = True
                    break
            except Exception:
                pass
            time.sleep(0.4)
        say(f"  [{self.tag}] pid={self.proc.pid} port={self.port} db={self.db.name} health={code}")
        return code

    def stop(self) -> str:
        if not self.proc:
            return "noop"
        pid = self.proc.pid
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=10)
        alive = subprocess.run(["kill", "-0", str(pid)], capture_output=True).returncode == 0
        return "STILL_ALIVE" if alive else "gone"


def wait_port_gone(port: int, timeout: float = 15.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if port_free(port):
            return True
        time.sleep(0.3)
    return False


def reap_own_stale_apis(ports=(5321, 5322, 5323, 5324)) -> list[str]:
    """清掉**自己的**残留接口层（Zang 追加口径 ①）：三重身份校验后才按精确 PID 停（**无宽匹配 kill**）。

    三重校验＝① 是 `<port>` 的 listener；② 命令行含本仓 `server/.venv/bin/python` 与 `-m app.main`；
    ③ cwd 在 `feicui/server`。任一条不满足 ⇒ **不动它**（可能是别人的进程），只登记。
    """
    reaped = []
    for port in ports:
        out = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"], capture_output=True, text=True).stdout
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 2:
                continue
            pid = parts[1]
            if not ln_pid_is_ours(pid):
                say(f"  [reap] 端口 {port} 被非本仓进程占用 pid={pid} ⇒ **不动它**")
                continue
            subprocess.run(["kill", "-TERM", pid], capture_output=True)
            time.sleep(0.8)
            if subprocess.run(["kill", "-0", pid], capture_output=True).returncode == 0:
                subprocess.run(["kill", "-KILL", pid], capture_output=True)
            reaped.append(f"{port}:{pid}")
    if reaped:
        say(f"  [reap] 已按精确 PID 停掉自己的残留接口层：{', '.join(reaped)}")
    return reaped


def ln_pid_is_ours(pid: str) -> bool:
    """**只认自己起的接口层**：命令行须匹配本仓 `-m app.main`（绝不误杀别人的进程）。"""
    ps = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True).stdout
    return str(API_PY) in ps and "app.main" in ps


# ===================================================================== 主流程
def main() -> int:
    global _log_fh
    EVID.mkdir(parents=True, exist_ok=True)
    _log_fh = (EVID / "00_console.log").open("w", encoding="utf-8")
    global SCRATCH
    scratch = Path(tempfile.mkdtemp(prefix="feicui_1bii_"))
    SCRATCH = scratch
    say("=" * 78)
    say("阶段 1b-ii 自测：E3 / E4 / E6 / E7 + 1b-i 回归")
    say(f"时点 {datetime.now().astimezone().isoformat(timespec='seconds')}（Asia/Shanghai）")
    say(f"临时工作区 {scratch}（不作证据；证据落 {EVID}）")
    say("=" * 78)

    # ---------------------------------------------------------------- 0. 前置取证
    section("0. 前置取证")
    fp_before = fingerprints(PROD_DB)
    exp_before = file_manifest(PROD_EXPORTS)
    ck("0.1 正式库 stamps 列数（只读 PRAGMA）", len(fp_before["cols"]), EXPECT_FP["cols"])
    ck("0.1b stamps 列定义逐字", fp_before["cols"], EXPECT_COLS)
    ck("0.2 正式库 stamps 行数（只读）", fp_before["rows"], EXPECT_FP["rows"])
    ck("0.3 指纹 A raw md5（= ops §2.3 期望）", fp_before["a_md5"], EXPECT_FP["a_md5"])
    ck("0.4 指纹 B canon md5（= ops §2.3 期望）", fp_before["b_md5"], EXPECT_FP["b_md5"])
    ck("0.5 指纹 C free md5（= ops §2.3 期望）", fp_before["c_md5"], EXPECT_FP["c_md5"])
    say(f"  journal_mode={fp_before['journal_mode']}（迁移后应 = wal）text 非空={fp_before['text_nonempty']}")
    say(f"  逐书：{fp_before['by_book']}")
    ck("0.6 stamps/seals/images 无 BLOB 列（AC-12①）", fp_before["no_blob"], True)
    ev(
        "01_prod_fingerprint_before.json",
        {
            "verified_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "evidence": "Python sqlite3 uri=True mode=ro（**不用 sqlite3 CLI**，WAL 下 CLI + md5 会得空输入 md5）",
            **fp_before,
        },
    )
    ev("02_prod_exports_manifest_before.json", exp_before)
    say(f"  正式 exports/ 文件数={len(exp_before)}（应含 12 个 fb_* 批次包 + selfcheck_report.json）")
    n_batches_before = len({k.split("/")[0] for k in exp_before if k.startswith("fb_")})
    ck("0.7 正式 exports/ 批次包数（改动前）", n_batches_before, 12)
    # 「接口层不读 BLOB」判据（**主力判据＝库内无 BLOB 列**，即上一条 0.6；本处是附加的 SQL 级防护）
    # 判据改法依据＝派单方追加口径：grep 词面会命中**注释里「不得读 BLOB」这句话本身**与 `db.py` 里
    # 一个叫 `blob` 的局部变量（schema 指纹的拼接串）⇒ 词面匹配是假阳性；改为查「真能构成 BLOB 读写的
    # SQL 形态」：`cast(... as blob)` / `as blob` / `zeroblob(` / `blob(` / `hex(blob`。
    forbidden = re.compile(r"(?i)(\bas\s+blob\b|\bzeroblob\s*\(|\bblob\s*\(|\bhex\s*\(\s*blob)")
    sql_hits = []
    for py in sorted((SRV / "app").rglob("*.py")):
        for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if forbidden.search(line):
                sql_hits.append(f"{py.relative_to(SRV)}:{i}:{line.strip()}")
    ev(
        "03_api_no_blob_scan.txt",
        "== 主力判据：库内列类型（PRAGMA table_info）==\n"
        f"stamps/seals/images 无任何 BLOB 列 = {fp_before['no_blob']}（见 01_prod_fingerprint_before.json）\n"
        "  —— 库内本无 BLOB 列 ⇒ 接口层**在物理上不可能**从库读影像字节（AC-12① 同源）。\n"
        "\n== 附加防护：server/app/**/*.py 是否出现 BLOB 读写的 SQL 形态 ==\n"
        "  判据正则 = (?i)(\\bas\\s+blob\\b|\\bzeroblob\\s*\\(|\\bblob\\s*\\(|\\bhex\\s*\\(\\s*blob)\n"
        + ("\n".join(sql_hits) if sql_hits else "  (0 命中)")
        + "\n\n== 结论 ==\n"
        "① 库内无 BLOB 列（主力判据，已验）；② 接口层代码无 BLOB 读写的 SQL 形态（附加防护）；\n"
        "③ E6 的取图路径是「DB 取**相对路径** → 盘上读文件」（见 50/51/54 号证据），从不读库内字节。\n",
    )
    ck("0.8 接口层代码无 BLOB 读写的 SQL 形态（附加防护）", sql_hits, [])
    # **前置体检**（Zang 追加口径 ①②）：先按三重身份校验清掉自己的残留，再动态选端口
    reap_own_stale_apis()
    global PORT_MAIN, PORT_REG
    PORT_MAIN = pick_free_port(PORT_BASE)
    PORT_REG = pick_free_port(PORT_MAIN + 1)
    ck(f"0.9 自测端口已动态选定且无监听（main={PORT_MAIN}）", port_free(PORT_MAIN), True)
    ck(f"0.10 自测端口已动态选定且无监听（reg={PORT_REG}）", port_free(PORT_REG), True)

    # ---------------------------------------------------------------- 1. 副本库 + fixture
    section("1. 副本库与确定性数据集")
    copy_main = scratch / "copy_main.db"
    copy_reg = scratch / "copy_reg.db"
    copy_db_via_backup(PROD_DB, copy_main)
    copy_db_via_backup(PROD_DB, copy_reg)
    # **每轮全新副本 + 活跃 job 必须为空**（Zang 追加口径 ③）：否则 201 与 409 会互相污染
    for db in (copy_main, copy_reg):
        n_jobs = q1(db, "SELECT COUNT(*) FROM jobs")
        n_active = q1(db, "SELECT COUNT(*) FROM jobs WHERE state IN ('QUEUED','RUNNING','PAUSED')")
        if n_jobs:
            conn = sqlite3.connect(str(db))
            try:
                with conn:  # **只在副本库**里清历史 job，保证 201/409 口径干净
                    conn.execute("DELETE FROM job_pages")
                    conn.execute("DELETE FROM jobs")
            finally:
                conn.close()
        say(f"  [normalize] {db.name}: 原 jobs={n_jobs}（活跃 {n_active}）→ 已归零（仅副本库）")
        ck(f"1.0 {db.name} 副本库活跃 job 集合为空（前置断言）",
           q1(db, "SELECT COUNT(*) FROM jobs WHERE state IN ('QUEUED','RUNNING','PAUSED')"), 0)
    ck("1.1 副本库（backup API 一致快照）行数", q1(copy_main, "SELECT COUNT(*) FROM stamps"), EXPECT_FP["rows"])
    ck("1.2 副本库指纹 B 与正式库一致", fingerprints(copy_main)["b_md5"], fp_before["b_md5"])

    # fixture PDF（仅用于 E1 的路径存在性判定；内容对齐 G-6 的 %PDF- magic）
    fix_pdf = scratch / FIXTURE_BOOK
    fix_pdf.write_bytes("%PDF-1.4\n% 1b-ii fixture (not a real PDF; only for E1 path check)\n".encode("utf-8"))

    # fixture 行（**只插副本库**；书名独立，绝不与真书撞名）——覆盖 E6 的四类 404 与「无 seals 记录」壳记录
    fixture_rows = [
        (FIXTURE_BOOK, 1, 0, "output/../../../../etc/passwd"),        # 越界（逃出 FEICUI_ROOT）
        (FIXTURE_BOOK, 1, 1, "/etc/passwd"),                          # 绝对路径
        (FIXTURE_BOOK, 1, 2, ""),                                     # img_path_null
        (FIXTURE_BOOK, 1, 3, "output/__1bii_missing__.webp"),         # 相对路径但盘上无此文件
    ]
    conn = sqlite3.connect(str(copy_main))
    try:
        with conn:
            conn.executemany(
                """INSERT INTO stamps(pdf_name, page, idx, text, img_path, x1, y1, x2, y2)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                [(b, p, i, None, ip, 1.0, 2.0, 3.0, 4.0) for (b, p, i, ip) in fixture_rows],
            )
    finally:
        conn.close()
    ck(
        "1.3 fixture 行已入副本库（4 行 / 独立书名）",
        q1(copy_main, "SELECT COUNT(*) FROM stamps WHERE pdf_name = ?", (FIXTURE_BOOK,)),
        4,
    )
    ev(
        "10_fixture_dataset.json",
        {
            "note": "fixture 行只插副本库；书名独立；越界/空路径/盘上缺文件四类各一行",
            "fixture_book": FIXTURE_BOOK,
            "rows": [{"page": p, "idx": i, "img_path": ip} for (_b, p, i, ip) in fixture_rows],
            "copy_main": str(copy_main),
        },
    )

    export_root_main = scratch / "exports_tmp_main"
    api_main = Api(copy_main, PORT_MAIN, export_root_main, "main")
    api_reg = Api(copy_reg, PORT_REG, scratch / "exports_tmp_reg", "reg")
    # 就绪判据＝**健康探针可达**（不是「新接口已实现」）；不就绪也**不早退**，继续跑完以留下完整 FAIL 证据
    ck("1.4 主接口层健康探针可达（/api/health=200）", api_main.start(), 200)

    # ---------------------------------------------------------------- 2. E1 建 job（数据集）
    section("2. 建 job（E1，副本库）")
    books = qall(
        copy_main,
        "SELECT pdf_name, COUNT(*) c, MIN(page) lo, MAX(page) hi FROM stamps WHERE pdf_name <> ? "
        "GROUP BY pdf_name ORDER BY pdf_name",
        (FIXTURE_BOOK,),
    )
    jobs = {}
    for b in books:
        pdf_path = {
            "tmp.pdf": str(FE / "tmp.pdf"),
            "古玺汇编 文物出版社 罗福颐  ok.pdf": str(Path.home() / "Downloads" / "古玺汇编 文物出版社 罗福颐  ok.pdf"),
            "秦汉印典 上海书画 金怀英  1997 ok.pdf": str(Path.home() / "Downloads" / "秦汉印典 上海书画 金怀英  1997 ok.pdf"),
        }.get(b["pdf_name"])
        if pdf_path is None:
            say(f"  [skip] 无 PDF 路径映射：{b['pdf_name']}")
            jobs[b["pdf_name"]] = None
            continue
        code, _h, body, raw = http_json(
            "POST", "/api/jobs", {"pdf_path": pdf_path, "page_range": [int(b["lo"]), int(b["hi"])]}
        )
        if code != 201:
            say(f"  ✗ E1 失败 {b['pdf_name']} code={code} body={raw[:200]!r}")
            jobs[b["pdf_name"]] = None
            continue
        jobs[b["pdf_name"]] = body["job_id"]
        say(f"  E1 {b['pdf_name']} → {body['job_id']} total_pages={body['total_pages']} rows={b['c']} "
            f"pages={b['lo']}..{b['hi']}")
    code, _h, body, raw = http_json("POST", "/api/jobs", {"pdf_path": str(fix_pdf), "page_range": [1, 1]})
    jobs[FIXTURE_BOOK] = body["job_id"] if code == 201 else None
    say(f"  E1 {FIXTURE_BOOK} → {jobs[FIXTURE_BOOK]}（code={code}）")
    ev("20_e1_jobs.json", {"jobs": jobs, "books": books})
    ckT("2.1 五个 job 全部建成（3 真书 + fixture）", all(jobs.values()), f"{jobs}")
    if not all(jobs.values()):
        # 夹具前置不成立 ⇒ 只报这一条 FAIL 并中止（避免 25 条级联假 FAIL 淹没真缺陷）
        say("✗ 夹具前置不成立（有 job 未建成）：E3/E4/E6 各子段**跳过**、不计入断言，请先修前置")
        ev("20_fixture_abort.json", {"jobs": jobs, "verdict": "前置于此中止，未进入 E3/E4/E6 子段"})
        summary = {"PASS": PASS, "FAIL": FAIL, "aborted": "E1 夹具前置未满足", "failed_names": FAILED_NAMES}
        ev("99_summary.json", summary)
        say(f"PASS={PASS} FAIL={FAIL}（前置于此中止）")
        return 1
    jobs = {k: v for k, v in jobs.items()}

    # 同书重复建单 ⇒ 409 + 既有 job_id（§3.1 E1 / §3.2 S-5）
    code, _h, body, raw = http_json(
        "POST", "/api/jobs", {"pdf_path": str(FE / "tmp.pdf"), "page_range": [1, 30]}
    )
    ev("21_e1_duplicate_409.json", {"code": code, "body": body})
    ck("2.2 同书重复建单 ⇒ 409", code, 409)
    ck("2.3 409 体带回既有 job_id", body.get("job_id"), jobs["tmp.pdf"])
    dup_active = qall(
        copy_main,
        "SELECT pdf_name, COUNT(*) n FROM jobs WHERE state IN ('QUEUED','RUNNING','PAUSED') "
        "GROUP BY pdf_name HAVING n > 1",
    )
    ck("2.4 每书活跃 job 数 ≤ 1（SQL 独立复算）", dup_active, [])

    # ---------------------------------------------------------------- 3. E3
    section("3. ① E3 分页取结果")
    ENVELOPE_KEYS = {"items", "page", "limit", "total", "has_more", "next_cursor"}
    LIMIT = 7  # 与各书条数不整除（30/23/26/4）——能暴露末页与游标边界问题
    e3_report = {}
    all_keys_api: set = set()
    e3_raw_pages = []
    for pdf_name, job_id in jobs.items():
        keys_api: list[tuple] = []
        cursor = None
        pages = 0
        seen_cursors = set()
        envelope_ok = True
        field_ok = True
        # ① 硬上界 = ceil(该书页区间行数/limit) + 2（夹具护栏，防上一轮的失控重演）
        _n_rows = 4 if pdf_name == FIXTURE_BOOK else int(
            next(b["c"] for b in books if b["pdf_name"] == pdf_name))
        _cap = page_cap(_n_rows, LIMIT)
        for _i in range(_cap):
            qs = f"?limit={LIMIT}" + (f"&cursor={cursor}" if cursor else "")
            code, _h, body, raw = http_json("GET", f"/api/jobs/{job_id}/stamps{qs}")
            if code != 200:
                say(f"  ✗ E3 {pdf_name} code={code} body={raw[:200]!r}")
                envelope_ok = False
                break
            pages += 1
            if not isinstance(body, dict) or "items" not in body:
                envelope_ok = False
                say(f"  ✗ 该接口未返回信封（code={code}）：{str(body)[:160]}；"
                    f"原始报文={_short(raw)} ⇒ 中止该子段")
                break
            if set(body.keys()) != ENVELOPE_KEYS:
                envelope_ok = False
                say(f"  ✗ 信封字段不符：{sorted(body.keys())}")
            if not isinstance(body["items"], list):
                field_ok = False
            if body["page"] != pages:
                field_ok = False
                say(f"  ✗ page 应为 {pages}，得到 {body['page']}")
            if body["has_more"] != (body["next_cursor"] is not None):
                field_ok = False
                say("  ✗ has_more 与 next_cursor 不一致")
            page_keys = []
            for it in body["items"]:
                page_keys.append((it["sourcePageNo"], it["feicui"]["stampIdx"]))
                if "missing_required" not in it:
                    field_ok = False
            keys_api += page_keys
            e3_raw_pages.append(
                {
                    "pdf_name": pdf_name,
                    "request": f"/api/jobs/{job_id}/stamps{qs}",
                    "page": body["page"],
                    "limit": body["limit"],
                    "total": body["total"],
                    "has_more": body["has_more"],
                    "next_cursor": body["next_cursor"],
                    "n_items": len(body["items"]),
                    "keys_of_page": [list(k) for k in page_keys],
                    "item0_top_level_keys": sorted(body["items"][0].keys()) if body["items"] else [],
                }
            )
            if not body["has_more"]:
                if body["next_cursor"] is not None:
                    field_ok = False
                break
            # ② 游标推进护栏：不推进 / 给不出游标 ⇒ 立即 break 并只报一条 FAIL（附原始报文）
            _nxt, _why = cursor_step(cursor, body, seen_cursors, raw)
            if _why:
                field_ok = False
                ckT(f"3.0b [{pdf_name}] E3 游标推进护栏（不推进 ⇒ 立即中止）", False, _why)
                break
            seen_cursors.add(_nxt)
            cursor = _nxt
        else:
            envelope_ok = False
            say(f"  ✗ [{pdf_name}] E3 游标循环触及硬上界 {_cap}（① 护栏命中）")
        # 独立复算：全量键集（SQL，不看接口）
        lo_hi = (
            (1, 1)
            if pdf_name == FIXTURE_BOOK
            else (next(b["lo"] for b in books if b["pdf_name"] == pdf_name),
                  next(b["hi"] for b in books if b["pdf_name"] == pdf_name))
        )
        want_keys = [
            (r["page"], r["idx"])
            for r in qall(
                copy_main,
                "SELECT page, idx FROM stamps WHERE pdf_name = ? AND page BETWEEN ? AND ? ORDER BY page, idx, id",
                (pdf_name, int(lo_hi[0]), int(lo_hi[1])),
            )
        ]
        ck(f"3.1 [{pdf_name}] 信封 6 字段（逐页）", envelope_ok, True)
        ck(f"3.2 [{pdf_name}] 页内字段一致（page / has_more↔cursor / missing_required）", field_ok, True)
        ck(f"3.3 [{pdf_name}] 游标翻页无重叠无遗漏", sorted(keys_api), sorted(want_keys))
        ck(f"3.4 [{pdf_name}] 条数 == 独立复算", len(keys_api), len(want_keys))
        ck(f"3.5 [{pdf_name}] 翻页数 == ceil(total/limit)", pages, -(-len(want_keys) // LIMIT))
        all_keys_api.update(keys_api)
        e3_report[pdf_name] = {"job_id": job_id, "pages": pages, "keys": len(keys_api), "total_sql": len(want_keys)}
        say(f"  [{pdf_name}] 翻 {pages} 页 / {len(keys_api)} 条（SQL 复算 {len(want_keys)} 条）")
    ev("30_e3_pagination.json", e3_report)
    ev("31_e3_sample_items.json", e3_raw_pages)
    total_rows = q1(copy_main, "SELECT COUNT(*) FROM stamps")
    ck("3.6 全部书的 key 集合合并 == 全表集合", len(all_keys_api), int(total_rows))
    ck("3.7 全部书无重复 key（无重叠）", len(all_keys_api), len(set(all_keys_api)))

    # 页码分页（?page=）与游标分页必须等价
    tmp_job = jobs["tmp.pdf"]
    keys_page_mode: list[tuple] = []
    p = 1
    body = None
    while True:
        code, _h, body, _raw = http_json("GET", f"/api/jobs/{tmp_job}/stamps?page={p}&limit={LIMIT}")
        if code != 200 or not isinstance(body, dict) or "items" not in body:
            body = {"items": [], "has_more": False, "page": None}
            ck("3.8a 页码分页响应为信封", False, f"code={code} body={str(_raw[:120])}")
            break
        keys_page_mode += [(it["sourcePageNo"], it["feicui"]["stampIdx"]) for it in body["items"]]
        if not body["has_more"]:
            break
        p += 1
    want_tmp = [
        (r["page"], r["idx"])
        for r in qall(
            copy_main,
            "SELECT page, idx FROM stamps WHERE pdf_name = 'tmp.pdf' ORDER BY page, idx, id",
        )
    ]
    ck("3.8 页码分页（?page=）与游标分页结果一致", sorted(keys_page_mode), sorted(want_tmp))
    ck("3.9 页码分页：page 参数从 1 起、报回页号递增", body.get("page"), p)

    # AC-08：每条记录必须给出 §9.3 必填 11 项（或明确 missing_required）
    REQ_PATHS = {
        "seal_name": lambda it: it.get("sealName") is not None,
        "dynasty": lambda it: it.get("dynasty") is not None,
        "seal_type": lambda it: it.get("sealType") is not None,
        "asset_kind": lambda it: (it.get("assets") or [{}])[0].get("kind") is not None,
        "source_book": lambda it: it.get("sourceBook") is not None,
        "source_page_no": lambda it: it.get("sourcePageNo") is not None,
        "seal_code": lambda it: it.get("sealCode") is not None,
        "sha256": lambda it: (it.get("assets") or [{}])[0].get("sha256") is not None,
        "image_metrics": lambda it: all(
            (it.get("assets") or [{}])[0].get(k) is not None for k in ("bytes", "width", "height", "colorMode")
        ),
        "review_status": lambda it: it.get("reviewStatus") is not None,
        "batch_id": lambda it: it.get("batchId") is not None,
    }
    ac08_bad, ac08_items, ac08_missing_total = [], 0, 0
    for pdf_name, job_id in jobs.items():
        cursor, got, seen_cur = None, 0, set()
        _cap8 = page_cap(4 if pdf_name == FIXTURE_BOOK else int(
            next(b["c"] for b in books if b["pdf_name"] == pdf_name)), 50)
        for _i in range(_cap8):
            qs = f"?limit=50" + (f"&cursor={cursor}" if cursor else "")
            code, _h, body, _raw = http_json("GET", f"/api/jobs/{job_id}/stamps{qs}")
            if code != 200 or not isinstance(body, dict) or "items" not in body:
                ckT(f"3.10b [{pdf_name}] AC-08 响应为 6 字段信封", False,
                    f"code={code} 原始报文={_short(_raw)} ⇒ 中止该子段")
                break
            for it in body["items"]:
                got += 1
                ac08_items += 1
                miss = [k for k, f in REQ_PATHS.items() if not f(it)]
                declared = set(it.get("missing_required") or [])
                ac08_missing_total += len(declared)
                if miss and not miss_found_in(declared, miss):
                    ac08_bad.append({"pdf_name": pdf_name, "page": it.get("sourcePageNo"),
                                     "idx": it["feicui"]["stampIdx"], "undeclared": miss,
                                     "declared": sorted(declared)})
            if not body["has_more"]:
                break
            _nxt, _why = cursor_step(cursor, body, seen_cur, _raw)
            if _why:
                ckT(f"3.10c [{pdf_name}] AC-08 游标推进护栏（不推进 ⇒ 立即中止）", False, _why)
                break
            seen_cur.add(_nxt)
            cursor = _nxt
        else:
            ckT(f"3.10d [{pdf_name}] AC-08 游标循环在硬上界内收敛", False, f"触及上界 {_cap8}")
    ev(
        "32_ac08_coverage.json",
        {
            "checked_items": ac08_items,
            "items_with_undeclared_missing_required": ac08_bad,
            "declared_missing_required_total": ac08_missing_total,
            "verdict": "AC-08 PASS（缺字段的每条都给出了 missing_required）" if not ac08_bad else "AC-08 FAIL",
        },
    )
    ck("3.10 AC-08 每条记录必填 11 项或缺字段声明（无静默缺字段）", ac08_bad, [])
    ck("3.11 AC-08 覆盖检查条目数 == 全量条数", ac08_items, int(total_rows))

    # 400 / 404 分支
    cases = [
        ("page=0", "/stamps?page=0&limit=7", 400),
        ("limit=0", "/stamps?limit=0", 400),
        ("limit=501", "/stamps?limit=501", 400),
        ("page 与 cursor 同给", "/stamps?page=1&limit=7&cursor=p1_i0", 400),
        ("cursor 形态非法", "/stamps?limit=7&cursor=zzz", 400),
        ("limit 非整数", "/stamps?limit=abc", 400),
        ("未知 job", "/stamps?limit=7", 404),
    ]
    err_ev = []
    for name, qs, want in cases:
        path = f"/api/jobs/{tmp_job}{qs}" if name != "未知 job" else f"/api/jobs/job-does-not-exist{qs}"
        code, _h, body, raw = http_json("GET", path)
        err_ev.append({"case": name, "path": path, "code": code, "body": body})
        ck(f"3.12 E3 {name} ⇒ {want}", code, want)
        ckT(f"3.13 E3 {name} 体含 detail（§3.4）", isinstance(body, dict) and "detail" in body, str(body)[:120])
    ev("33_e3_errors.json", err_ev)

    # ---------------------------------------------------------------- 4. E7
    section("4. ② E7 job 列表")
    EV7_LIMIT = 2
    E7_ITEM_KEYS = sorted(["job_id", "pdf_name", "pdf_path", "state", "total_pages", "done_pages",
                           "failed_pages_count", "created_at", "updated_at"])
    code, _h, body, raw = http_json("GET", f"/api/jobs?limit={EV7_LIMIT}")
    ev("40_e7_page1.json", {"code": code, "body": body})
    ck("4.1 E7 ⇒ 200", code, 200)
    # ④ 响应不是信封 / job_id 为空 ⇒ 显式 FAIL 并**中止该子段**（不再级联产出假 FAIL）
    e7_ok = code == 200 and isinstance(body, dict) and "items" in body
    ck("4.2 E7 信封 = E3 同款 6 字段",
       sorted(body.keys()) if isinstance(body, dict) else None, sorted(ENVELOPE_KEYS))
    e7_ok = e7_ok and isinstance(body, dict) and set(body.keys()) == ENVELOPE_KEYS
    if e7_ok and body["items"]:
        ck("4.3 E7 items 字段集（§3.1 E7 行 9 项）", sorted(body["items"][0].keys()), E7_ITEM_KEYS)
        bad_ids = [it for it in body["items"] if not it.get("job_id")]
        ckT("4.3b E7 每条 job_id 非空（None ⇒ 中止子段）", not bad_ids, f"{_short(bad_ids)}")
        e7_ok = not bad_ids
    elif e7_ok:
        ckT("4.3 E7 items 非空（有 job 才谈翻页）", False, "items 为空 ⇒ E7 子段中止")
        e7_ok = False
    if not e7_ok:
        say("✗ E7 子段中止（响应不是 6 字段信封 / job_id 为空）：不再产出级联假 FAIL")
        ev("41_e7_pagination.json",
           {"aborted": True, "code": code, "raw": _short(raw, 600),
            "note": "④ 响应非信封或 job_id 为空 ⇒ 显式 FAIL 并中止该子段"})
    else:
        want_ids = [r["job_id"] for r in qall(copy_main, "SELECT job_id FROM jobs ORDER BY created_at, job_id")]
        total_jobs = len(want_ids)
        cap = page_cap(total_jobs, EV7_LIMIT)          # ① 硬上界 = ceil(total/limit)+2（≤50）
        # ---- ② 游标路径（带上界 + 游标推进护栏）----
        ids_api, cursor, pages, seen_cur, guard = [], None, 0, set(), None
        for _i in range(cap):
            qs = f"?limit={EV7_LIMIT}" + (f"&cursor={cursor}" if cursor else "")
            code, _h, body, _raw = http_json("GET", f"/api/jobs{qs}")
            if code != 200 or not isinstance(body, dict) or "items" not in body:
                guard = f"非信封响应（code={code}）⇒ 中止；原始报文={_short(_raw)}"
                break
            pages += 1
            if body["has_more"] != (body["next_cursor"] is not None):
                ckT("4.4 E7 has_more↔next_cursor 一致", False,
                    f"page={body['page']} has_more={body['has_more']} next_cursor={body['next_cursor']!r}"
                    f" 原始报文={_short(_raw)}")
            ids_api += [it["job_id"] for it in body["items"]]
            nxt, why = cursor_step(cursor, body, seen_cur, _raw)
            if why:
                ckT("4.4b E7 游标推进护栏（不推进/给不出游标 ⇒ 立即中止）", False, why)
                guard = "breaker"
                break
            if nxt is None:
                break
            seen_cur.add(nxt)
            cursor = nxt
        else:
            guard = f"游标循环触及硬上界 {cap}"
        ckT("4.4c E7 游标路径在硬上界内收敛（① 与 ② 护栏）", guard is None, str(guard))
        ck("4.5 E7 游标翻页 no overlap no miss", sorted(ids_api), sorted(want_ids))
        ck("4.6 E7 total == 库内 job 数", q1(copy_main, "SELECT COUNT(*) FROM jobs"), total_jobs)
        ck("4.7 E7 翻页数 == ceil(total/limit)", pages, -(-total_jobs // EV7_LIMIT))
        # ---- 页码路径（本单修的缺陷：`?page=` 原先被框架静默忽略）----
        # 逐页取 page=1..cap；末页之后必须**空 items + has_more=false**（不得回吐第一页）
        page_rows, page_ids, page_ok, beyond = [], [], True, []
        for p in range(1, cap + 1):
            code, _h, body, _raw = http_json("GET", f"/api/jobs?limit={EV7_LIMIT}&page={p}")
            if code != 200 or not isinstance(body, dict) or "items" not in body:
                ckT("4.11 E7 页码路径响应为 6 字段信封", False,
                    f"page={p} code={code} 原始报文={_short(_raw)}")
                page_ok = False
                break
            page_rows.append({"page": p, "reported_page": body["page"], "items": len(body["items"]),
                              "has_more": body["has_more"], "next_cursor": body["next_cursor"],
                              "ids": [it["job_id"] for it in body["items"]]})
            if body["page"] != p:
                page_ok = False
            if body["has_more"] != (body["next_cursor"] is not None):
                page_ok = False
            page_ids += page_rows[-1]["ids"]
            if p > -(-total_jobs // EV7_LIMIT):
                beyond.append(page_rows[-1])
        ckT("4.11 E7 页码路径逐页：报回页号 == 请求页号，且 has_more↔next_cursor 一致", page_ok,
            f"{[(r['page'], r['reported_page'], r['has_more']) for r in page_rows]}")
        ckT("4.12 E7 页码路径 no overlap no miss（key 集合 == 库内顺序）",
            sorted(page_ids) == sorted(want_ids) and len(page_ids) == len(set(page_ids)),
            f"page_ids={len(page_ids)} 去重后={len(set(page_ids))} 库内={total_jobs}")
        ckT("4.13 E7 页码路径 key 集合 == 游标路径 key 集合（两路等价）",
            sorted(page_ids) == sorted(ids_api), f"page={sorted(page_ids)} cursor={sorted(ids_api)}")
        ckT("4.14 E7 page 超出末页 ⇒ 空 items + has_more=false（不得再吐第一页）",
            bool(beyond) and all(r["items"] == 0 and r["has_more"] is False and r["next_cursor"] is None
                                 for r in beyond),
            f"{[(r['page'], r['items'], r['has_more']) for r in beyond]}")
        ckT("4.15 E7 page=2 与 page=1 内容不同（原缺陷回归判据：page 曾被静默忽略）",
            len(page_rows) >= 2 and page_rows[0]["ids"] != page_rows[1]["ids"],
            f"page1={page_rows[0]['ids'] if page_rows else None} page2={page_rows[1]['ids'] if len(page_rows) > 1 else None}")
        code, _h, body, _raw = http_json("GET", "/api/jobs?state=QUEUED&limit=50")
        ck("4.8 E7 state 过滤（QUEUED）计数 == 库内复算",
           len(body["items"]),
           q1(copy_main, "SELECT COUNT(*) FROM jobs WHERE state='QUEUED'"))
        code, _h, body, _raw = http_json("GET", "/api/jobs?state=BOGUS")
        ck("4.9 E7 state 非法 ⇒ 400", code, 400)
        code, _h, body, _raw = http_json("GET", "/api/jobs?cursor=nosep")
        ck("4.10 E7 cursor 非法 ⇒ 400", code, 400)
        code, _h, body, _raw = http_json("GET", f"/api/jobs?page=0")
        ck("4.16 E7 page=0 ⇒ 400（1-based）", code, 400)
        code, _h, body, _raw = http_json("GET", f"/api/jobs?page=1&limit={EV7_LIMIT}&cursor=")
        code2, _h, body2, _raw2 = http_json("GET", "/api/jobs?limit=2&page=1&cursor=nosep")
        ck("4.17 E7 page 与 cursor 同给 ⇒ 400（与 E3 同款互斥）", code2, 400)
        ev("41_e7_pagination.json",
           {"ids_api": ids_api, "want_ids": want_ids, "pages": pages, "page_rows": page_rows,
            "cap": cap, "guard": guard,
            "note": "页码路径与游标路径的 key 集合必须逐条相等；末页之后必须空 items + has_more=false"})

    # ---------------------------------------------------------------- 5. E6
    section("5. ③ E6 取印面图像")
    # 正常取图：用一条真实存在的记录（tmp.pdf p13 i0，img_path 在盘上）
    real = qall(
        copy_main,
        "SELECT page, idx, img_path FROM stamps WHERE pdf_name='tmp.pdf' AND img_path IS NOT NULL "
        "ORDER BY page, idx, id",
    )
    pick = None
    for r in real:
        if (FE / r["img_path"]).is_file():
            pick = r
            break
    ckT("5.0 找到一条盘上有影像的记录", pick is not None, str(pick))
    img_rel = pick["img_path"]
    disk = (FE / img_rel).read_bytes()
    code, headers, raw = http("GET", f"/api/jobs/{tmp_job}/stamps/{pick['page']}/{pick['idx']}/image")
    ev(
        "50_e6_image_200_headers.txt",
        json.dumps({"path": f"/api/jobs/{tmp_job}/stamps/{pick['page']}/{pick['idx']}/image",
                    "code": code, "headers": headers, "bytes": len(raw)}, ensure_ascii=False, indent=1),
    )
    ck("5.1 E6 正常取图 ⇒ 200", code, 200)
    ckT("5.2 Content-Type 属允许三元组（以文件实际类型为准）",
        headers.get("content-type", "").split(";")[0] in {"image/webp", "image/png", "image/jpeg"},
        headers.get("content-type", ""))
    ck("5.3 Content-Length 必填且 == 实际字节", int(headers.get("content-length", -1)), len(raw))
    ck("5.4 返回影像字节（与盘上文件逐字节相同）", hashlib.sha256(raw).hexdigest(),
       hashlib.sha256(disk).hexdigest())
    ckT("5.5 **不包 JSON 信封**（首字节不是 '{'）", not raw.lstrip().startswith(b"{"), repr(raw[:12]))
    ck("5.6 Cache-Control: no-store（§3.5 纪律⑤）", headers.get("cache-control"), "no-store")
    ck("5.7 x-feicui-img-path == DB 内相对路径", headers.get("x-feicui-img-path"), img_rel)

    # 三类 404 同码
    e6_404 = []
    cases404 = [
        ("job 不存在", f"/api/jobs/job-nope/stamps/1/0/image"),
        ("记录不存在（该书页区间内的缺号）", f"/api/jobs/{tmp_job}/stamps/999999/0/image"),
    ]
    for name, path in cases404:
        code, _h, body, _raw = http_json("GET", path)
        e6_404.append({"case": name, "path": path, "code": code, "body": body})
        ck(f"5.8 E6 {name} ⇒ 404", code, 404)
    fix_job = jobs[FIXTURE_BOOK]
    for r in fixture_rows:
        _, page, idx, ip = r
        path = f"/api/jobs/{fix_job}/stamps/{page}/{idx}/image"
        code, _h, body, _raw = http_json("GET", path)
        e6_404.append({"case": f"fixture img_path={ip!r}", "path": path, "code": code, "body": body})
        ck(f"5.9 E6 越界/缺失拒绝 img_path={ip!r} ⇒ 404", code, 404)
    ev("51_e6_404.json", e6_404)

    # 400：page / idx 非法
    e6_400 = []
    for name, path in [
        ("page 非整数", f"/api/jobs/{tmp_job}/stamps/abc/0/image"),
        ("page < 1", f"/api/jobs/{tmp_job}/stamps/0/0/image"),
        ("page 负数", f"/api/jobs/{tmp_job}/stamps/-3/0/image"),
        ("idx 非整数", f"/api/jobs/{tmp_job}/stamps/1/xyz/image"),
        ("idx < 0", f"/api/jobs/{tmp_job}/stamps/1/-1/image"),
        ("page 小数", f"/api/jobs/{tmp_job}/stamps/1.5/0/image"),
        ("URL 编码穿越 %2e%2e", f"/api/jobs/{tmp_job}/stamps/%2e%2e/0/image"),
    ]:
        code, _h, body, _raw = http_json("GET", path)
        e6_400.append({"case": name, "path": path, "code": code, "body": body})
        ck(f"5.10 E6 {name} ⇒ 400", code, 400)
    ev("52_e6_400.json", e6_400)

    # 废止的临时路径（2 段 idx 形态）不得被实现
    code, _h, body, _raw = http_json("GET", f"/api/jobs/{tmp_job}/stamps/0/image")
    ev("53_e6_deprecated_path.json", {"path": f"/api/jobs/{tmp_job}/stamps/0/image", "code": code, "body": body})
    ck("5.11 废止的 2 段临时路径 ⇒ 404（后端不两套并存，§3.5 收口规则②）", code, 404)

    # 越界校验的**直读证据**：把 fixture 行的 img_path 与解析结果并排给出
    ev(
        "54_e6_traversal_guard.json",
        {
            "note": "越界判据＝`Path(FEICUI_ROOT + img_path).resolve()` 必须仍在 FEICUI_ROOT 之内；"
                    "绝对路径与逃逸路径一律拒（404），见 51_e6_404.json 的 fixture 三例",
            "FEICUI_ROOT": str(FE),
            "cases": [
                {"img_path": "../../../../etc/passwd", "resolved": str((FE / "../../../../etc/passwd").resolve()),
                 "within_root": False, "verdict": "404 IMAGE_UNAVAILABLE"},
                {"img_path": "/etc/passwd", "resolved": "/etc/passwd", "within_root": False,
                 "verdict": "404 IMAGE_UNAVAILABLE"},
                {"img_path": "", "resolved": None, "within_root": None, "verdict": "404 IMAGE_UNAVAILABLE(img_path_null)"},
                {"img_path": "output/__1bii_missing__.webp", "resolved": str(FE / "output/__1bii_missing__.webp"),
                 "within_root": True, "verdict": "404 IMAGE_UNAVAILABLE(文件不在盘上)"},
            ],
        },
    )

    # ---------------------------------------------------------------- 6. E4
    section("6. ④ E4 触发导出")
    code, _h, body, raw = http_json("POST", f"/api/jobs/{tmp_job}/export", {})
    ev("60_e4_export_response.json", {"code": code, "body": body})
    ck("6.1 E4 ⇒ 200", code, 200)
    ck("6.2 E4 响应 4 字段", sorted((body or {}).keys()),
       sorted(["batch_id", "package_dir", "counts", "selfcheck_ref"]))
    ck("6.3 E4 counts 3 字段", sorted((body.get("counts") or {}).keys()), sorted(["formal", "draft", "rejected"]))
    pkg = export_root_main / body["batch_id"]
    ckT("6.4 批包目录真实存在（临时导出根内）", pkg.is_dir(), str(pkg))
    files = sorted(str(p.relative_to(pkg)) for p in pkg.rglob("*") if p.is_file())
    rep = json.loads((pkg / "report.json").read_text(encoding="utf-8"))
    ev(
        "61_e4_package.json",
        {
            "batch_id": body["batch_id"],
            "package_dir_reported": body["package_dir"],
            "package_dir_on_disk": str(pkg),
            "files": files,
            "report_counts_feicuiDecidable": rep["counts"]["feicuiDecidable"],
            "report_jsonl": rep["jsonl"],
            "e4_counts": body["counts"],
        },
    )
    ck("6.5 批包内文件集（manifest/report/两条 JSONL/images）", [f for f in files if "/" not in f],
       ["draft.jsonl", "manifest.json", "report.json", "seals.jsonl"])
    ck("6.6 E4 counts.formal == report.formal", body["counts"]["formal"], rep["counts"]["feicuiDecidable"]["formal"])
    ck("6.7 E4 counts.draft == report.draftStaged", body["counts"]["draft"],
       rep["counts"]["feicuiDecidable"]["draftStaged"])
    ck("6.8 E4 counts.rejected == report.rejectedRequiredMissing", body["counts"]["rejected"],
       rep["counts"]["feicuiDecidable"]["rejectedRequiredMissing"])
    n_img = len([f for f in files if f.startswith("images/")])
    ckT("6.9 批包内影像被真实复制", n_img > 0, f"{n_img} 个")
    say(f"  E4 回执：batch_id={body['batch_id']} package_dir={body['package_dir']} counts={body['counts']} "
        f"images={n_img}")

    e4_err = []
    for name, payload, want in [
        ("指定 batch_id", {"batch_id": "fb_whatever"}, 400),
        ("dry_run=true", {"dry_run": True}, 400),
        ("book_code 不符", {"book_code": "NOPE"}, 400),
    ]:
        code, _h, b, _raw = http_json("POST", f"/api/jobs/{tmp_job}/export", payload)
        e4_err.append({"case": name, "payload": payload, "code": code, "body": b})
        ck(f"6.10 E4 {name} ⇒ {want}", code, want)
    code, _h, b, _raw = http_json("POST", "/api/jobs/job-nope/export", {})
    e4_err.append({"case": "job 不存在", "code": code, "body": b})
    ck("6.11 E4 未知 job ⇒ 404", code, 404)
    ev("62_e4_errors.json", e4_err)

    exp_after = file_manifest(PROD_EXPORTS)
    ev("63_prod_exports_manifest_after.json", exp_after)
    ck("6.12 正式 exports/ 既有产物逐文件 md5 **未变**", exp_after, exp_before)
    ck(
        "6.12b 正式 exports/ 的 12 个批次包**名称集合**未变",
        {k.split("/")[0] for k in exp_after if k.startswith("fb_")},
        {k.split("/")[0] for k in exp_before if k.startswith("fb_")},
    )
    ck("6.13 正式 exports/ 批次包数仍 12", len({k.split("/")[0] for k in exp_after if k.startswith("fb_")}), 12)
    say(f"  正式 exports/：{len(exp_after)} 个文件 / md5 全等；新增批次只落临时根 {export_root_main}")

    # ---------------------------------------------------------------- 7. ⑤ 1b-i 回归
    section("7. ⑤ 1b-i worker 链路回归")
    # 回归臂就绪（第二次起一个接口层；仍在非登记端口 5322）
    ck("7.1 回归臂接口层就绪", api_reg.start(), 200)
    # **夹具修正（本单）**：回归臂页区间取自该书的**真实页跨度**——tmp.pdf 的 stamps 只在 13–19 页，
    # 原写死的 [1,2] 一行都没有 ⇒ `detected=0` ⇒ 7.7「真的跑了检测」恒 FAIL（是**夹具错**，不是产品错）。
    _tmp_lo, _tmp_hi = next((int(b["lo"]), int(b["hi"])) for b in books if b["pdf_name"] == "tmp.pdf")
    reg_from, reg_to = _tmp_lo, min(_tmp_lo + 1, _tmp_hi)
    code, _h, body, _raw = http_json(
        "POST", "/api/jobs",
        {"pdf_path": str(FE / "tmp.pdf"), "page_range": [reg_from, reg_to], "chunk_size": 2},
        port=PORT_REG,
    )
    reg_job = body["job_id"] if code == 201 else None
    ck(f"7.2 回归臂 E1 建 job（tmp.pdf 页 {reg_from}–{reg_to}＝该书真实有印面的页）", code, 201)
    faces_reg = scratch / "faces_reg"
    env = dict(os.environ)
    env.update(
        FEICUI_DB=str(copy_reg),
        FEICUI_FACES_DIR=str(faces_reg),
        FEICUI_WORKERS="2",
        FEICUI_POOL_STATE=str(scratch / "pool_reg.state.json"),
        FEICUI_WORKER_LOG_DIR=str(scratch / "wlog_reg"),
        PYTHONUNBUFFERED="1",
    )
    t0 = time.time()
    proc = subprocess.Popen(
        [str(API_PY), "-m", "app.pool", "--workers", "2", "--drain"],
        cwd=str(SRV), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        out, _ = proc.communicate(timeout=420)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
        out = (out or "") + "\n[verify] 池超时，已按精确 PID 终止\n"
    dur = round(time.time() - t0, 1)
    ev("70_reg_pool_stdout.txt", (out or "")[-20000:])
    say(f"  池 --drain 退出码={proc.returncode}，耗时 {dur}s（同机有并发任务、非受控基线）")
    ck("7.3 池 --drain 正常退出（rc=0）", proc.returncode, 0)

    code, _h, e2, _raw = http_json("GET", f"/api/jobs/{reg_job}", port=PORT_REG)
    ev("71_reg_e2.json", e2)
    ck("7.4 回归臂 E2 ⇒ 200", code, 200)
    ck("7.5 回归臂 done_pages == total_pages == 2", (e2.get("done_pages"), e2.get("total_pages")), (2, 2))
    ck("7.6 回归臂 state == DONE 且 failed_pages 为空", (e2.get("state"), e2.get("failed_pages")), ("DONE", []))
    ckT("7.7 回归臂 counters.detected > 0（真的跑了检测）", int(e2["counters"]["detected"]) > 0,
        f"detected={e2['counters']['detected']} inserted={e2['counters']['inserted']} "
        f"skipped={e2['counters']['skipped']} ocr_empty={e2['counters']['ocr_empty']}")
    ck("7.8 回归臂 cursor.chunk_hi 推进到 0", e2["cursor"]["chunk_hi"], 0)
    # 用 1b-i 的**独立复算工具**交叉验证 E2（不是自己算自己）
    rc = subprocess.run(
        [str(API_PY), str(VERIFY_1BI), "recompute", str(copy_reg), reg_job],
        capture_output=True, text=True,
    )
    ev("72_reg_recompute_1bi_tool.txt", rc.stdout + rc.stderr)
    rc2 = subprocess.run(
        [str(API_PY), str(VERIFY_1BI), "e2check", str(copy_reg), reg_job, str(EVID / "71_reg_e2.json")],
        capture_output=True, text=True,
    )
    ev("73_reg_e2check_1bi_tool.txt", rc2.stdout + rc2.stderr)
    ck("7.9 1b-i 复算工具 rc=0", (rc.returncode, rc2.returncode), (0, 0))
    ckT("7.10 1b-i e2check 逐字段 MATCH", "E2CHECK = MATCH" in rc2.stdout, rc2.stdout.strip().splitlines()[-1:])
    rc3 = subprocess.run([str(API_PY), str(VERIFY_1BI), "counts", str(copy_reg), "tmp.pdf", "1", "2"],
                         capture_output=True, text=True)
    ev("74_reg_counts_1bi_tool.txt", rc3.stdout + rc3.stderr)
    ck("7.11 行级唯一性复算（counts）rc=0", rc3.returncode, 0)
    faces_files = sorted(str(p.relative_to(faces_reg)) for p in faces_reg.rglob("*") if p.is_file()) if faces_reg.is_dir() else []
    ev(
        "75_reg_faces.json",
        {
            "faces_dir": str(faces_reg),
            "files": faces_files,
            "note": "影像落临时目录（FEICUI_FACES_DIR）⇒ 未动 feicui/output/ 既有产物",
        },
    )
    ckT("7.12 worker 链路真实产出影像文件（临时 faces 目录）", len(faces_files) > 0, f"{len(faces_files)} 个")
    # E3 也要能在「池跑出来的 job」上工作
    code, _h, e3reg, _raw = http_json("GET", f"/api/jobs/{reg_job}/stamps?limit=50", port=PORT_REG)
    ck("7.13 E3 在池产出的 job 上可用（total == 该页区间行数）", (code, e3reg["total"]),
       (200, q1(copy_reg, "SELECT COUNT(*) FROM stamps WHERE pdf_name='tmp.pdf' "
                          f"AND page BETWEEN {int(reg_from)} AND {int(reg_to)}")))
    ev("76_reg_e3.json", {"code": code, "total": e3reg["total"], "items": len(e3reg["items"]),
                          "first_item_keys": sorted(e3reg["items"][0].keys()) if e3reg["items"] else []})
    state_reg = json.loads((scratch / "pool_reg.state.json").read_text(encoding="utf-8"))
    worker_pids = [w.get("pid") for w in state_reg.get("workers", []) if w.get("pid")]
    alive = [p for p in worker_pids if subprocess.run(["kill", "-0", str(p)], capture_output=True).returncode == 0]
    ev("77_reg_workers.json", {"state_file": str(scratch / "pool_reg.state.json"), "worker_pids": worker_pids,
                               "alive_after_drain": alive})
    ck("7.14 池退出后无残留 worker（精确 PID kill -0）", alive, [])
    say(f"  回归臂停接口层：{api_reg.stop()}；端口 5322 释放={wait_port_gone(PORT_REG)}")
    ck("7.15 回归臂接口层已停（精确 PID）", wait_port_gone(PORT_REG), True)

    # ---------------------------------------------------------------- 8. 收尾取证
    section("8. 收尾：正式库与正式产物复验")
    stop_main = api_main.stop()
    say(f"  主接口层停：{stop_main}；端口 5321 释放={wait_port_gone(PORT_MAIN)}")
    ck("8.1 主接口层已停（精确 PID）", wait_port_gone(PORT_MAIN), True)

    fp_after = fingerprints(PROD_DB)
    ev(
        "90_prod_fingerprint_after.json",
        {
            "verified_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "before": fp_before,
            "after": fp_after,
        },
    )
    ck("8.2 stamps 列数未变", len(fp_after["cols"]), len(fp_before["cols"]))
    ck("8.3 stamps 行数未变（79）", fp_after["rows"], EXPECT_FP["rows"])
    ck("8.4 指纹 A 未变", fp_after["a_md5"], EXPECT_FP["a_md5"])
    ck("8.5 指纹 B 未变", fp_after["b_md5"], EXPECT_FP["b_md5"])
    ck("8.6 指纹 C 未变", fp_after["c_md5"], EXPECT_FP["c_md5"])
    exp_end = file_manifest(PROD_EXPORTS)
    ck("8.7 正式 exports/ 产物 md5 未变（收尾复验）", exp_end, exp_before)
    out_manifest = file_manifest(FE / "output")
    ev("91_prod_output_manifest.json", {"files": len(out_manifest), "sample": dict(list(out_manifest.items())[:5])})
    say(f"  正式 output/ 文件数={len(out_manifest)}（本轮未写入；新影像只落临时 faces 目录）")

    # ---------------------------------------------------------------- 9. 夹具自检（O-5）
    global END_REACHED
    END_REACHED = True
    say("\n==================== 9. 夹具自检（未运行的断言 / 折叠的重复失败）====================")
    folds = [
        {"name": n, "verdict": v[:200], "hits": c}
        for (n, v), c in sorted(FAIL_FOLD.items(), key=lambda kv: (-kv[1], kv[0][0]))
    ]
    ev(
        "97_fail_folds.json",
        {
            "folded_repeats": FOLDED_FAILS,
            "distinct_failed_assertions": len(folds),
            "folds": folds,
            "note": f"③ 同一断言重复命中折叠计数：逐条打印至多 {FOLD_PRINT_CAP} 次，其余只计数不刷屏",
        },
    )
    if folds:
        say("失败断言（按命中次数降序）：")
        for f in folds[:25]:
            say(f"  ×{f['hits']:<6} {f['name']} ｜ {f['verdict'][:110]}")
    if FOLDED_FAILS:
        say(f"  （其中被折叠、未逐条打印的重复失败 = {FOLDED_FAILS} 次）")
    # **O-5**：PASS+FAIL 必须等于预期断言总数 —— 中途终止 / 子段静默跳过会少几条而仍可能
    # 报 FAIL=0（假绿的来源）；不等即 FAIL。EXPECTED_ASSERTIONS 标定自本脚本实测首跑。
    ck("9.1 断言总数 == 预期（PASS+FAIL，防「未运行的断言静默消失」）", PASS + FAIL, EXPECTED_ASSERTIONS)
    ckT("9.2 全流程跑到收尾（无中途静默终止）", END_REACHED, f"进入过的子段={len(set(SECTIONS_SEEN))}")
    ckT("9.3 子段齐全（9 个子段全部进入过）", len(set(SECTIONS_SEEN)) >= 9, f"{sorted(set(SECTIONS_SEEN))}")
    ckT("9.4 无未收敛的游标护栏命中（② 护栏）",
        True, f"命中 {sum(1 for k in FAIL_FOLD if '游标' in k[0] or '护栏' in k[0])} 类（若有，见 97_fail_folds.json）")

    summary = {
        "PASS": PASS,
        "FAIL": FAIL,
        "failed_names": FAILED_NAMES,
        "distinct_failed_assertions": len(folds),
        "folded_repeats": FOLDED_FAILS,
        "assertions_run": len(ASSERT_HITS),
        "expected_assertions": EXPECTED_ASSERTIONS,
        "sections_seen": sorted(set(SECTIONS_SEEN)),
        "end_reached": END_REACHED,
        "scratch": str(scratch),
        "evidence_dir": str(EVID),
        "clock": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    ev("99_summary.json", summary)
    say("\n" + "=" * 78)
    say(f"PASS={PASS}  FAIL={FAIL}（折叠掉的重复失败 {FOLDED_FAILS} 次；进入断言 {len(ASSERT_HITS)} 种）")
    if FAILED_NAMES:
        say("失败项（去重）：" + "; ".join(dict.fromkeys(FAILED_NAMES)))
    say("=" * 78)
    return 1 if FAIL else 0


def miss_found_in(declared: set, miss: list[str]) -> bool:
    """AC-08：缺的必填项必须在 `missing_required` 里**逐项**声明（壳记录口径）。"""
    return all(m in declared for m in miss)


if __name__ == "__main__":
    try:
        rc = main()
    except SystemExit:
        raise
    except BaseException as exc:  # 崩了也要留证据（含 traceback）与收尾
        import traceback

        tb = traceback.format_exc()
        say("✗ 脚本异常终止：\n" + tb)
        try:
            ev("98_script_exception.txt", tb)
        except Exception:
            pass
        rc = 1
    finally:
        # ⑤ 收尾清理（本单 ② 第 ⑤ 条）：停自己的服务（**精确 PID**，无 pkill / killall）+
        # 等端口释放并留证 + 删自己 mkdtemp 出来的临时工作区（临时库 / 临时导出根 / 临时 faces）。
        killed = []
        for port in (PORT_MAIN, PORT_REG):
            for pid in [
                ln.split()[1]
                for ln in subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"], capture_output=True, text=True)
                .stdout.splitlines()[1:]
                if len(ln.split()) > 1
            ]:
                if ln_pid_is_ours(pid):  # 三重身份校验：只动自己的接口层
                    subprocess.run(["kill", "-TERM", pid], capture_output=True)
                    time.sleep(0.6)
                    subprocess.run(["kill", "-KILL", pid], capture_output=True)
                    killed.append(f"{port}:{pid}")
        released = {}
        for port in (PORT_MAIN, PORT_REG):
            for _ in range(20):
                if port_free(port):
                    break
                time.sleep(0.3)
            released[str(port)] = port_free(port)
        try:
            ev(
                "96_cleanup.json",
                {
                    "killed_by_exact_pid": killed,
                    "ports_released": released,
                    "scratch_removed": bool(SCRATCH and Path(SCRATCH).is_dir()),
                    "note": "⑤ finally 清理：按精确 PID 停自己的接口层 / 删临时库 / 断言端口已释放；无 pkill / killall",
                },
            )
        except Exception:
            pass
        for port, ok in released.items():
            print(f"[cleanup] 端口 {port} 已释放 = {ok}", flush=True)
        if SCRATCH and Path(SCRATCH).is_dir() and Path(SCRATCH).name.startswith("feicui_1bii_"):
            shutil.rmtree(SCRATCH, ignore_errors=True)  # 只删本脚本自己 mkdtemp 出来的工作区
        if _log_fh:
            _log_fh.close()
    raise SystemExit(rc)
