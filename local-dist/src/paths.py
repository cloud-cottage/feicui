#!/usr/bin/env python
# local-dist/src/paths.py
"""「斐萃」**用户目录单一真源**（data root ＋ log dir）—— 跨平台，纯 stdlib。

为什么要有这个文件（2026-10-20，Windows 移植单）：
    此前数据根/日志目录的拼接**散在四处**，而且每处都写死 macOS 路径：
      `local-dist/build/pack_main.py::_user_dirs()`   `~/Library/Application Support/斐萃` ＋ `~/Library/Logs/斐萃`
      `local-dist/src/yinyuan_client.py::default_data_dir()`   同上（`~/Library/Application Support/斐萃`）
      `local-dist/build/README.md` / 各处注释            同上（文档口径）
    ⇒ Windows 上这三处会一起把 `.env` / `yinyuan.json` / `var/**` / 日志写进
      `C:\\Users\\<u>\\Library\\Application Support\\斐萃`（一个 macOS 味道的假目录），且**没人拦得住**。
    现在所有平台派生**只在本文件**，其余模块一律调用 `data_dir() ` / `log_dir()`。

口径（**优先级自高到低**）：

| 目录 | 1（最高） | macOS | Windows | Linux / 其他 |
| --- | --- | --- | --- | --- |
| 数据根 | `FEICUI_DATA_DIR` | `~/Library/Application Support/斐萃` | `%APPDATA%\\斐萃` | `$XDG_DATA_HOME/斐萃`（默认 `~/.local/share/斐萃`） |
| 日志 | `FEICUI_LOG_DIR` | `~/Library/Logs/斐萃` | `%LOCALAPPDATA%\\斐萃\\logs` | `$XDG_STATE_HOME/斐萃/logs`（默认 `~/.local/state/斐萃/logs`） |

  * 环境变量优先是**既有行为**（`pack_main.py` 一直这么干，`selftest.py` / `domtest*.py`
    靠它把自检隔离到临时目录）⇒ 必须保留，且**空串按未设处理**（`FEICUI_DATA_DIR=""` 不当地址）。
  * Windows 上数据根走 **Roaming**（`%APPDATA%`，用户配置随域漫游），日志走 **Local**
    （`%LOCALAPPDATA%`，机器本地大文件，不该被漫游同步）。
  * Linux 用 XDG：数据 `share`、日志放 `state`（`logs` 子目录与 Windows 对齐；macOS 保持
    `~/Library/Logs/斐萃` 原样，**不**加 `logs` 子目录 —— 改了就动了老用户的日志位置）。

**测试可注入**：所有函数都接受 `platform= / environ= / home=` 关键字（默认取 `sys.platform` /
`os.environ` / `Path.home()`），三平台断言可在任意一台机上跑（见
`local-dist/tests/test_paths.py`，CI 里也在 windows-latest 上真跑一遍）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

#: 用户可见目录名（中文，与 `.app` / 窗口标题一致；**不要**改成 ASCII）
APP_DIRNAME = "斐萃"

#: 数据根覆盖变量（**最高优先级**；打包态由 `pack_main.py` 钉成绝对路径再传给子进程）
DATA_ENV = "FEICUI_DATA_DIR"
#: 日志目录覆盖变量（同上）
LOG_ENV = "FEICUI_LOG_DIR"

__all__ = [
    "APP_DIRNAME", "DATA_ENV", "LOG_ENV",
    "data_dir", "log_dir", "user_dirs", "var_dir", "jobs_dir", "env_file", "session_file",
    "ensure_dirs", "describe", "platform_tag",
]


def _env(environ, name: str) -> str:
    """读环境变量；**空串视作未设**（避免 `FEICUI_DATA_DIR=` 把根目录变成 `Path('')`）。"""
    src = os.environ if environ is None else environ
    return (src.get(name) or "").strip()


def _plat(platform: str | None) -> str:
    p = sys.platform if platform is None else platform
    # `cygwin` / `msys` 也算 Windows（只在手动注入时出现，Python 本体不会报这两个）
    return "win32" if p in ("win32", "cygwin", "msys") else p


def _home(home) -> Path:
    return Path(home) if home is not None else Path.home()


def platform_tag(platform: str | None = None) -> str:
    """给日志/产物名用的平台短标签：`macos` / `windows` / `linux`。"""
    p = _plat(platform)
    if p == "darwin":
        return "macos"
    if p == "win32":
        return "windows"
    return "linux"


def _default_root(kind: str, *, platform: str | None, environ, home) -> Path:
    """按平台派生**默认**用户目录（不做存在性检查、不建目录）。`kind` ∈ {`data`,`logs`}。

    这是**唯一**一处平台分支；其余函数只做「环境变量优先 → 回落本函数」。
    """
    p = _plat(platform)
    h = _home(home)
    if p == "darwin":
        if kind == "data":
            return h / "Library" / "Application Support" / APP_DIRNAME
        return h / "Library" / "Logs" / APP_DIRNAME
    if p == "win32":
        if kind == "data":
            base = _env(environ, "APPDATA")
            return Path(base) / APP_DIRNAME if base else h / "AppData" / "Roaming" / APP_DIRNAME
        base = _env(environ, "LOCALAPPDATA")
        return (Path(base) if base else h / "AppData" / "Local") / APP_DIRNAME / "logs"
    # Linux / 其他 POSIX：XDG（`XDG_*` 未设时按 XDG 规范的默认值）
    if kind == "data":
        base = _env(environ, "XDG_DATA_HOME")
        return Path(base) / APP_DIRNAME if base else h / ".local" / "share" / APP_DIRNAME
    base = _env(environ, "XDG_STATE_HOME")
    return (Path(base) if base else h / ".local" / "state") / APP_DIRNAME / "logs"


def data_dir(*, platform: str | None = None, environ=None, home=None) -> Path:
    """用户**可写数据根**（`.env` / `.session.json` / `yinyuan.json` / `var/**`）。

    `FEICUI_DATA_DIR` 最高优先（打包态由 `pack_main.py` 钉好；自检脚本用它做隔离）。
    """
    override = _env(environ, DATA_ENV)
    if override:
        return Path(override).expanduser()
    return _default_root("data", platform=platform, environ=environ, home=home)


def log_dir(*, platform: str | None = None, environ=None, home=None) -> Path:
    """日志目录（`pack-<yyyymmdd>.log` 等）。`FEICUI_LOG_DIR` 最高优先。"""
    override = _env(environ, LOG_ENV)
    if override:
        return Path(override).expanduser()
    return _default_root("logs", platform=platform, environ=environ, home=home)


def user_dirs(*, platform: str | None = None, environ=None, home=None) -> tuple[Path, Path]:
    """`(data_dir, log_dir)` —— 打包入口一次取两个。"""
    return (
        data_dir(platform=platform, environ=environ, home=home),
        log_dir(platform=platform, environ=environ, home=home),
    )


def _root(data: Path | str | None, kw: dict) -> Path:
    """`data` 显式给了就用它，否则回落到 `data_dir(**kw)`（`FEICUI_DATA_DIR` 优先）。"""
    return Path(data) if data else Path(data_dir(**kw))


def var_dir(data: Path | str | None = None, **kw) -> Path:
    """`<data>/var`（侧车 / 缓存 / 作业日志）。"""
    return _root(data, kw) / "var"


def jobs_dir(data: Path | str | None = None, **kw) -> Path:
    """`<data>/var/jobs`（tab2 每件任务一份日志）。"""
    return _root(data, kw) / "var" / "jobs"


def env_file(data: Path | str | None = None, **kw) -> Path:
    """`<data>/.env`（印源 host / 账号等非密钥配置）。"""
    return _root(data, kw) / ".env"


def session_file(data: Path | str | None = None, **kw) -> Path:
    """`<data>/.session.json`（印源会话缓存）。"""
    return _root(data, kw) / ".session.json"


def ensure_dirs(data: Path | str | None = None, logs: Path | str | None = None, **kw) -> tuple[Path, Path]:
    """建 `data` / `data/var` / `data/var/jobs` / `logs` 四层（失败**静默**：只读盘/权限问题不该拦启动）。"""
    d = _root(data, kw)
    lg = Path(logs) if logs else Path(log_dir(**kw))
    for path in (d, d / "var", d / "var" / "jobs", lg):
        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    return d, lg


def describe(*, platform: str | None = None, environ=None, home=None) -> dict:
    """给启动 banner / 单测用的一行摘要（含**生效来源**：`env` 还是 `platform`）。"""
    env = os.environ if environ is None else environ
    d, lg = user_dirs(platform=platform, environ=env, home=home)
    return {
        "platform": platform_tag(platform),
        "raw_platform": sys.platform if platform is None else platform,
        "data_dir": str(d),
        "log_dir": str(lg),
        "data_source": f"env:{DATA_ENV}" if _env(env, DATA_ENV) else "platform-default",
        "log_source": f"env:{LOG_ENV}" if _env(env, LOG_ENV) else "platform-default",
    }
