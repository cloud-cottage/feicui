"""池的**拉起器**（E1 后异步拉起 + API 启动补跑）——Kong / 阶段 1c-激活。

## 它解决什么

`feicui-api`（5196）只做入队 + 查询，真正跑活的是**独立进程**的池（`app.pool`，规范 §1.3 进程分离）。
1b 交付时池**只能由人工/脚本拉起** ⇒ 用户在 UI 上建的 job 会永远停在 `QUEUED`：
面板托管的只有 API / 前端两条**端口服务**，「池」是无端口常驻进程，**不入 `services` 表**（见
`ctrl/PORTS.md` P9）；入表会污染面板「N/N 全监听」的判态。故本层采取第三种形态：

```
   E1 POST /api/jobs ──► 入队（jobs=QUEUED）──► 本模块：**异步、detached** 拉起一次
                                                `./.venv/bin/python -m app.pool --workers 4 --drain`
                                                池跑完（无活跃 job）自行退出，不常驻
   API 启动 ──► 扫一次 QUEUED/RUNNING ──► 有则同样拉一次（防 API 重启后 job 被遗忘）
```

## 纪律（逐条对应派单）

* **不阻塞请求**：`launch_pool_async` 只起一条 daemon 线程，`spawn` 返回即结束；池的任何失败
  （退出码非 0 / 解释器缺失）**只记日志**，绝不影响 E1 的 `201`。
* **进程分离**：拉起的是**独立进程**（`start_new_session=True` ⇒ 自成进程组，不随 API 退出而收走），
  worker 仍是池的子进程；**接口层内不跑 OCR**（§1.3）。
* **写正式库的授权变量**：子进程 env 显式带 `FEICUI_ALLOW_PROD_MIGRATE=1`（否则 `app.migrations`
  会以 exit 3 拒绝写正式库 ⇒ 池起不来）与 `FEICUI_DB=<API 同库>`；**不给就不写**（授权只在本行）。
* **双起保护（"已有池在跑"＝正常分支）**：池自身用 `flock` 占 `server/.run/pool.state.lock`。本层
  ① 先试 `flock(LOCK_EX|LOCK_NB)` 探测（不占锁、不写库）；② 池若仍以 exit 5（锁被占）退出，
  只记 INFO —— **不报错、不重试堆进程**。
* **补跑兜底（close the stranding race）**：拉起的候选池可能"锁被占而退出"或"刚要退出"，
  而此刻新 job 已入库 ⇒ 会有 job 无人认领。故每次拉起后**至多再复查 `MAX_RECHECK` 次**
  （默认 3 次 / 每次间隔 2.5s）：只要"仍有活跃 job 且无池在跑"，就再拉一次。次数有上界，
  池若因结构性故障永远起不来也不会无限堆进程。

用法（一般由 API 调用，不必手工）：
    from . import poolctl
    poolctl.launch_pool_async(st, reason="E1:job-...")     # 异步
    poolctl.catch_up_on_startup(st)                        # API 启动补跑（内部亦异步）
"""
from __future__ import annotations

import fcntl
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

from . import db, repository
from .config import SERVER_DIR, Settings

log = logging.getLogger("feicui.api.poolctl")

POOL_MODULE = "app.pool"
DEFAULT_WORKERS = 4
RECHECK_DELAY_S = 2.5
MAX_RECHECK = 3


# --------------------------------------------------------------------------- 探测
def pool_lock_path(st: Settings) -> Path:
    """池的写锁文件（与 `app.pool.Pool._acquire_lock` 同源口径）。"""
    return st.pool_state_path.with_suffix(".lock")


def pool_running(st: Settings) -> bool:
    """**只读探测**：写锁被别的进程持有 ⇒ 已有池在跑（探测完立刻释放自己的探测锁）。

    用 `flock(LOCK_EX|LOCK_NB)` 试占：探到占用就说明有池活着；试占成功说明当前无池，
    立即 `LOCK_UN` 放掉（不写 pid、不动状态文件），因此**探测本身没有副作用**。
    """
    lock_path = pool_lock_path(st)
    if not lock_path.exists():
        return False
    try:
        fh = lock_path.open("a")
    except OSError as exc:  # pragma: no cover - 权限等异常不阻断主链路
        log.warning("池写锁探测失败（按无池处理）：%r", exc)
        return False
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return True
    try:
        fcntl.flock(fh, fcntl.LOCK_UN)
    finally:
        fh.close()
    return False


# --------------------------------------------------------------------------- 拉起
def pool_launch_log(st: Settings) -> Path:
    return SERVER_DIR / ".run" / "pool-launch.log"


def _child_env(st: Settings) -> dict:
    env = os.environ.copy()
    env["FEICUI_DB"] = str(st.db_path)          # 与 API 同库（面板托管的 API 指向正式库）
    env["FEICUI_ALLOW_PROD_MIGRATE"] = "1"      # 写正式库的显式授权（否则 app.migrations exit 3）
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _spawn(st: Settings, reason: str, workers: int, drain: bool) -> subprocess.Popen | None:
    """起一个真池进程（detached）；失败只记日志并返回 None。"""
    args = [sys.executable, "-m", POOL_MODULE, "--workers", str(workers)]
    if drain:
        args.append("--drain")
    log_path = pool_launch_log(st)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = log_path.open("a", buffering=1, encoding="utf-8")
    except OSError as exc:
        log.warning("打不开池拉起日志（跳过本次拉起）：%r", exc)
        return None
    try:
        fh.write(
            f"\n=== launch {db.now_iso()} reason={reason} args={' '.join(args)} "
            f"cwd={SERVER_DIR} db={st.db_path} prod_allowed=1\n"
        )
        proc = subprocess.Popen(  # noqa: S603 - 参数由本层构造，非用户输入
            args,
            cwd=str(SERVER_DIR),
            env=_child_env(st),
            stdin=subprocess.DEVNULL,
            stdout=fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # detached：独立进程组，不随 API 退出被收走
        )
    except Exception as exc:  # pragma: no cover - 拉起失败不得影响调用方
        log.warning("拉起池失败（reason=%s）：%r", reason, exc)
        fh.close()
        return None
    log.info("已拉起池：pid=%d reason=%s（日志 %s）", proc.pid, reason, log_path)
    threading.Thread(target=_reap, args=(proc, reason, log_path), daemon=True, name="pool-reap").start()
    return proc


def _reap(proc: subprocess.Popen, reason: str, log_path: Path) -> None:
    """收尸线程：把池的退出码写进日志；**exit 5 ＝ 已有池在跑**（正常分支，不是错误）。"""
    try:
        rc = proc.wait()
    except Exception as exc:  # pragma: no cover
        log.warning("池 pid=%d 收尸失败：%r", proc.pid, exc)
        return
    try:
        with log_path.open("a", buffering=1, encoding="utf-8") as fh:
            fh.write(f"--- exit {db.now_iso()} rc={rc} pid={proc.pid} reason={reason}\n")
    except OSError:
        pass
    if rc == 5:
        log.info("池 pid=%d 退出 rc=5（写锁被占 ⇒ 已有池在跑），按正常分支忽略：reason=%s", proc.pid, reason)
    elif rc == 0:
        log.info("池 pid=%d 跑完退出 rc=0：reason=%s", proc.pid, reason)
    else:
        log.warning("池 pid=%d 异常退出 rc=%d：reason=%s（详见 %s）", proc.pid, rc, reason, log_path)


def _active_jobs(st: Settings) -> list[dict]:
    try:
        return repository.list_active_jobs(st.db_path)
    except Exception as exc:  # pragma: no cover - 读库失败不阻断（下一轮复查再试）
        log.warning("补跑扫描失败：%r", exc)
        return []


def _attempt(st: Settings, reason: str, workers: int, drain: bool, depth: int) -> None:
    if pool_running(st):
        log.info("池已在跑（写锁被持有）⇒ 跳过拉起：reason=%s", reason)
    else:
        _spawn(st, reason, workers, drain)
    if depth < MAX_RECHECK:
        timer = threading.Timer(
            RECHECK_DELAY_S, _recheck, args=(st, reason, workers, drain, depth + 1)
        )
        timer.daemon = True
        timer.start()


def _recheck(st: Settings, reason: str, workers: int, drain: bool, depth: int) -> None:
    """兜底复查：候选池可能"锁被占而退出 / 刚要退出"，此期间入库的 job 会无人认领。"""
    active = _active_jobs(st)
    if not active:
        return
    if pool_running(st):
        return  # 有池活着 ⇒ 它自己会取活
    log.warning(
        "补跑：仍有 %d 个活跃 job 且无池在跑 ⇒ 再拉一次（depth=%d）：%s",
        len(active),
        depth,
        [j["job_id"] for j in active],
    )
    _attempt(st, reason, workers, drain, depth)


def launch_pool_async(
    st: Settings, *, reason: str, workers: int = DEFAULT_WORKERS, drain: bool = True
) -> None:
    """**异步**拉起一次池（不阻塞调用方；任何失败只记日志）。"""
    threading.Thread(
        target=_attempt, args=(st, reason, workers, drain, 0), daemon=True, name="pool-launch-attempt"
    ).start()


def catch_up_on_startup(st: Settings) -> None:
    """API 启动补跑：库里有 `QUEUED`/`RUNNING` 的 job ⇒ 拉一次池（防 API 重启后 job 被遗忘）。"""

    def _run() -> None:
        active = _active_jobs(st)
        if not active:
            log.info("启动补跑：无活跃 job（QUEUED/RUNNING）⇒ 不拉起池")
            return
        log.warning(
            "启动补跑：发现 %d 个活跃 job ⇒ 拉起池：%s",
            len(active),
            [f"{j['job_id']}({j['state']})" for j in active],
        )
        _spawn(st, "startup-catchup", DEFAULT_WORKERS, True)
        timer = threading.Timer(
            RECHECK_DELAY_S, _recheck, args=(st, "startup-catchup", DEFAULT_WORKERS, True, 1)
        )
        timer.daemon = True
        timer.start()

    threading.Thread(target=_run, daemon=True, name="pool-startup-catchup").start()


def status(st: Settings) -> dict:
    """只读自检（运维 / 自测用）：池是否在跑、锁文件、拉起日志与库内活跃 job。"""
    return {
        "pool_running": pool_running(st),
        "lock_path": str(pool_lock_path(st)),
        "launch_log": str(pool_launch_log(st)),
        "active_jobs": [j["job_id"] for j in _active_jobs(st)],
    }
