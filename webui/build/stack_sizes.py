#!/usr/bin/env python
# webui/build/stack_sizes.py —— `.app` 体积按「栈」拆解（哪一块占多少 MB）。
"""跑法：
    webui/build/.venv-build/bin/python webui/build/stack_sizes.py webui/build/dist/斐萃-s2.app [--json out.json] [--top-other 10]

口径（**实读，不是估算**）：
  * `du_mb`            `du -sk` 读数（磁盘占用；`.app` 内 `Frameworks/` 与 `Resources/` 是**硬链接同一份**，
                       故 du 会自动去重 —— 这是「占用」口径）。
  * `unique_mb`        遍历全部普通文件、**按 inode 去重**后求和（内容真值口径）。
  * `stacks`           同上，但按路径/文件名关键字归堆（长关键字优先，未命中归 `<other>`）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path

# (栈名, 正则) —— 顺序即优先级：越专有越靠前
STACKS: list[tuple[str, str]] = [
    ("paddle 全家", r"(^|/)(paddle|paddlex|paddleocr)(/|$)|libphi|libpaddle|libiomp|libmkl"),
    ("onnxruntime", r"(^|/)onnxruntime(/|$)|libonnxruntime"),
    ("rapidocr(含模型)", r"(^|/)rapidocr(/|$)|PP-OCRv6_(det|rec)_small\.onnx|ch_ppocr_mobile"),
    ("pymupdf", r"(^|/)(pymupdf|fitz)(/|$)|libmupdf"),
    ("opencv(python 绑定)", r"(^|/)cv2(/|$)|libopencv"),
    ("opencv 附属媒体库(ffmpeg 等)", r"libav(codec|format|util|filter|device|if)|libsw(scale|resample)|libx26\d|libaom|libdav1d|libvpx|libmp3lame|libopus|libvorbis|libtheora|libbluray|libaribb24|libSvtAv1|libOrbbecSDK|libarchive|libchromaprint|libssh|libvidstab|libwebp|libopenjp2|libtiff|libjpeg|libx264|libx265|libzimg|libspeex|libgme|libmodplug|libbs2b|libflite|libsnappy|libzmq|libpgm|libnorm|libass|libfribidi|libharfbuzz|libfontconfig|libfreetype|libunicode|libsoxr|librist|libsrt|libtwolame|libgsm|libopenmpt"),
    ("numpy", r"(^|/)numpy(/|$)"),
    ("pyobjc / 系统框架(macOS 壳)", r"(^|/)(objc|pyobjc|AppKit|Foundation|WebKit|Cocoa|Quartz|CoreFoundation|Security|UniformTypeIdentifiers|_cffi_backend|cryptography)|libffi"),
    ("webview", r"(^|/)webview(/|$)"),
    ("tifffile+PIL", r"(^|/)(tifffile|PIL|imagecodecs)(/|$)"),
    ("shapely+pyclipper", r"(^|/)(shapely|pyclipper|pyclip)"),
    ("Python 运行时", r"^/Python(\.framework)?$|^/python3\.\d+$|^/base_library\.zip$|^/libpython|^/libmpdec|^/libxcb|^/libX11|^/libXau|^/libXdmcp|^/libz\.|^/liblzma|^/libssl|^/libcrypto|^/libb2"),
]


def classify(rel: str) -> str:
    for name, pat in STACKS:
        if re.search(pat, rel, re.IGNORECASE):
            return name
    return "<other>"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("app")
    ap.add_argument("--json", default="")
    ap.add_argument("--top-other", type=int, default=12)
    args = ap.parse_args()
    root = Path(args.app).resolve()
    du = subprocess.run(["du", "-sk", str(root)], capture_output=True, text=True).stdout.split()
    du_mb = round(int(du[0]) / 1024, 1) if du else 0.0

    per: dict[str, int] = defaultdict(int)
    seen: set[tuple[int, int]] = set()
    others: list[tuple[int, str]] = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            p = Path(dirpath) / f
            try:
                st = p.stat()
            except OSError:
                continue
            key = (st.st_dev, st.st_ino)
            if key in seen:          # 硬链接去重（Frameworks/ 与 Resources/ 是同一份）
                continue
            seen.add(key)
            rel = "/" + str(p.relative_to(root))
            name = classify(rel)
            per[name] += st.st_size
            if name == "<other>":
                others.append((st.st_size, rel.lstrip("/")))
    uniq = sum(per.values())
    print(f"app={root.name}  du={du_mb} MB  unique_content={round(uniq/1e6,1)} MB  files={len(seen)}")
    for name, sz in sorted(per.items(), key=lambda kv: -kv[1]):
        print(f"  {name:30s} {sz/1e6:8.1f} MB  {100.0*sz/uniq:5.1f}%")
    print(f"  —— <other> 明细（前 {args.top_other}）——")
    for sz, rel in sorted(others, reverse=True)[: args.top_other]:
        print(f"     {sz/1e6:7.2f} MB  {rel}")
    if args.json:
        Path(args.json).write_text(json.dumps(
            {"app": root.name, "du_mb": du_mb, "unique_mb": round(uniq / 1e6, 1),
             "stacks": {k: round(v / 1e6, 1) for k, v in sorted(per.items(), key=lambda kv: -kv[1])},
             "other_top": [{"mb": round(sz / 1e6, 2), "path": rel} for sz, rel in sorted(others, reverse=True)[:args.top_other]]},
            ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
