#!/usr/bin/env python3
"""印人 API 分页自检（机械断言）：`GET /api/persons` 的分页口径（**独立于 `verify_delivery_seam.py`**）。

**背景（本单缺陷）**：旧实现回吐 `{items, page, limit, total, has_more, next_cursor}` 且
`has_more=true` 而 `next_cursor=null`（**两个分页口径混用、自相矛盾**）；并且对未支持的 `cursor`
**静默忽略**（`?cursor=abc` 仍 200）。本脚本把这两条钉成**机械可判负**的断言。

断言（任一不满足 ⇒ `ok=false`／退出码非 0）：
  ① **分页不变式**：`has_more == (page*limit < total)`；
     且**信封不再含 `next_cursor`**（该键已删——本端点无游标协议）；
     且**不得**出现「`has_more is True` ＋ `next_cursor is None`」的自相矛盾形态。
  ② **未支持参数显式拒绝**：`?cursor=abc` ⇒ **400 结构化 JSON**（含机器可读 `error` 与人类可读 `detail`），
     **不得** 200、**不得**静默忽略、**不得** HTML 错误页。
     （「待支持」分支：若某实现改为**支持** `cursor` 而返回 200，则其分页读数**必须真的变化**，否则仍 FAIL。）
  ③ **末页 / 空页**：`page` 越界（`offset >= total`）⇒ `items==[]` 且 `has_more==False`；
     末页（`page*limit >= total`）⇒ `has_more==False`。
  ④ **反向自证**：把**旧形态**（`has_more=true` ＋ `next_cursor=null`）喂进**同一判据函数** ⇒ **必须 FAIL**
     （证明本判据能对旧形态判负）。

只读（GET），只用 stdlib（`urllib`），不触库、不联网采集。
用法：python3 verify_api_paging.py [--base http://127.0.0.1:5196]
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:5196"


# ───────────────────────────────────────────────────────── 取数 ──────────────
def _get(base: str, path: str, timeout: float = 15.0) -> dict:
    """返回 {status, content_type, raw, body(解析或 None), json_ok}。"""
    url = f"{base.rstrip('/')}{path}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            ctype = resp.headers.get("Content-Type", "")
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:  # 4xx/5xx 也带 body（我们不吞）
        status = exc.code
        ctype = exc.headers.get("Content-Type", "") if exc.headers else ""
        raw = exc.read().decode("utf-8", "replace")
    except Exception as exc:  # pragma: no cover - 连不上即报错
        return {"status": None, "content_type": "", "raw": f"{type(exc).__name__}: {exc}",
                "body": None, "json_ok": False, "url": url}
    body, json_ok = None, False
    try:
        body = json.loads(raw)
        json_ok = True
    except (ValueError, TypeError):
        pass
    return {"status": status, "content_type": ctype, "raw": raw, "body": body,
            "json_ok": json_ok, "url": url}


def machine_error(body: dict | None) -> str | None:
    """取「机器可读」错误码：顶层 `error`，或 `detail.error`（本仓路由用 HTTPException(detail={...})）。"""
    if not isinstance(body, dict):
        return None
    if isinstance(body.get("error"), str):
        return body["error"]
    det = body.get("detail")
    if isinstance(det, dict) and isinstance(det.get("error"), str):
        return det["error"]
    return None


def human_detail(body: dict | None) -> str | None:
    if not isinstance(body, dict):
        return None
    det = body.get("detail")
    if isinstance(det, str):
        return det
    if isinstance(det, dict):
        d = det.get("detail")
        return d if isinstance(d, str) else json.dumps(det, ensure_ascii=False)
    return None


# ────────────────────────────────────────── 判据（可被反向自证复用）────────────
def envelope_violations(body: dict, page: int, limit: int) -> list[dict]:
    """分页信封机械判据。返回违规清单（空 ⇒ 合规）。**同一函数**用于正向实跑与④旧形态反向自证。"""
    v: list[dict] = []
    if not isinstance(body, dict):
        return [{"kind": "not_a_dict", "got_type": type(body).__name__}]
    total = body.get("total")
    if not isinstance(total, int) or isinstance(total, bool):
        v.append({"kind": "total_not_int", "total": total})
        return v
    # ①a 不变式 has_more == (page*limit < total)
    expected = (page * limit) < total
    if body.get("has_more") is not expected:
        v.append({"kind": "has_more_invariant_violated", "got": body.get("has_more"),
                  "expected": expected, "page": page, "limit": limit, "total": total})
    # ①b 自相矛盾形态：has_more=true 而 next_cursor=null
    if body.get("has_more") is True and "next_cursor" in body and body.get("next_cursor") is None:
        v.append({"kind": "has_more_true_but_next_cursor_null",
                  "has_more": True, "next_cursor": None})
    # ①c 本端点无游标协议 ⇒ 信封**不得**含 next_cursor（该键已删）
    if "next_cursor" in body:
        v.append({"kind": "next_cursor_present_but_endpoint_has_no_cursor",
                  "next_cursor": body.get("next_cursor")})
    # ①d page/limit 回显一致
    if body.get("page") != page:
        v.append({"kind": "page_echo_mismatch", "got": body.get("page"), "expected": page})
    if body.get("limit") != limit:
        v.append({"kind": "limit_echo_mismatch", "got": body.get("limit"), "expected": limit})
    if not isinstance(body.get("items"), list):
        v.append({"kind": "items_not_list", "got_type": type(body.get("items")).__name__})
    return v


def main() -> int:
    ap = argparse.ArgumentParser(description="印人 API 分页自检")
    ap.add_argument("--base", default=DEFAULT_BASE)
    args = ap.parse_args()

    res: dict = {"base": args.base, "checks": {}, "raw_responses": {}, "ok": True}

    def check(name: str, passed: bool, detail):
        res["checks"][name] = {"pass": bool(passed), "detail": detail}
        if not passed:
            res["ok"] = False

    # ── 取数（四个真回包 + 一个越界空页）────────────────────────────────────
    r_limit3 = _get(args.base, "/api/persons?limit=3")
    r_cursor = _get(args.base, "/api/persons?limit=3&cursor=abc")
    r_limit500 = _get(args.base, "/api/persons?limit=500")
    r_lastpage = _get(args.base, "/api/persons?page=190&limit=3")
    r_empty = _get(args.base, "/api/persons?page=100000&limit=3")
    r_over = _get(args.base, "/api/persons?limit=501")  # 超上限（既有行为，sanity）

    for key, r in (("limit=3", r_limit3), ("limit=3&cursor=abc", r_cursor),
                   ("limit=500", r_limit500), ("page=190&limit=3", r_lastpage),
                   ("page=100000&limit=3", r_empty), ("limit=501", r_over)):
        raw = r["raw"]
        res["raw_responses"][key] = {"status": r["status"], "content_type": r["content_type"],
                                     "url": r["url"], "raw_len": len(raw),
                                     "raw_head": raw[:400],
                                     "raw_tail": (raw[-400:] if len(raw) > 800 else "")}

    # ── ① 分页不变式 + 信封形态（limit=3）──────────────────────────────────
    b = r_limit3["body"] or {}
    viol = envelope_violations(b, 1, 3)
    check("①.invariant_limit_eq_3", r_limit3["status"] == 200 and not viol,
          {"status": r_limit3["status"], "has_more": b.get("has_more"),
           "page": b.get("page"), "limit": b.get("limit"), "total": b.get("total"),
           "items_len": len(b.get("items") or []), "envelope_keys": sorted(b.keys()),
           "violations": viol})
    has_next_cursor = isinstance(b, dict) and ("next_cursor" in b)
    check("①.next_cursor_key_removed", not has_next_cursor,
          {"next_cursor_present": has_next_cursor, "envelope_keys": sorted(b.keys())})

    # ── ① 分页不变式（limit=500：整页取满）────────────────────────────────
    b5 = r_limit500["body"] or {}
    viol5 = envelope_violations(b5, 1, 500) if b5 else [{"kind": "no_body"}]
    check("①.invariant_limit_eq_500", r_limit500["status"] == 200 and not viol5,
          {"status": r_limit500["status"], "has_more": b5.get("has_more"),
           "total": b5.get("total"), "items_len": len(b5.get("items") or []), "violations": viol5})

    # ── ② cursor 未支持 ⇒ 400 结构化 JSON ────────────────────────────────
    cb = r_cursor["body"]
    err = machine_error(cb)
    detail = human_detail(cb)
    is_json = r_cursor["json_ok"]
    is_html = ("<html" in r_cursor["raw"].lower()[:2000]) or ("text/html" in (r_cursor["content_type"] or "").lower())
    if r_cursor["status"] == 400:
        passed_2 = is_json and (err is not None) and (detail is not None) and not is_html
        check("②.cursor_unsupported_400_structured", passed_2,
              {"status": r_cursor["status"], "error": err, "detail": detail,
               "is_json": is_json, "is_html": is_html, "content_type": r_cursor["content_type"]})
    elif r_cursor["status"] == 200:
        # 「待支持」分支：既然 200，分页读数必须**真的变化**（否则＝静默忽略 ⇒ FAIL）
        changed = (json.dumps(b.get("items"), ensure_ascii=False) != json.dumps(cb.get("items"), ensure_ascii=False)
                   or b.get("page") != cb.get("page") or b.get("total") != cb.get("total"))
        check("②.cursor_supported_200_changes_paging", changed,
              {"status": 200, "pagination_changed": changed, "note": "本实现取 400 分支；此分支仅供他实现"})
    else:
        check("②.cursor_unsupported_400_structured", False,
              {"status": r_cursor["status"], "error": err, "detail": detail, "is_html": is_html})

    # ── ③ 末页 / 空页 ─────────────────────────────────────────────────────
    lp = r_lastpage["body"] or {}
    lp_items = lp.get("items")
    check("③.last_page_no_more", r_lastpage["status"] == 200 and lp.get("has_more") is False
          and isinstance(lp_items, list) and len(lp_items) > 0 and lp.get("page") == 190,
          {"status": r_lastpage["status"], "page": lp.get("page"), "has_more": lp.get("has_more"),
           "items_len": len(lp_items) if isinstance(lp_items, list) else None, "total": lp.get("total")})

    ep = r_empty["body"] or {}
    check("③.out_of_range_empty", r_empty["status"] == 200 and ep.get("items") == [] and ep.get("has_more") is False,
          {"status": r_empty["status"], "page": ep.get("page"), "items": ep.get("items"),
           "has_more": ep.get("has_more"), "total": ep.get("total")})

    # sanity：limit 超上限（既有语义，未改）⇒ 400
    check("sanity.limit_over_cap_400", r_over["status"] == 400,
          {"status": r_over["status"], "error": machine_error(r_over["body"])})

    # ── ④ 反向自证：旧形态（has_more=true ＋ next_cursor=null）必须被判负 ─────
    old_form = {"items": [{"source_person_id": "x"}], "page": 1, "limit": 3, "total": 570,
                "has_more": True, "next_cursor": None}
    old_viol = envelope_violations(old_form, 1, 3)
    check("④.regression_old_form_Fails", bool(old_viol),
          {"old_form_keys": sorted(old_form.keys()), "old_form_verdict": "FAIL" if old_viol else "PASS",
           "old_form_violations": old_viol,
           "note": "旧形态（has_more=true ＋ next_cursor=null）喂同一判据 ⇒ 必须非空（判负）"})

    # 反向自证（正向对照）：新形态合规 ⇒ 判据应为空
    new_form = {"items": [{"source_person_id": "x"}], "page": 1, "limit": 3, "total": 570, "has_more": True}
    new_viol = envelope_violations(new_form, 1, 3)
    check("④.regression_new_form_Passes", not new_viol,
          {"new_form_keys": sorted(new_form.keys()), "new_form_violations": new_viol})

    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
