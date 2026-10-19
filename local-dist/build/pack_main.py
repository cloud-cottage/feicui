#!/usr/bin/env python
# local-dist/build/pack_main.py
"""「斐萃 · 本地封装分发版」——**PyInstaller 冻结态唯一入口**（源码态入口仍是 `local-dist/app.py`）。

本文件只在**打包产物**里当 `__main__` 跑；它在 `local-dist/build/feicui.spec` 里被指定为入口脚本。
之所以不直接把 `local-dist/app.py` 当入口，有两条**实测**理由（详见 `local-dist/build/README.md` §2）：

① **模块名 `app` 会撞车**：仓根 `app.py`（旧 Streamlit 壳）与 `server/app/` 包同名。
   若把它作为模块 `app` 收进 PYZ，冻结态下 `import app.colorcal`（引擎脚本与 `api.py`
   都要用）会被 PyInstaller 的冻结导入器先命中「壳模块」⇒ `ModuleNotFoundError`。
   ⇒ 本入口用 **按文件路径加载**（`spec_from_file_location`，模块名 `feicui_shell`），
   并把 `app.py` 作为 **data**（落到资源根），于是 `import app.*` 只会命中
   `server/app/` 的源码包。

② **`sys.executable` 是引导器，不是 python**：父进程（GUI）调引擎子进程时必须带
   `--engine-run <脚本> <引擎参数…>`；本入口据此**在同包解释器内**执行引擎脚本
   （`runpy.run_path(..., run_name="__main__")`）。不带该标志就会把参数当 GUI 参数
   再起一个窗口 —— 这正是「PyInstaller 下引擎子进程怎么调」的答案。

日志（`.app` 下**没有 stdout**；Windows 双击的 `.exe` 同理）：
    数据根 = `local-dist/src/paths.py::data_dir()`（**跨平台单一真源**）：
        macOS   ~/Library/Application Support/斐萃
        Windows %APPDATA%\斐萃
        Linux   ~/.local/share/斐萃（XDG_DATA_HOME）
    日志   = `local-dist/src/paths.py::log_dir()`：
        macOS   ~/Library/Logs/斐萃/pack-<yyyymmdd>.log
        Windows %LOCALAPPDATA%\斐萃\logs\pack-<yyyymmdd>.log
        Linux   ~/.local/state/斐萃/logs/pack-<yyyymmdd>.log
    `FEICUI_DATA_DIR` / `FEICUI_LOG_DIR` 仍**最高优先**（自检脚本靠它隔离）。
"""
from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

ENGINE_RUN_FLAG = "--engine-run"          # 必须与 `local-dist/api.py::ENGINE_RUN_FLAG` 同字面量


def _resource_root() -> Path:
    """包内资源根（onedir ⇒ `sys._MEIPASS`；兜底用本文件所在目录）。"""
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else Path(__file__).resolve().parent


def _user_dirs() -> tuple[Path, Path]:
    """`(data, logs)` —— **不在本文件拼平台路径**：全部委托 `local-dist/src/paths.py`。"""
    root = _resource_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from src.paths import user_dirs           # 冻结态取自 PYZ / 源码态取自 `<root>/src/paths.py`
    return user_dirs()


def _boot() -> tuple[Path, Path]:
    """建用户目录、把两个路径环境变量钉好、把 stdout/stderr 接到日志文件。返回 (data, logs)。"""
    from src.paths import ensure_dirs            # 与 `_user_dirs` 同源（单一真源）

    data, logs = _user_dirs()
    data, logs = ensure_dirs(data, logs)          # data / var / var/jobs / logs 四层

    root = _resource_root()
    # ⚠ 必须在 import api / src.* 之前设好（它们在建模块级常量时就读）
    os.environ["FEICUI_WEBUI_DIR"] = str(root)
    os.environ["FEICUI_PACK_ROOT"] = str(root)
    os.environ["FEICUI_DATA_DIR"] = str(data)

    log_path = logs / f"pack-{datetime.now():%Y%m%d}.log"
    try:
        fh = open(log_path, "a", encoding="utf-8", buffering=1)   # 行缓冲 ⇒ 崩了也留痕
    except Exception:
        fh = None
    # `--windowed` 下 sys.stdout / sys.stderr 可能是 None（无控制台）：任何 print 都会炸 ⇒ 换掉
    body = fh if fh is not None else open(os.devnull, "w", encoding="utf-8")
    sys.stdout = body
    sys.stderr = body
    return data, logs


def _banner(mode: str) -> None:
    print(f"\n===== feicui pack entry | {datetime.now():%Y-%m-%d %H:%M:%S} | mode={mode} "
          f"| frozen={getattr(sys, 'frozen', False)} | exe={sys.executable} "
          f"| argv={sys.argv[1:]} =====", flush=True)


def run_engine(rest: list[str]) -> int:
    """引擎子进程模式：`<引导器> --engine-run <脚本路径> <引擎参数…>`。

    在同包解释器内执行引擎脚本（引擎要用的 pymupdf/cv2/numpy/tifffile 都在包内）。
    **逐件一进程**（本仓硬纪律：Paddle/原生栈同进程反复建/毁推理上下文会 SIGSEGV）。
    """
    import runpy

    if not rest:
        print("ENGINE_RUN: 缺少脚本路径（用法：--engine-run <script.py> [args…]）", flush=True)
        return 2
    script = Path(rest[0])
    if not script.is_file():
        print(f"ENGINE_RUN: 引擎脚本不存在：{script}", flush=True)
        return 2
    sys.argv = [str(script)] + list(rest[1:])
    print(f"ENGINE_RUN: script={script} args={rest[1:]}", flush=True)
    runpy.run_path(str(script), run_name="__main__")   # 脚本自带 `raise SystemExit(main())`
    return 0


def run_gui(argv: list[str]) -> int:
    """GUI 模式：按**文件路径**加载 `app.py`（模块名 `feicui_shell`，避开 `app` 撞名）。"""
    import importlib.util

    root = _resource_root()
    shell_path = root / "app.py"
    if not shell_path.is_file():
        print(f"GUI: 壳脚本缺失：{shell_path}", flush=True)
        return 3
    for p in (str(root), str(root / "server")):
        if p not in sys.path:
            sys.path.insert(0, p)
    spec = importlib.util.spec_from_file_location("feicui_shell", shell_path)
    if spec is None or spec.loader is None:
        print(f"GUI: 无法加载 {shell_path}", flush=True)
        return 3
    module = importlib.util.module_from_spec(spec)
    sys.modules["feicui_shell"] = module      # 先注册再 exec（@dataclass 注解解析依赖它）
    spec.loader.exec_module(module)
    return int(module.main(argv) or 0)


def main() -> int:
    data, logs = _boot()
    argv = sys.argv[1:]
    mode = "engine" if (argv and argv[0] == ENGINE_RUN_FLAG) else "gui"
    _banner(mode)
    print(f"BOOT: platform={sys.platform} resource_root={_resource_root()} "
          f"data_dir={data} log_dir={logs} path0={sys.path[:3]}", flush=True)
    try:
        if mode == "engine":
            return run_engine(argv[1:])
        return run_gui(argv)
    except SystemExit:
        raise
    except BaseException:
        print("FATAL: 未捕获异常（原文如下）", flush=True)
        traceback.print_exc(file=sys.stdout)
        try:
            sys.stdout.flush()
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
