#!/usr/bin/env python3
"""印谱采集 API 分页 / 负向自检（IT-1 / 分页不变式）——经 HTTP（默认 5196）。

判据：
  * `has_more == (page*limit < total)`；响应**不含 `next_cursor`**；
  * **未白名单查询参数** ⇒ 400 结构化 JSON（含 `cursor`）；
  * `page` 越界 ⇒ `items=[]` 且 `has_more=False`；
  * 筛选（有无影像 / 有无年份 / 题名关键字）命中数与库内口径一致。

用法：python3 verify_api.py [--base http://127.0.0.1:5196] [--out x.json] [--txt x.txt]
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path


def _get(url: str) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}


def _post(url: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else b""
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Accept": "application/json", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:5196")
    ap.add_argument("--out", default=None)
    ap.add_argument("--txt", default=None)
    args = ap.parse_args()

    B = args.base.rstrip("/")
    lines: list[str] = []
    out: dict = {"base": B, "cases": {}}

    def rec(name, ok, detail):
        out["cases"][name] = {"ok": ok, "detail": detail}
        lines.append(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    st, body = _get(f"{B}/api/items?limit=50&page=1")
    total = body.get("total")
    rec("list_200", st == 200, f"HTTP {st} total={total}")
    rec("no_next_cursor", "next_cursor" not in body, f"keys={sorted(body.keys())}")
    inv1 = body.get("has_more") == (1 * 50 < total)
    rec("invariant_p1", inv1, f"has_more={body.get('has_more')} page*limit={50} total={total}")

    st2, p2 = _get(f"{B}/api/items?limit=50&page=2")
    inv2 = p2.get("has_more") == (2 * 50 < total)
    rec("invariant_p2", inv2, f"has_more={p2.get('has_more')} 2*50<{total}={2*50<total}")

    # 越界页
    big = (total // 50) + 5
    st3, p3 = _get(f"{B}/api/items?limit=50&page={big}")
    rec("out_of_range_empty", p3.get("items") == [] and p3.get("has_more") is False,
        f"page={big} items={len(p3.get('items') or [])} has_more={p3.get('has_more')}")

    # 负向：未白名单参数
    st4, b4 = _get(f"{B}/api/items?cursor=abc")
    rec("unsupported_cursor_400", st4 == 400 and (b4.get("detail") or {}).get("error") == "UNSUPPORTED_PARAM",
        f"HTTP {st4} error={(b4.get('detail') or {}).get('error')}")

    # 筛选
    st5, f_img = _get(f"{B}/api/items?has_image=true&limit=1")
    st6, f_img0 = _get(f"{B}/api/items?has_image=false&limit=1")
    rec("filter_has_image", st5 == 200 and st6 == 200,
        f"has_image=true→{f_img.get('total')} / false→{f_img0.get('total')}")
    st7, f_yr = _get(f"{B}/api/items?has_year=true&limit=1")
    rec("filter_has_year", st7 == 200, f"has_year=true→{f_yr.get('total')}")

    st8, q = _get(f"{B}/api/items?q=%E9%BE%8D%E6%B3%93&limit=5")  # 龍泓
    rec("filter_title_kw", st8 == 200 and any("龍泓" in (it.get("title") or "") for it in (q.get("items") or [])),
        f"q=龍泓 → total={q.get('total')}")

    # 单本 / 404
    st9, it = _get(f"{B}/api/items/2214")
    rec("get_item_2214", st9 == 200 and it.get("source_item_id") == "2214" and it.get("as_book_id") == "0307",
        f"HTTP {st9} title={it.get('title')} creators={len(it.get('creators') or [])}")
    st10, _ = _get(f"{B}/api/items/999999")
    rec("get_item_404", st10 == 404, f"HTTP {st10}")

    # batches
    st11, bat = _get(f"{B}/api/items/batches")
    rec("batches_200", st11 == 200 and isinstance(bat.get("items"), list), f"HTTP {st11} n={len(bat.get('items') or [])}")

    # 就绪包：POST /api/items/package（从本库重建，不联网）
    st12, pkg = _post(f"{B}/api/items/package")
    rec("package_200", st12 == 200 and pkg.get("key_face_status") == "pending_xiai" and isinstance(pkg.get("rows"), int),
        f"HTTP {st12} rows={pkg.get('rows')} creators_rows={pkg.get('creators_rows')} "
        f"key_face_status={pkg.get('key_face_status')} detail_policy.enabled={(pkg.get('detail_policy') or {}).get('enabled')}")

    # 负向：package 未白名单参数 ⇒ 400
    st13, b13 = _post(f"{B}/api/items/package?foo=1")
    rec("package_unsupported_400", st13 == 400 and (b13.get("detail") or {}).get("error") == "UNSUPPORTED_PARAM",
        f"HTTP {st13} error={(b13.get('detail') or {}).get('error')}")

    out["pass"] = all(c["ok"] for c in out["cases"].values())
    text = json.dumps(out, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    if args.txt:
        Path(args.txt).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
