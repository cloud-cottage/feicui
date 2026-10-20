#!/usr/bin/env python
# local-dist/build/check-spec-platforms.py
"""**不构建**、只**模拟** `feicui.spec` 在 darwin / win32 / linux 三个平台上的分支行为。

为什么需要它：spec 里的平台分叉（`BUNDLE` 只给 macOS、`.ico` 只给 Windows、
`webview.platforms.cocoa` 只在 darwin 出现）**只能在 Windows/CI 上真验**；但绝大多数错误
（比如又把 `cocoa` 写回无条件列表、把 `BUNDLE` 挪出 `if`）是**纯静态**的，本地就能拦住。

做法：把 PyInstaller 的 `Analysis / PYZ / EXE / COLLECT / BUNDLE` 换成记录参数的桩，
`collect_all` 换成返回空三元的假实现，然后 `exec(compile(spec))` 三遍（每遍 monkeypatch
`sys.platform`）⇒ 断言 **传给** 各构建类的参数。**零依赖**（不需要 PyInstaller、不写文件）。

跑法：
    python3 local-dist/build/check-spec-platforms.py          # 任何 Python ≥ 3.9
"""
from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

SPEC = Path(__file__).resolve().with_name("feicui.spec")
WEBUI = SPEC.parent.parent                      # local-dist/


def _stub_pyinstaller() -> None:
    """spec 顶部 `from PyInstaller.utils.hooks import collect_all` ⇒ 用假包顶上。"""
    pkg = types.ModuleType("PyInstaller")
    utils = types.ModuleType("PyInstaller.utils")
    hooks = types.ModuleType("PyInstaller.utils.hooks")
    hooks.collect_all = lambda name: ([], [], [])          # (datas, binaries, hiddenimports)
    pkg.utils, utils.hooks = utils, hooks
    sys.modules.setdefault("PyInstaller", pkg)
    sys.modules.setdefault("PyInstaller.utils", utils)
    sys.modules.setdefault("PyInstaller.utils.hooks", hooks)


def run(platform: str, stage: str = "1") -> dict:
    rec: dict = {"analysis": None, "exe": None, "collect": None, "bundle": None}

    class Analysis:
        def __init__(self, scripts, **kw):
            self.pure, self.scripts, self.binaries, self.datas = ["pure"], ["script"], [], []
            rec["analysis"] = {"scripts": scripts, **kw}

    class PYZ:
        def __init__(self, pure):
            pass

    class EXE:
        def __init__(self, *a, **kw):
            rec["exe"] = kw

    class COLLECT:
        def __init__(self, *a, **kw):
            rec["collect"] = kw

    class BUNDLE:
        def __init__(self, *a, **kw):
            rec["bundle"] = kw

    g = {"SPECPATH": str(SPEC.parent), "__file__": str(SPEC), "__name__": "spec",
         "Analysis": Analysis, "PYZ": PYZ, "EXE": EXE, "COLLECT": COLLECT, "BUNDLE": BUNDLE}
    old_plat, old_stage = sys.platform, os.environ.get("FEICUI_PACK_STAGE")
    sys.platform, os.environ["FEICUI_PACK_STAGE"] = platform, stage
    try:
        exec(compile(SPEC.read_text(encoding="utf-8"), str(SPEC), "exec"), g)
    finally:
        sys.platform = old_plat
        if old_stage is None:
            os.environ.pop("FEICUI_PACK_STAGE", None)
        else:
            os.environ["FEICUI_PACK_STAGE"] = old_stage
    rec["vars"] = {k: g.get(k) for k in ("ICON", "EXE_NAME", "BUNDLE_NAME", "IS_MAC", "IS_WIN")}
    rec["hiddenimports"] = rec["analysis"]["hiddenimports"]
    return rec


def main() -> int:
    _stub_pyinstaller()
    fails: list[str] = []

    def check(cond: bool, msg: str) -> None:
        print(("✅ " if cond else "❌ ") + msg, flush=True)
        if not cond:
            fails.append(msg)

    # ── darwin：行为必须与历史一致（BUNDLE 有、icns、cocoa 有、名字带 _lite）──────────────
    mac = run("darwin")
    check(mac["bundle"] is not None, "darwin: 调用了 BUNDLE（.app）")
    check(mac["bundle"] and mac["bundle"].get("icon") == str(WEBUI / "build" / "feicui.icns"),
          "darwin: BUNDLE icon = build/feicui.icns")
    check("webview.platforms.cocoa" in mac["hiddenimports"], "darwin: hiddenimports 含 webview.platforms.cocoa")
    check("webview.platforms.edgechromium" not in mac["hiddenimports"],
          "darwin: hiddenimports **不含** edgechromium")
    check(mac["vars"]["EXE_NAME"] == "斐萃_lite" and mac["vars"]["BUNDLE_NAME"] == "斐萃_lite",
          "darwin: EXE_NAME/BUNDLE_NAME = 斐萃_lite（stage 1 ⇒ _lite）")
    check(mac["exe"].get("console") is False and "icon" not in mac["exe"],
          "darwin: console=False 且 EXE 不传 icon（mac 图标只走 BUNDLE）")
    check(mac["exe"].get("argv_emulation") is False and "target_arch" in mac["exe"],
          "darwin: 保留了 argv_emulation/target_arch 等 mac 专属开关")

    # ── win32：onedir、ico、无 cocoa、exe 名 斐萃.exe ─────────────────────────────────
    win = run("win32")
    check(win["bundle"] is None, "win32: **不**调用 BUNDLE（否则 PyInstaller 直接断言失败）")
    check(win["collect"] and win["collect"].get("name") == "斐萃_lite",
          "win32: COLLECT 目录名 = 斐萃_lite（onedir）")
    check(win["exe"].get("name") == "斐萃" and win["vars"]["EXE_NAME"] == "斐萃",
          "win32: EXE 名 = 斐萃（双击用，不带阶段后缀）")
    check(win["exe"].get("icon") == str(WEBUI / "build" / "feicui.ico"),
          "win32: EXE icon = build/feicui.ico")
    check(win["exe"].get("console") is False, "win32: console=False（GUI 子系统，双击不弹黑框）")
    check(win["exe"].get("exclude_binaries") is True, "win32: exclude_binaries=True（onedir，非 onefile）")
    check("webview.platforms.cocoa" not in win["hiddenimports"],
          "win32: hiddenimports **不含** webview.platforms.cocoa（红线）")
    check("webview.platforms.edgechromium" in win["hiddenimports"],
          "win32: hiddenimports 含 webview.platforms.edgechromium")
    check("webview.platforms.winforms" in win["hiddenimports"], "win32: hiddenimports 含 winforms")
    check("clr" in win["hiddenimports"] and "clr_loader" in win["hiddenimports"],
          "win32: hiddenimports 含 pythonnet 的 clr / clr_loader")
    check(all("cocoa" not in h for h in win["hiddenimports"]), "win32: 任何 hiddenimport 都不含 cocoa")
    check(win["analysis"]["scripts"][0].endswith("pack_main.py"), "win32: 入口仍是 build/pack_main.py")
    check(any(p.endswith("paths.py") for p, _ in win["analysis"]["datas"]),
          "win32: datas 含 src/paths.py")

    # ── stage 2：OCR 开关不该污染平台分支（只验 hiddenimports 增量）────────────────────
    win2 = run("win32", stage="2")
    check("src.ocr_rapid" in win2["hiddenimports"], "win32 stage2: 收 OCR 模块")
    check("webview.platforms.cocoa" not in win2["hiddenimports"], "win32 stage2: 仍不含 cocoa")

    # ── linux：onedir、无 BUNDLE、无 cocoa ────────────────────────────────────────────
    lin = run("linux")
    check(lin["bundle"] is None, "linux: 不调用 BUNDLE")
    check("webview.platforms.cocoa" not in lin["hiddenimports"], "linux: 不含 cocoa")

    print("\nSPEC_PLATFORM_READINGS " + json.dumps({
        "darwin": {"exe_name": mac["vars"]["EXE_NAME"], "bundle": bool(mac["bundle"]),
                   "icon": mac["vars"]["ICON"], "hiddenimports": len(mac["hiddenimports"])},
        "win32": {"exe_name": win["vars"]["EXE_NAME"], "bundle": bool(win["bundle"]),
                  "icon": win["vars"]["ICON"], "collect_name": win["collect"]["name"],
                  "hiddenimports": win["hiddenimports"]},
        "linux": {"exe_name": lin["vars"]["EXE_NAME"], "bundle": bool(lin["bundle"])},
    }, ensure_ascii=False), flush=True)
    print(f"\n{'OK' if not fails else 'FAIL'} —— {len(fails)} 处不符", flush=True)
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
