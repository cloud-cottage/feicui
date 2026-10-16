#!/usr/bin/env python
# webui/app.py
"""「斐萃」本地电脑版 —— **PyWebView 原生窗口入口**（唯一启动形态）。

口径（Kevin 2026-10-16，含当日变更）：
  * 壳 ＝ **PyWebView 原生窗口**（Streamlit UI 退役；不再有 `--serve` / 端口监听 / 浏览器形态）。
  * 一份 UI（`ui/`，纯 HTML/CSS/JS，**无 CDN 外链**）＋ 一个 js_api 桥（`api.py`）。
  * `api.py` / `src/*.py` **不 import webview**；本文件是唯一 import `webview` 的地方
    ⇒ 逻辑层可脱离 GUI 单测（`webui/selftest.py`）。
  * 长任务（tab2 HighRes 渲染）走子进程 + 后台线程，进度经
    `window.evaluate_js('window.onProgress(…)')` 推给 UI。

跑法：
    ./venv/bin/python webui/app.py                       # 打开窗口
    ./venv/bin/python webui/app.py --debug               # 开 DevTools
    ./venv/bin/python webui/app.py --test-exit-after 12   # 起窗 12 s 后自动关（自检用，非交互）
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path

WEBUI_DIR = Path(__file__).resolve().parent
if str(WEBUI_DIR) not in sys.path:
    sys.path.insert(0, str(WEBUI_DIR))

from api import APP_NAME, APP_VERSION, UI_DIR, FeicuiApi  # noqa: E402

WINDOW_TITLE = f"{APP_NAME} v{APP_VERSION}"
INDEX = UI_DIR / "index.html"


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
    return webview, window


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="斐萃 本地电脑版（PyWebView）")
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
            try:
                window.destroy()
            except Exception as exc:  # pragma: no cover
                print(f"WINDOW_TEST: destroy 失败 {exc!r}", flush=True)

        threading.Timer(args.test_exit_after, _bye).start()

    print(f"WEBUI_START mode=native ui={INDEX} engine_python={api.jobs.engine_python()}", flush=True)
    webview.start(debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
