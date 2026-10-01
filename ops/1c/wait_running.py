#!/usr/bin/env python3
"""等面板 12 条全 running（阶段 1c-激活验收用；只读）。

用法：
    python3 ops/1c/wait_running.py [--expect 12] [--timeout 120]
输出：轮询时间线（每轮打印 running 数 + 非 running 条目）+ 最终逐条表。
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request

PANEL = "http://127.0.0.1:5555"


def fetch(path: str) -> dict:
    with urllib.request.urlopen(PANEL + path, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect", type=int, default=12)
    ap.add_argument("--timeout", type=float, default=120.0)
    args = ap.parse_args()

    t0 = time.time()
    deadline = t0 + args.timeout
    last = {}
    while True:
        try:
            last = fetch("/api/status")
        except Exception as exc:
            print(f"[{time.time() - t0:6.1f}s] /api/status 读失败：{exc!r}")
            if time.time() > deadline:
                return 1
            time.sleep(3)
            continue
        running = [k for k, v in last.items() if v.get("state") == "running"]
        notrunning = {k: v.get("state") for k, v in last.items() if v.get("state") != "running"}
        print(f"[{time.time() - t0:6.1f}s] 条目={len(last)} running={len(running)} 非running={notrunning}")
        if len(running) >= args.expect and not notrunning:
            break
        if time.time() > deadline:
            print("✗ 超时未达全 running")
            break
        time.sleep(3)

    print()
    self_info = fetch("/api/self")
    print("self = " + json.dumps(self_info, ensure_ascii=False))
    print()
    for sid, v in last.items():
        print(
            f"{sid:12s} | {v.get('state'):9s} | port={v.get('port')} pid={v.get('pid')} "
            f"portOpen={v.get('portOpen')} cwd={v.get('cwd')}"
        )
    nr = {k: v.get("state") for k, v in last.items() if v.get("state") != "running"}
    print(f"\n条目数={len(last)} running={sum(1 for v in last.values() if v.get('state') == 'running')} 非running={nr}")
    return 0 if not nr and len(last) == args.expect else 1


if __name__ == "__main__":
    raise SystemExit(main())
