#!/usr/bin/env python3
"""K5b 衍生：现场复现「修复前基线」——把 SealDetailView.vue 的按钮条件临时还原为
`v-if="canReplaceFaceImage"`，用同一探针量一遍（预期：XAI-0001 3 个块都有按钮），
再原样写回修复版并核对 md5。**只临时动一个条件字符串**，其余字节不变。
"""
import json
import re
import subprocess
import sys
import time
import hashlib

sys.path.insert(0, "/Users/kevin/bistro/xiai/feicui/ops")
from kong_k5b_edge_selftest import (BASE, PORT, ADMIN, CODE, SEAL, BLOCK_SCAN,  # noqa: E402
                                    new_target, ensure_chrome, Tab)

VIEW = "/Users/kevin/bistro/xiai/src/views/SealDetailView.vue"
FIXED_COND = 'v-if="canReplaceFaceImage && !face.isEdge"'
BASE_COND = 'v-if="canReplaceFaceImage"'
OUT = "/Users/kevin/bistro/xiai/feicui/ops/kong_k5b_edge_baseline_raw.json"


def md5(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def main():
    src = open(VIEW, encoding="utf-8").read()
    assert src.count(FIXED_COND) == 1, "预期修复版恰好出现一次"
    out = {"view_md5_with_fix": md5(VIEW)}

    # ---- 临时还原基线 ----
    open(VIEW, "w", encoding="utf-8").write(src.replace(FIXED_COND, BASE_COND))
    time.sleep(3.0)  # 等 Vite HMR
    ensure_chrome()
    tab = Tab(new_target(f"{BASE}/")["webSocketDebuggerUrl"])
    try:
        tab.goto(f"{BASE}/", wait=2.0)
        tab.js("(() => { localStorage.clear(); return 1; })()")
        tab.goto(f"{BASE}/login", wait=1.5)
        tab.js(
            "(() => { const set=(el,v)=>{el.value=v; el.dispatchEvent(new Event('input',{bubbles:true}));};"
            f" set(document.querySelector('#login-phone'), '{ADMIN}');"
            f" set(document.querySelector('#login-code'), '{CODE}');"
            " document.querySelector('form.login__form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));"
            " return 1; })()"
        )
        time.sleep(2.0)
        tab.goto(f"{BASE}/seal/{SEAL}", wait=2.5)
        snap = tab.js(BLOCK_SCAN)
        out["baseline_repro"] = {k: v for k, v in snap.items() if k != "rows"}
        out["baseline_repro"]["rows"] = [
            {"kind": r["kind"], "faceId": r["faceId"], "hasReplaceBtn": r["hasReplaceBtn"]}
            for r in snap["rows"]]
    finally:
        tab.close()
        # ---- 原样写回修复版 ----
        open(VIEW, "w", encoding="utf-8").write(src)
        time.sleep(2.0)
    out["view_md5_restored"] = md5(VIEW)
    out["restored_equals_fixed"] = out["view_md5_restored"] == out["view_md5_with_fix"]
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["restored_equals_fixed"] else 1


if __name__ == "__main__":
    sys.exit(main())
