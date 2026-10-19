#!/usr/bin/env python
# local-dist/build/make-ico.py
"""从 **1024 母图**生成 Windows `.ico`（多尺寸 16/32/48/64/128/256），并**自查**产物。

为什么单独一个脚本（而不是构建时现生成）：
  * `.ico` 只有 **几十 KB**（见下 readings），**入库**比「CI 每次现算」更稳：CI 里少一步 PIL 依赖、
    少一类「母图被替换了但产物没更新」的漂移；
  * 同时保留脚本 ⇒ 母图换版后 `bash` 一条命令重生成，读数一起打印（尺寸列表 ＋ 每帧字节）。
  ⇒ 本仓选择：**提交 `local-dist/build/feicui.ico`**；CI 只**校验**它存在且帧数/尺寸正确
    （`--check` 模式，不写文件），见 `.github/workflows/windows.yml`。

母图：`local-dist/build/feicui-1024.png`（1024×1024 RGBA，由 `make-icns.sh` 用 qlmanage 从
`local-dist/assets/feicui.svg` 矢量重渲染而来，与 macOS 的 `feicui.icns` 同源）。

跑法：
    ./venv/bin/python local-dist/build/make-ico.py            # 生成 ＋ 自查（写 feicui.ico）
    ./venv/bin/python local-dist/build/make-ico.py --check     # 只自查（CI 用；不写文件）

依赖：Pillow（本仓 `venv` 已有；CI 里由 render 栈安装顺带装上）——**不引其他新依赖**。
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
SRC = HERE / "feicui-1024.png"
OUT = HERE / "feicui.ico"
SIZES = (16, 32, 48, 64, 128, 256)


def _parse_ico(path: Path) -> list[dict]:
    """直接解析 ICO 目录项（不依赖 PIL 的解析路径）：`(w,h,bpp,bytes)` 逐帧。"""
    raw = path.read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", raw, 0)
    assert reserved == 0 and kind == 1, f"不是 ICO：reserved={reserved} type={kind}"
    frames = []
    for i in range(count):
        w, h, colors, _res, planes, bpp, nbytes, offset = struct.unpack_from("<BBBBHHII", raw, 6 + 16 * i)
        frames.append({"w": w or 256, "h": h or 256, "bpp": bpp,
                       "bytes": nbytes, "offset": offset, "png": raw[offset:offset + 8] == b"\x89PNG\r\n\x1a\n"})
    return frames


def verify(path: Path) -> dict:
    frames = _parse_ico(path)
    img = Image.open(path)
    sizes_seen = sorted({f["w"] for f in frames})
    missing = [s for s in SIZES if s not in sizes_seen]
    ok = (not missing) and img.format == "ICO" and path.stat().st_size > 0
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "frames": len(frames),
        "sizes": sizes_seen,
        "missing": missing,
        "per_frame": frames,
        "pil_format": img.format,
        "ok": ok,
    }


def build(src: Path = SRC, out: Path = OUT) -> dict:
    im = Image.open(src)
    assert im.size == (1024, 1024), f"母图必须是 1024×1024，实际 {im.size}"
    im = im.convert("RGBA")
    out.parent.mkdir(parents=True, exist_ok=True)
    # Pillow 的 ICO 写入器自己按 `sizes` 用 LANCZOS 逐帧缩放（≥256 帧自动存 PNG 压缩）
    im.save(out, format="ICO", sizes=[(s, s) for s in SIZES])
    return verify(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="从 1024 母图生成/校验 Windows .ico")
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--check", action="store_true", help="只校验现有 .ico（CI 用，不写文件）")
    args = ap.parse_args(argv)

    src, out = Path(args.src), Path(args.out)
    if args.check:
        if not out.exists():
            print(f"FAIL: 缺 {out}（本地跑 `python local-dist/build/make-ico.py` 生成后入库）")
            return 2
        reading = verify(out)
    else:
        if not src.exists():
            print(f"FAIL: 缺母图 {src}")
            return 2
        reading = build(src, out)
        reading["src"] = str(src)
        reading["src_size"] = list(Image.open(src).size)

    print("ICO_READINGS " + json.dumps(reading, ensure_ascii=False))
    print(f"{'OK' if reading['ok'] else 'FAIL'}: {reading['path']} "
          f"{reading['bytes']} B · {reading['frames']} 帧 · sizes={reading['sizes']} "
          f"· missing={reading['missing']}")
    return 0 if reading["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
