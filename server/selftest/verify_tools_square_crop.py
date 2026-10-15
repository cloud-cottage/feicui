#!/usr/bin/env python
"""`POST /api/tools/square-crop` 自测（**真跑**，逐条留证）——Kong / 单「square-crop」。

运行（**API 层解释器**，无需 cv2：所有图像编解码都借 worker 解释器）：
    cd /Users/kevin/bistro/feicui/server
    ./.venv/bin/python selftest/verify_tools_square_crop.py --base-url http://127.0.0.1:5201

六条自测（与派单逐条对应；全 PASS ⇒ exit 0，任一 FAIL ⇒ exit 1）：
  1. **真实影像 200**：把工程内真实影像（`output/faces/TMP/p0013_00.webp` 与
     `output/古玺汇编 文物出版社 罗福颐  ok/p24_0.webp`）当上传图送入端点；
  2. **方形断言**：返回影像 `width == height`、`mime == image/webp`、`image_base64` 解出的字节
     `sha256` 与声明一致、**且能被 `cv2.imdecode` 解回**、解回尺寸与声明 `width/height` 逐字相同；
  3. **顺序/形状断言**：`count == len(candidates)`、`idx` 0..n-1、候选按**面积降序**、
     `square` 为正方形且落在 `source` 图内；
  4. **零 DB 写证据**：调用前后 `stamps` 行数与**内容指纹**（canonical JSON / md5，口径与
     `ops/prod_migrate_fingerprint.py` 的 B 口径同构）不变；**禁用库文件 md5**；
  5. **错误路径**：不传文件 ⇒ 400；传非图片（文本）⇒ 400；传纯白图 ⇒ **422 `NO_CANDIDATE`**；
     一律**结构化 JSON**（断言 content-type 是 JSON，不是 HTML 错误页）；
  6. **CORS 实证**：`Origin: http://127.0.0.1:5163` 与 `http://localhost:5163` 的 `OPTIONS` 预检
     与真实 POST 都回 `Access-Control-Allow-Origin`；**未允许的 origin 不回**（证明没放开 `*`）。

留证：把每次请求的状态码 + 关键响应头 + 响应体（截断）落成文本文件（默认
`<feicui>/ops/kong_square_crop_selftest_raw.txt`，仅追加本单证据文件，不碰其它目录）。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
FEICUI_ROOT = SERVER_DIR.parent
WORKER_PY = FEICUI_ROOT / "venv" / "bin" / "python"
DEFAULT_DB = FEICUI_ROOT / "yinpu.db"
PATH_EP = "/api/tools/square-crop"

SAMPLE_A = FEICUI_ROOT / "output" / "faces" / "TMP" / "p0013_00.webp"
SAMPLE_B = FEICUI_ROOT / "output" / "古玺汇编 文物出版社 罗福颐  ok" / "p24_0.webp"

ORIGIN_OK = "http://127.0.0.1:5163"
ORIGIN_OK2 = "http://localhost:5163"
ORIGIN_BAD = "http://127.0.0.1:59999"

_results: list[dict] = []
_transcript: list[str] = []


def log(line: str = "") -> None:
    print(line)
    _transcript.append(line)


def check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append({"check": name, "ok": bool(ok), "detail": detail})
    log(f"  [{'PASS' if ok else 'FAIL'}] {name} — {detail}")
    return bool(ok)


# --------------------------------------------------------------------------- HTTP（纯 stdlib）
def build_multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> tuple[str, bytes]:
    boundary = "----feicuiSelftest" + os.urandom(8).hex()
    out: list[bytes] = []
    for k, v in fields.items():
        out.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8")
        )
    for k, (fn, data, ctype) in files.items():
        out.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{fn}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n".encode("utf-8")
            + data
            + b"\r\n"
        )
    out.append(f"--{boundary}--\r\n".encode("utf-8"))
    return f"multipart/form-data; boundary={boundary}", b"".join(out)


def http(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read()


def post_image(
    base: str,
    data: bytes,
    *,
    filename: str = "sample.webp",
    ctype: str = "image/webp",
    fields: dict[str, str] | None = None,
    origin: str | None = None,
) -> tuple[int, dict[str, str], bytes]:
    ct, body = build_multipart(fields or {}, {"image": (filename, data, ctype)})
    headers = {"Content-Type": ct}
    if origin:
        headers["Origin"] = origin
    return http("POST", base + PATH_EP, headers=headers, body=body)


def post_no_file(base: str, origin: str | None = None) -> tuple[int, dict[str, str], bytes]:
    ct, body = build_multipart({"pad_ratio": "0.15"}, {})
    headers = {"Content-Type": ct}
    if origin:
        headers["Origin"] = origin
    return http("POST", base + PATH_EP, headers=headers, body=body)


def preflight(base: str, origin: str) -> tuple[int, dict[str, str], bytes]:
    return http(
        "OPTIONS",
        base + PATH_EP,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )


def dump(method: str, url: str, status: int, hdrs: dict[str, str], body: bytes, note: str = "") -> None:
    keys = [
        "content-type",
        "access-control-allow-origin",
        "access-control-allow-methods",
        "access-control-allow-headers",
        "allow",
        "vary",
        "content-length",
    ]
    log(f"    {note}")
    log(f"    → {method} {url}")
    log(f"    ← {status}")
    for k in keys:
        if k in hdrs:
            log(f"      {k}: {hdrs[k]}")
    if body:
        try:
            parsed = json.loads(body.decode("utf-8"))
            shown = dict(parsed)
            for c in shown.get("candidates") or []:
                if "image_base64" in c:
                    c["image_base64"] = f"<{len(c['image_base64'])} chars b64>"
            txt = json.dumps(shown, ensure_ascii=False)[:900]
        except Exception:
            txt = body[:300].decode("utf-8", "replace")
        log(f"      body: {txt}")


# --------------------------------------------------------------------------- 借 worker 解释器做图像活
def worker_eval(snippet: str, stdin_bytes: bytes | None = None) -> str:
    """在 worker 解释器里跑一小段 python（本层无 cv2/numpy），stdout 原样返回。"""
    proc = subprocess.run(
        [str(WORKER_PY), "-c", snippet],
        input=stdin_bytes if stdin_bytes is not None else b"",
        capture_output=True,
        cwd=str(FEICUI_ROOT),
        timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"worker 解释器失败：{proc.stderr.decode('utf-8', 'replace')[-500:]}")
    return proc.stdout.decode("utf-8", "replace").strip()


_SNIPPET_DIMS = (
    "import sys,base64,hashlib,cv2,numpy as np;"
    "b=base64.b64decode(sys.stdin.buffer.read());"
    "im=cv2.imdecode(np.frombuffer(b,dtype=np.uint8),cv2.IMREAD_UNCHANGED);"
    "print('NONE' if im is None else f'{im.shape[1]}x{im.shape[0]}')"
)


def decode_dims(data: bytes) -> str:
    """用 cv2 把字节解回，返回 `WxH`（解不出来返回 `NONE`）。"""
    return worker_eval(_SNIPPET_DIMS, base64.b64encode(data))


def make_white_png(path: Path, side: int = 200) -> None:
    snippet = (
        "import cv2,numpy as np,sys;"
        f"cv2.imwrite(sys.argv[1], np.full(({side},{side},3),255,dtype=np.uint8))"
    )
    proc = subprocess.run(
        [str(WORKER_PY), "-c", snippet, str(path)], capture_output=True, cwd=str(FEICUI_ROOT), timeout=120
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace")[-500:])


def make_two_red_squares_png(path: Path, big: int = 220, small: int = 120) -> None:
    """合成图：白底两枚**大小不同**的红色实心方块（用于验证「候选按面积降序」的排序口径）。"""
    snippet = (
        "import cv2,numpy as np,sys;"
        "im=np.full((400,400,3),255,dtype=np.uint8);"
        f"cv2.rectangle(im,(20,20),(20+{big},20+{big}),(0,0,220),-1);"   # BGR 红（HSV 落在 hsv_high/low 口径内）
        f"cv2.rectangle(im,(250,250),(250+{small},250+{small}),(0,0,220),-1);"
        "cv2.imwrite(sys.argv[1], im)"
    )
    proc = subprocess.run(
        [str(WORKER_PY), "-c", snippet, str(path)], capture_output=True, cwd=str(FEICUI_ROOT), timeout=120
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace")[-500:])


# --------------------------------------------------------------------------- 内容指纹（只读）
def stamps_fingerprint(db_path: Path) -> dict:
    """`stamps` 行数 + canonical-JSON 内容指纹（**禁用库文件 md5**）。

    口径与 `ops/prod_migrate_fingerprint.py` 的 **B canon** 同构：每行 `{列名: 值}` 的
    JSON（`ensure_ascii=False, sort_keys=True, separators=(',',':')`）按 `id` 升序、`\\n` 连接、末尾补 `\\n`。
    另外给出 `id<=79` 子集指纹（派单点名的「原 79 行」）与 A raw 口径作交叉校验。
    """
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        names = [r[1] for r in conn.execute("PRAGMA table_info(stamps)")]
        rows = list(conn.execute("SELECT * FROM stamps ORDER BY id"))
        canon = [
            json.dumps({n: r[n] for n in names}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for r in rows
        ]
        raw = ["|".join("" if r[n] is None else str(r[n]) for n in names) for r in rows]
        head = [(r, c) for r, c in zip(rows, canon) if int(r["id"]) <= 79]
        return {
            "rows": len(rows),
            "md5_B_canon": hashlib.md5(("\n".join(canon) + "\n").encode("utf-8")).hexdigest(),
            "sha256_B_canon": hashlib.sha256(("\n".join(canon) + "\n").encode("utf-8")).hexdigest(),
            "md5_A_raw": hashlib.md5(("\n".join(raw) + "\n").encode("utf-8")).hexdigest(),
            "rows_le79": len(head),
            "md5_B_canon_le79": hashlib.md5(
                ("\n".join(c for _, c in head) + "\n").encode("utf-8")
            ).hexdigest(),
        }
    finally:
        conn.close()


# --------------------------------------------------------------------------- 断言辅助
def sorted_by_area_desc(cands: list[dict]) -> bool:
    areas = [c.get("area") for c in cands]
    if any(a is None for a in areas):
        return False
    return all(areas[i] >= areas[i + 1] for i in range(len(areas) - 1))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:5201", help="待测实例（临时端口实例）")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="用于「零 DB 写」指纹的库（默认正式库，只读打开）")
    ap.add_argument(
        "--evidence-out",
        default=str(FEICUI_ROOT / "ops" / "kong_square_crop_selftest_raw.txt"),
    )
    ap.add_argument("--label", default="", help="本次运行的标签（写进证据文件抬头）")
    ap.add_argument("--skip-cors-sensitive", action="store_true", help="（保留位，无实际用途）")
    args = ap.parse_args(argv)

    base = args.base_url.rstrip("/")
    db_path = Path(args.db).expanduser()
    log("=" * 100)
    log(f"square-crop 自测｜label={args.label}｜base={base}｜db={db_path}｜{__import__('datetime').datetime.now().isoformat()}")
    log(f"worker 解释器 = {WORKER_PY}（存在＝{WORKER_PY.is_file()}）；本层解释器 = {sys.executable}")
    log("=" * 100)

    # ---------- 输入样本 ----------
    samples = {}
    for tag, p in (("A:p0013_00.webp", SAMPLE_A), ("B:古玺汇编 p24_0.webp", SAMPLE_B)):
        if p.is_file():
            samples[tag] = (p, p.read_bytes())
            log(f"样本 {tag}：{p}（{len(samples[tag][1])} B，cv2 解回 {decode_dims(samples[tag][1])}）")
        else:
            log(f"样本 {tag}：**文件不存在**（跳过）{p}")
    if not samples:
        check("样本存在", False, "两枚样本影像都不存在，无法自测")
        return 1
    check("样本存在", True, f"{len(samples)} 枚真实影像")

    tmpdir = Path(tempfile.mkdtemp(prefix="feicui_square_selftest_"))
    white = tmpdir / "white.png"
    make_white_png(white, 200)
    log(f"造纯白图：{white}（200×200，cv2 解回 {decode_dims(white.read_bytes())}）")
    two = tmpdir / "two_red_squares.png"
    make_two_red_squares_png(two)
    log(f"造双红方块合成图：{two}（400×400，cv2 解回 {decode_dims(two.read_bytes())}）")

    # ---------- 零 DB 写：调用前指纹 ----------
    fp_before = stamps_fingerprint(db_path)
    log(f"调用前 stamps 指纹：rows={fp_before['rows']} md5_B={fp_before['md5_B_canon']} "
        f"rows<=79={fp_before['rows_le79']} md5_B(<=79)={fp_before['md5_B_canon_le79']}")

    # ---------- ① 真实影像 200 ＋ ② 方形 / ③ 顺序 ----------
    log("\n---- ① 真实影像 200（含 ② 方形断言 / ③ 顺序断言）----")
    for tag, (path, data) in samples.items():
        status, hdrs, body = post_image(base, data, filename=path.name, fields={"pad_ratio": "0.15"})
        dump("POST", base + PATH_EP, status, hdrs, body, note=f"上传 {tag}（{path.name}）")
        if not check(f"{tag} 状态码 200", status == 200, f"实际 {status}"):
            continue
        j = json.loads(body.decode("utf-8"))
        check(f"{tag} ok=true", j.get("ok") is True, f"ok={j.get('ok')}")
        cands = j.get("candidates") or []
        check(
            f"{tag} count 与 candidates 长度一致",
            j.get("count") == len(cands) and len(cands) >= 1,
            f"count={j.get('count')} len={len(cands)}",
        )
        src_w, src_h = j.get("source", {}).get("width"), j.get("source", {}).get("height")
        in_w, in_h = decode_dims(data).split("x")
        check(
            f"{tag} source 与原图尺寸一致",
            (src_w, src_h) == (int(in_w), int(in_h)),
            f"source={src_w}x{src_h} 原图={in_w}x{in_h}",
        )
        check(f"{tag} idx 0..n-1", [c.get("idx") for c in cands] == list(range(len(cands))),
              f"idx={[c.get('idx') for c in cands]}")
        check(f"{tag} 候选按面积降序", sorted_by_area_desc(cands),
              f"area={[round(c.get('area', -1), 1) for c in cands]}")

        first = cands[0]
        log(f"    第一个候选：{json.dumps({k: v for k, v in first.items() if k != 'image_base64'}, ensure_ascii=False)}")
        check(f"{tag} 第一候选 mime=image/webp", first.get("mime") == "image/webp", str(first.get("mime")))
        check(
            f"{tag} 第一候选 width==height（正方形）",
            first.get("width") == first.get("height") and int(first.get("width") or 0) > 0,
            f"{first.get('width')}x{first.get('height')}",
        )
        x1, y1, x2, y2 = first.get("square") or (0, 0, 0, 0)
        check(
            f"{tag} square 是正方形且边长==side",
            (x2 - x1) == (y2 - y1) == first.get("side"),
            f"square={first.get('square')} side={first.get('side')}",
        )
        check(
            f"{tag} square 落在原图内",
            0 <= x1 and 0 <= y1 and x2 <= src_w and y2 <= src_h,
            f"square={first.get('square')} source={src_w}x{src_h}",
        )
        raw_bytes = base64.b64decode(first.get("image_base64") or "")
        check(
            f"{tag} image_base64 无 data URL 前缀且 sha256 自洽",
            not (first.get("image_base64") or "").startswith("data:"),
            f"b64 前 16 字符={ (first.get('image_base64') or '')[:16] }",
        )
        check(
            f"{tag} sha256 == WebP 字节 sha256",
            hashlib.sha256(raw_bytes).hexdigest() == first.get("sha256"),
            f"声明={first.get('sha256')} 实测={hashlib.sha256(raw_bytes).hexdigest()}",
        )
        dims = decode_dims(raw_bytes)
        check(
            f"{tag} cv2.imdecode 解回且尺寸与声明一致",
            dims == f"{first.get('width')}x{first.get('height')}",
            f"解回={dims} 声明={first.get('width')}x{first.get('height')}",
        )
        check(
            f"{tag} WebP magic（RIFF/WEBP）",
            raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP",
            f"head={raw_bytes[:12]!r}",
        )

    # ---------- ③b 多候选排序（合成两枚大小不同的红方块 ⇒ 验证「按面积降序」）----------
    log("\n---- ③b 多候选排序（合成图：220×220 与 120×120 两枚红方块）----")
    st, hd, bd = post_image(base, two.read_bytes(), filename="two_red_squares.png", ctype="image/png")
    dump("POST", base + PATH_EP, st, hd, bd, note="合成双红方块图")
    if check("双红方块 状态码 200", st == 200, f"实际 {st}"):
        j = json.loads(bd.decode())
        cs = j.get("candidates") or []
        check("双红方块 count==2", j.get("count") == 2 and len(cs) == 2, f"count={j.get('count')} len={len(cs)}")
        check("双红方块 候选按面积降序（idx 0 是大的）",
              sorted_by_area_desc(cs) and cs[0]["area"] > cs[1]["area"],
              f"area={[round(c['area'], 1) for c in cs]}")
        check("双红方块 idx 0..n-1", [c["idx"] for c in cs] == list(range(len(cs))),
              f"idx={[c['idx'] for c in cs]}")
        check("双红方块 每个候选 square 均为正方形且边长==side",
              all((c["square"][2] - c["square"][0]) == (c["square"][3] - c["square"][1]) == c["side"] for c in cs),
              f"side={[c['side'] for c in cs]}")

    # ---------- 额外：quality / max_side 参数确实生效 ----------
    log("\n---- 附：quality=80 / max_side=100 生效性（同一张图）----")
    tag0, (path0, data0) = next(iter(samples.items()))
    s_d, h_d, b_d = post_image(base, data0, filename=path0.name, fields={"quality": "80"})
    s_m, h_m, b_m = post_image(base, data0, filename=path0.name, fields={"max_side": "100"})
    s_q, h_q, b_q = post_image(base, data0, filename=path0.name, fields={"quality": "95"})
    if s_d == 200 and s_q == 200 and s_m == 200:
        jd, jq, jm = (json.loads(x.decode()) for x in (b_d, b_q, b_m))
        dump("POST", base + PATH_EP, s_d, h_d, b_d, note="quality=80")
        dump("POST", base + PATH_EP, s_m, h_m, b_m, note="max_side=100")
        check("quality=80 的 WebP 字节数 < quality=95", len(base64.b64decode(jd["candidates"][0]["image_base64"]))
              < len(base64.b64decode(jq["candidates"][0]["image_base64"])),
              f"q80={len(base64.b64decode(jd['candidates'][0]['image_base64']))}B "
              f"q95={len(base64.b64decode(jq['candidates'][0]['image_base64']))}B")
        check("params_used.quality 如实回传", jd["params_used"]["quality"] == 80, str(jd["params_used"]["quality"]))
        m0 = jm["candidates"][0]
        check("max_side=100 ⇒ 输出 100×100（仍正方形）", (m0["width"], m0["height"]) == (100, 100),
              f"{m0['width']}x{m0['height']} side={m0['side']}")
        check("max_side=100 ⇒ params_used.max_side=100", jm["params_used"]["max_side"] == 100,
              str(jm["params_used"]["max_side"]))
    else:
        check("quality/max_side 三连调用均 200", False, f"{s_d}/{s_q}/{s_m}")

    # ---------- ⑤ 错误路径 ----------
    log("\n---- ⑤ 错误路径（400 / 400 / 422，且一律结构化 JSON）----")
    st, hd, bd = post_no_file(base)
    dump("POST", base + PATH_EP, st, hd, bd, note="不传文件（只有 pad_ratio 文本字段）")
    check("缺 image ⇒ 400", st == 400, f"实际 {st}")
    check("缺 image 的响应是 JSON", hd.get("content-type", "").startswith("application/json"),
          str(hd.get("content-type")))
    if hd.get("content-type", "").startswith("application/json"):
        check("缺 image 的 reason 可读", bool(json.loads(bd.decode()).get("reason")),
              str(json.loads(bd.decode()).get("reason"))[:120])

    st, hd, bd = post_image(base, "这不是图片，只是一段文本\n".encode("utf-8"), filename="note.txt", ctype="text/plain")
    dump("POST", base + PATH_EP, st, hd, bd, note="传非图片（text/plain）")
    check("非图片 ⇒ 400", st == 400, f"实际 {st}")
    check("非图片的响应是 JSON", hd.get("content-type", "").startswith("application/json"),
          str(hd.get("content-type")))

    st, hd, bd = post_image(base, white.read_bytes(), filename="white.png", ctype="image/png")
    dump("POST", base + PATH_EP, st, hd, bd, note="传纯白图（无红掩膜 ⇒ 无候选）")
    check("纯白图 ⇒ 422", st == 422, f"实际 {st}")
    if st == 422:
        j = json.loads(bd.decode())
        check("纯白图 reason == NO_CANDIDATE", j.get("reason") == "NO_CANDIDATE", str(j.get("reason")))
    check("纯白图的响应是 JSON（非 HTML 错误页）",
          hd.get("content-type", "").startswith("application/json"), str(hd.get("content-type")))

    # ---------- ⑥ CORS ----------
    log("\n---- ⑥ CORS 实证（预检 + 真实 POST；含未允许 origin 的负例）----")
    for origin in (ORIGIN_OK, ORIGIN_OK2):
        st, hd, bd = preflight(base, origin)
        dump("OPTIONS", base + PATH_EP, st, hd, bd, note=f"预检 Origin={origin}")
        check(f"预检 {origin} ⇒ 200", st == 200, f"实际 {st}")
        check(f"预检 {origin} 回 Access-Control-Allow-Origin: {origin}",
              hd.get("access-control-allow-origin") == origin, str(hd.get("access-control-allow-origin")))
        check(f"预检 {origin} 允许 POST", "POST" in (hd.get("access-control-allow-methods") or ""),
              str(hd.get("access-control-allow-methods")))

    tag0, (path0, data0) = next(iter(samples.items()))
    st, hd, bd = post_image(base, data0, filename=path0.name, origin=ORIGIN_OK)
    dump("POST", base + PATH_EP, st, hd, bd, note=f"真实 POST 带 Origin={ORIGIN_OK}")
    check(f"真实 POST 带 Origin={ORIGIN_OK} ⇒ 200 且回 ACAO",
          st == 200 and hd.get("access-control-allow-origin") == ORIGIN_OK,
          f"status={st} ACAO={hd.get('access-control-allow-origin')}")

    st, hd, bd = preflight(base, ORIGIN_BAD)
    dump("OPTIONS", base + PATH_EP, st, hd, bd, note=f"未允许 origin 负例 Origin={ORIGIN_BAD}")
    check(f"未允许 origin（{ORIGIN_BAD}）不回 ACAO（证明未放开 `*`）",
          hd.get("access-control-allow-origin") is None, str(hd.get("access-control-allow-origin")))

    # ---------- ⑦ 独立客户端复核（curl -F：另一套 multipart 编码器，佐证本端点的解析不挑客户端）----------
    log("\n---- ⑦ 独立客户端复核：curl -F（另一套 multipart 编码器；带 Origin）----")
    curl = shutil.which("curl")
    if not curl:
        log("    本机无 curl，跳过该附加项（不计入 FAIL）")
    else:
        tag0, (path0, data0) = next(iter(samples.items()))
        hdr_file = tmpdir / "curl_headers.txt"
        body_file = tmpdir / "curl_body.json"
        proc = subprocess.run(
            [
                curl, "-s", "-X", "POST", base + PATH_EP,
                "-H", f"Origin: {ORIGIN_OK}",
                "-F", f"image=@{path0};type=image/webp",
                "-F", "pad_ratio=0.15",
                "-D", str(hdr_file),
                "-o", str(body_file),
            ],
            capture_output=True,
            timeout=180,
        )
        raw_headers = hdr_file.read_text(encoding="utf-8") if hdr_file.is_file() else ""
        cbody = body_file.read_bytes() if body_file.is_file() else b""
        log(f"    curl rc={proc.returncode}")
        for ln in raw_headers.strip().splitlines():
            log(f"      {ln}")
        try:
            cj = json.loads(cbody.decode("utf-8"))
            shown = dict(cj)
            for c in shown.get("candidates") or []:
                c["image_base64"] = f"<{len(c['image_base64'])} chars b64>"
            log(f"      body: {json.dumps(shown, ensure_ascii=False)[:600]}")
        except Exception:
            log(f"      body(raw): {cbody[:300]!r}")
        check("curl -F 上传 ⇒ HTTP/1.1 200", " 200 " in raw_headers.splitlines()[0] if raw_headers else False,
              raw_headers.splitlines()[0] if raw_headers else "（无响应头）")
        check("curl -F 上传 ⇒ 回 ACAO 5163",
              f"access-control-allow-origin: {ORIGIN_OK}".lower() in raw_headers.lower(),
              f"headers 含 ACAO={f'access-control-allow-origin: {ORIGIN_OK}'.lower() in raw_headers.lower()}")
        try:
            cj2 = json.loads(cbody.decode("utf-8"))
            c0 = (cj2.get("candidates") or [{}])[0]
            check("curl 路径的候选同样满足 正方形 + mime",
                  c0.get("width") == c0.get("height") == c0.get("side") and c0.get("mime") == "image/webp",
                  f"side={c0.get('side')} {c0.get('width')}x{c0.get('height')} {c0.get('mime')} sha256={str(c0.get('sha256'))[:16]}…")
        except Exception as exc:  # noqa: BLE001
            check("curl 路径响应可解析", False, f"{exc!r}")

    # ---------- 零 DB 写：调用后指纹 ----------
    fp_after = stamps_fingerprint(db_path)
    log(f"\n调用后 stamps 指纹：rows={fp_after['rows']} md5_B={fp_after['md5_B_canon']} "
        f"rows<=79={fp_after['rows_le79']} md5_B(<=79)={fp_after['md5_B_canon_le79']}")
    check("stamps 行数不变", fp_before["rows"] == fp_after["rows"],
          f"{fp_before['rows']} -> {fp_after['rows']}")
    check("stamps 内容指纹（B canon / md5）不变", fp_before["md5_B_canon"] == fp_after["md5_B_canon"],
          f"{fp_before['md5_B_canon']} -> {fp_after['md5_B_canon']}")
    check("stamps A raw 指纹不变", fp_before["md5_A_raw"] == fp_after["md5_A_raw"],
          f"{fp_before['md5_A_raw']} -> {fp_after['md5_A_raw']}")
    check("原 79 行（id<=79）子集指纹不变",
          fp_before["rows_le79"] == fp_after["rows_le79"]
          and fp_before["md5_B_canon_le79"] == fp_after["md5_B_canon_le79"],
          f"rows={fp_after['rows_le79']} md5={fp_before['md5_B_canon_le79']} -> {fp_after['md5_B_canon_le79']}")

    # ---------- 汇总 ----------
    npass = sum(1 for r in _results if r["ok"])
    nfail = len(_results) - npass
    summary = {
        "label": args.label,
        "base_url": base,
        "db": str(db_path),
        "checks_total": len(_results),
        "checks_pass": npass,
        "checks_fail": nfail,
        "failed": [r for r in _results if not r["ok"]],
        "stamps_fingerprint_before": fp_before,
        "stamps_fingerprint_after": fp_after,
    }
    log("\n" + "=" * 100)
    log(json.dumps({k: v for k, v in summary.items() if k != "failed"}, ensure_ascii=False, indent=2))
    log(f"结论：{'ALL PASS' if nfail == 0 else f'{nfail} 条 FAIL'}（共 {len(_results)} 条断言）")
    log("=" * 100)

    out = Path(args.evidence_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(_transcript) + "\n")
    print(f"留证已写入：{out}")
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
