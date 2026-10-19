#!/usr/bin/env python
# local-dist/app.py
"""「斐萃」本地封装分发版 —— **PyWebView 原生窗口入口**（唯一启动形态）。

口径（Kevin 2026-10-16，含当日变更）：
  * 壳 ＝ **PyWebView 原生窗口**（Streamlit UI 退役；不再有 `--serve` / 端口监听 / 浏览器形态）。
  * 一份 UI（`ui/`，纯 HTML/CSS/JS，**无 CDN 外链**）＋ 一个 js_api 桥（`api.py`）。
  * `api.py` / `src/*.py` **不 import webview**；本文件是唯一 import `webview` 的地方
    ⇒ 逻辑层可脱离 GUI 单测（`local-dist/selftest.py`）。
  * 长任务（tab2 HighRes 渲染）走子进程 + 后台线程，进度经
    `window.evaluate_js('window.onProgress(…)')` 推给 UI。

跑法：
    ./venv/bin/python local-dist/app.py                       # 打开窗口
    ./venv/bin/python local-dist/app.py --debug               # 开 DevTools
    ./venv/bin/python local-dist/app.py --test-exit-after 12   # 起窗 12 s 后自动关（自检用，非交互）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

WEBUI_DIR = Path(__file__).resolve().parent
if str(WEBUI_DIR) not in sys.path:
    sys.path.insert(0, str(WEBUI_DIR))

from api import APP_NAME, APP_TITLE, APP_VERSION, UI_DIR, FeicuiApi  # noqa: E402

#: 窗口标题＝**单一真源** `api.APP_TITLE`（＝「斐萃」玺印解析任务台 · 本地封装分发版，带本地版后缀）
WINDOW_TITLE = APP_TITLE
INDEX = UI_DIR / "index.html"

#: 诊断开关：`FEICUI_EXIT_TRACE=1` ⇒ 打印「关窗 → 进程落地」各阶段时间戳/线程名（默认静默）
EXIT_TRACE = os.environ.get("FEICUI_EXIT_TRACE") == "1"
_T0 = time.monotonic()
_exit_lock = threading.Lock()
_exit_fired = False


def _trace(msg: str) -> None:
    if EXIT_TRACE:
        print(f"EXIT_TRACE t={time.monotonic() - _T0:.3f}s "
              f"thread={threading.current_thread().name} {msg}", flush=True)


def _hard_exit(reason: str, code: int = 0) -> None:
    """**唯一**退出通道：flush 后 `os._exit`（跳过解释器/pywebview 的收尾阶段）。

    口径（2026-10-18 实测）：macOS 上窗口关掉后 `webview.start()` 的收尾**不保证返回** ——
    Cocoa runloop 已 `stop_`、`windowWillClose_` 里已把 `i.webview` 置 None 并 `del instances[uid]`，
    但主线程/HTTP 服务/bridge 线程的收敛可能卡住（实测同一包 `open -n` 起 15 次里 1 次
    「窗口消失 → 进程消失」= 42.7 s；父级另见 ≥90 s），进程 STAT=S 空转 ⇒ 挂载中的 DMG
    被它持有 ⇒ `hdiutil detach` 报 busy。
    **不用 `sys.exit()`**：它只抛 SystemExit，卡在 runloop 里的主线程根本回不来。
    """
    global _exit_fired
    with _exit_lock:
        if _exit_fired:
            return
        _exit_fired = True
    _trace(f"hard_exit reason={reason} code={code}")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass
    os._exit(code)


def _arm_exit_watchdog(grace: float, reason: str) -> None:
    """daemon 看门狗：`grace` 秒后无条件落地（窗口已关却退不动的兜底）。"""

    def _wait() -> None:
        time.sleep(max(0.0, grace))
        _hard_exit(reason)

    threading.Thread(target=_wait, name="exit-watchdog", daemon=True).start()



def _make_pusher(window):
    """进度推送：把 onProgress(payload) 注入页面（失败只忽略，UI 另有轮询兜底）。"""

    def push(snapshot: dict) -> None:
        try:
            payload = json.dumps(snapshot, ensure_ascii=False)
            window.evaluate_js(f"window.onProgress && window.onProgress({payload});")
        except Exception:
            pass

    return push


def build_window(api: FeicuiApi, *, width: int = 1320, height: int = 880):
    """建窗口（**不阻塞**）；返回 (webview_module, window)。"""
    import webview  # 仅此处 import（分层纪律）

    if not INDEX.exists():
        raise SystemExit(f"UI 缺失：{INDEX}")
    window = webview.create_window(
        WINDOW_TITLE,
        url=str(INDEX),          # 本地文件 ⇒ pywebview 内建 http server 提供（相对引用可用）
        js_api=api,
        width=width,
        height=height,
        min_size=(980, 640),
        text_select=True,
    )
    api.jobs.attach_pusher(_make_pusher(window))
    api._closer = window.destroy

    # 关窗是**唯一**汇点：Timer/UI「关闭窗口」按钮(`api.shutdown`)/标题栏红点/Cmd-Q 都落到
    # Cocoa `windowWillClose_` ⇒ `events.closed`。挂在这里 ⇒ 一条兜底通道覆盖全部退出形态。
    def _on_closed(*_args) -> None:
        _trace("events.closed fired（窗口已销毁）")
        # 收尾给 0.4 s 让 UI 的最后一帧/日志落盘，然后无条件落地（不赌 runloop 会返回）
        _arm_exit_watchdog(0.4, "closed-event")

    window.events.closed += _on_closed
    return webview, window


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="斐萃 本地封装分发版（PyWebView）")
    ap.add_argument("--debug", action="store_true", help="开 DevTools / 调试模式")
    ap.add_argument("--width", type=int, default=1320)
    ap.add_argument("--height", type=int, default=880)
    ap.add_argument("--test-exit-after", type=float, default=0.0,
                    help="自检：起窗 N 秒后自动关窗并退出（0 = 正常交互运行）")
    args = ap.parse_args(argv)

    api = FeicuiApi()
    webview, window = build_window(api, width=args.width, height=args.height)

    if args.test_exit_after and args.test_exit_after > 0:

        def _bye() -> None:
            print(f"WINDOW_TEST: 窗口存活 {args.test_exit_after}s（自动关窗）", flush=True)
            _trace("test timer 触发（本线程非主线程；destroy 内部由 cocoa 转投主线程）")
            # 兜底：不管 closed 会不会来、runloop 收不收敛，2 s 后必定落地（< 3 s 验收线）
            _arm_exit_watchdog(2.0, "test-timer-fallback")
            try:
                window.destroy()
            except Exception as exc:  # pragma: no cover
                print(f"WINDOW_TEST: destroy 失败 {exc!r}", flush=True)

        timer = threading.Timer(args.test_exit_after, _bye)
        timer.daemon = True          # Timer 默认继承主线程的非 daemon 属性 ⇒ 显式置 daemon
        timer.start()

    print(f"WEBUI_START mode=native ui={INDEX} engine_python={api.jobs.engine_python()}", flush=True)
    webview.start(debug=args.debug)
    # 正常情形走不到这里（closed 事件已把进程落地）；到了说明 runloop 自己返回了 ⇒ 直接硬退，
    # 不进入解释器收尾（那条路上会卡住：见 _hard_exit 注释）。
    _trace("webview.start() 返回")
    _hard_exit("start-returned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
