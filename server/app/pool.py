"""常驻 worker 池 supervisor（**唯一写者**）——Kong / 阶段 1b-i。

## 它是什么

`feicui-api`（薄接口层，5196）只做**入队 + 查询**；真正把一本书解析完的是本进程：

```
   E1 POST /api/jobs  ──入队──▶  jobs(QUEUED) + job_pages(PENDING)   ← 接口层单事务写
                                        │
                          本进程（常驻，N=4 worker）│ 轮询取活
                                        ▼
        claim_job（置 RUNNING；把残留 RUNNING 页退回 PENDING ＝ 断点续跑入口）
                                        ▼
        claim_next_chunk（CAS 认领 chunk；chunk＝页区间＝并行单位＝断点单位）
                                        ▼
        ┌──────────── 4 个 worker 子进程（feicui/venv/bin/python）────────────┐
        │ 渲染 / 检测 / 释文块匹配 / OCR / 写 .webp（内容 sha256 幂等）        │
        └────────────────────┬──────────────────────────────────────────────┘
                             │ 每页一行 JSON（结果回到本进程）
                             ▼
        commit_chunk（**单事务**：stamps 行级幂等 upsert + job_pages→DONE/FAILED + 计数）
                             ▼
        jobs.cursor_chunk_* / 终态（DONE / FAILED_PARTIAL）
```

## 为什么写者只能是它一个（规范 §4.3）

WAL 只允许**一个写者**：N 个 worker 各自直连 `yinpu.db` 并发 `INSERT` 会触发 `database is locked`
或假成功。故 **worker 绝不碰 DB**，只回传结果；**DB 的每个事务都在本进程的主循环里串行发生**
（`app/repository.py` 执行层那一段）。本进程用 `flock` 独占锁保证「同库只有一个池实例」。
本单独占锁文件：`server/.run/pool.state.lock`（自测专用副本库亦然）。

## 断点续跑（§2.3 / AC-03）

页游标就是 `job_pages`（**落盘**，不在内存）。任一时刻 SIGKILL 掉池与全部 worker 后重启：
`claim_job` 会把该 job 残留的 `RUNNING` 页退回 `PENDING`，**已 `DONE` 的页不再重算**，
于是从断点处继续——最终行数与串行一次跑完相同（重复性由 `(pdf_name,page,idx)` 唯一索引兜底）。

## 幂等（§2.4 / AC-01 / AC-02）

* 行：`stamps` 上 `(pdf_name,page,idx)` 命中 ⇒ 默认 **skip（绝不改写旧行）**，`counters.inserted=0`；
  另有显式 `FEICUI_ON_CONFLICT=update` 形态（内容有别才改，并计入 `updated`）。
* 影像：命名只由 `(book_key,page,idx)` 决定（§4.1 D-4② / §4.2.2）⇒ 同路径；内容 `sha256` 相同
  ⇒ **不重写**；写盘一律「临时文件 + fsync + 原子替换」。

## 开关（都有默认值，默认＝现状行为，不得静默改默认）

| 环境变量 | 默认 | 含义 |
| --- | --- | --- |
| `FEICUI_WORKERS` | **4** | worker 进程数（AC-04 钉值；§5.1 的草案 8 待裁，见 REPORT 规范缺口） |
| `FEICUI_DOC_PREPROCESS` | **1（开）** | doc 预处理（PaddleOCR 默认）；`0` ⇒ 关（spike 实测 1.78×，**会改识别文本**，精度未定论 ⇒ 默认不动） |
| `FEICUI_CPU_THREADS` | **2** | 每 worker 的 `cpu_threads` 上限（派单口径，防线程超订） |
| `FEICUI_ON_CONFLICT` | **skip** | 行级冲突策略 |
| `FEICUI_FACES_DIR` | `<feicui>/output/faces` | 交付影像根（§4.1 D-4②） |
| `FEICUI_WORKER_PYTHON` | `<feicui>/venv/bin/python` | worker 解释器（§6.5 解释器矩阵） |

用法：
    cd /Users/kevin/bistro/shu/feicui/server
    FEICUI_DB=<db> ./.venv/bin/python -m app.pool --workers 4           # 常驻
    FEICUI_DB=<db> ./.venv/bin/python -m app.pool --workers 1 --drain   # 串行基线臂（跑完即退）
"""
from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import books, db, migrations, repository
from .config import REPO_ROOT, Settings, get_settings

WORKER_SCRIPT = Path(__file__).resolve().parents[1] / "worker" / "feicui_worker.py"
MAX_WORKER_DEATHS_PER_JOB = 4  # 超过则把在飞页记 FAILED（不无限重启）
READY_TIMEOUT_S = 240
log = logging.getLogger("feicui.pool")


# --------------------------------------------------------------------------- worker 槽位
class WorkerSlot:
    """一个 worker 子进程槽位：spawn / 发任务 / 读结果（专用读线程）/ 收尸。"""

    def __init__(self, index: int, st: Settings, q: "queue.Queue[dict]") -> None:
        self.index = index
        self.st = st
        self.q = q
        self.proc: subprocess.Popen | None = None
        self.task: dict | None = None
        self.ready = False
        self.spawns = 0
        self.exits = 0
        self.log_path = st.worker_log_dir / f"worker{index}.log"
        self._logfh = None

    # -- 生命周期
    def start(self) -> None:
        self.st.worker_log_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.update(
            {
                "FEICUI_ROOT": str(REPO_ROOT),
                "FEICUI_FACES_DIR": str(self.st.faces_dir),
                "FEICUI_DOC_PREPROCESS": "1" if self.st.doc_preprocess else "0",
                "FEICUI_CPU_THREADS": str(self.st.cpu_threads),
                "PYTHONUNBUFFERED": "1",
            }
        )
        self._logfh = self.log_path.open("a", buffering=1, encoding="utf-8")
        self._logfh.write(
            f"\n=== spawn#{self.spawns} {db.now_iso()} python={self.st.worker_python} "
            f"cwd={REPO_ROOT} doc_preprocess={env['FEICUI_DOC_PREPROCESS']} "
            f"cpu_threads={env['FEICUI_CPU_THREADS']} faces={env['FEICUI_FACES_DIR']}\n"
        )
        self.proc = subprocess.Popen(  # noqa: S603 - 路径来自配置，非用户输入
            [str(self.st.worker_python), str(WORKER_SCRIPT)],
            cwd=str(REPO_ROOT),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._logfh,
            text=True,
            bufsize=1,
        )
        self.spawns += 1
        self.task = None
        self.ready = False
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()
        log.info("worker#%d 已启动 pid=%d（第 %d 次）", self.index, self.proc.pid, self.spawns)

    def _reader(self, proc: subprocess.Popen) -> None:
        """协议读线程：stdout 一行一个 JSON ⇒ 投到共享队列（**只有主循环写 DB**）。"""
        for line in proc.stdout:  # type: ignore[union-attr]
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                self.q.put({"type": "badline", "slot": self.index, "line": line[:400]})
                continue
            msg["slot"] = self.index
            self.q.put(msg)
        self.q.put({"type": "eof", "slot": self.index, "pid": proc.pid})

    # -- 协议
    def send(self, obj: dict) -> bool:
        if self.proc is None or self.proc.poll() is not None or self.proc.stdin is None:
            return False
        try:
            self.proc.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
            return True
        except Exception as exc:
            log.warning("worker#%d 发任务失败：%r", self.index, exc)
            return False

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def pid(self) -> int | None:
        return self.proc.pid if self.proc is not None else None

    def reap(self) -> None:
        if self._logfh is not None:
            try:
                self._logfh.close()
            except Exception:
                pass
            self._logfh = None

    def shutdown(self, timeout: float = 15.0) -> None:
        if not self.alive():
            self.reap()
            return
        self.send({"cmd": "shutdown"})
        try:
            self.proc.wait(timeout=timeout)  # type: ignore[union-attr]
        except Exception:
            log.warning("worker#%d 未在 %ss 内退出 ⇒ SIGTERM", self.index, timeout)
            self.proc.terminate()  # type: ignore[union-attr]
            try:
                self.proc.wait(timeout=8)  # type: ignore[union-attr]
            except Exception:
                self.proc.kill()  # type: ignore[union-attr]
        self.reap()


# --------------------------------------------------------------------------- 池
class Pool:
    def __init__(
        self,
        st: Settings,
        *,
        workers: int,
        drain: bool = False,
        only_job: str | None = None,
        on_conflict: str | None = None,
    ) -> None:
        self.st = st
        self.n = max(1, int(workers))
        self.drain = drain
        self.only_job = only_job
        self.on_conflict = on_conflict or st.on_conflict
        self.q: "queue.Queue[dict]" = queue.Queue()
        self.slots = [WorkerSlot(i, st, self.q) for i in range(self.n)]
        self.job: dict | None = None
        self.tasks: dict[str, dict] = {}
        self.stopping = False
        self.deaths_for_job = 0
        self.job_finished: str | None = None
        self.stats = {
            "chunks_committed": 0,
            "pages_done": 0,
            "pages_failed": 0,
            "detected": 0,
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
            "ocr_empty": 0,
            "requeued_pages": 0,
            "imgs_written": 0,
            "imgs_reused": 0,
            "worker_deaths": 0,
        }
        self._lockfh = None
        self._t0 = time.time()

    # ---------------------------------------------------------------- 启动
    def _acquire_lock(self) -> None:
        self.st.pool_state_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.st.pool_state_path.with_suffix(".lock")
        self._lockfh = lock_path.open("w")
        try:
            fcntl.flock(self._lockfh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print(
                f"⏭ 跳过启动：已有池实例持有该库的写锁（{lock_path}）。\n"
                f"  规范 §4.3：WAL 单写者 ⇒ 同一 DB 只允许一个池进程。\n"
                f"  这是**正常分支**（阶段 1c-激活后由 API 按需拉起，重复拉起即走这里）：\n"
                f"  本进程立刻退出（exit 5），不占资源、不堆进程；已在跑的池会自己取活。",
                file=sys.stderr,
            )
            raise SystemExit(5)
        self._lockfh.write(f"{os.getpid()} {db.now_iso()}\n")
        self._lockfh.flush()

    def start(self) -> None:
        st = self.st
        if not st.db_path.is_file():
            print(f"✗ DB 不存在：{st.db_path}", file=sys.stderr)
            raise SystemExit(2)
        if not st.worker_python.is_file():
            print(f"✗ worker 解释器不存在：{st.worker_python}（§6.5 解释器矩阵）", file=sys.stderr)
            raise SystemExit(2)
        if not WORKER_SCRIPT.is_file():
            print(f"✗ worker 脚本不存在：{WORKER_SCRIPT}", file=sys.stderr)
            raise SystemExit(2)
        if self.on_conflict not in {repository.ON_CONFLICT_SKIP, repository.ON_CONFLICT_UPDATE}:
            print(f"✗ FEICUI_ON_CONFLICT 只能是 skip|update，当前 = {self.on_conflict}", file=sys.stderr)
            raise SystemExit(2)

        # 迁移幂等入口：表 / 索引（含行级幂等唯一索引）必须在位；正式库受安全闸保护
        rc = migrations.run()
        if rc != 0:
            print(f"✗ 迁移未通过（exit={rc}）⇒ 拒绝启动池", file=sys.stderr)
            raise SystemExit(rc)
        self._acquire_lock()

        log.info(
            "池启动：workers=%d db=%s faces=%s doc_preprocess=%s cpu_threads=%s on_conflict=%s "
            "worker_python=%s manager_python=%s",
            self.n,
            st.db_path,
            st.faces_dir,
            st.doc_preprocess,
            st.cpu_threads,
            self.on_conflict,
            st.worker_python,
            sys.executable,
        )
        log.info("🔒 单写者锁：%s", self.st.pool_state_path.with_suffix(".lock"))
        for slot in self.slots:
            slot.start()
        self._await_ready()
        self._write_state(reason="started")

    def _await_ready(self) -> None:
        """等所有 worker 报 ready（＝OCR 已预热完成，§5.2「worker 启动即预热」）。"""
        deadline = time.time() + READY_TIMEOUT_S
        while time.time() < deadline:
            self._pump(allow_commit=False)
            if all(s.ready for s in self.slots):
                return
            if any(not s.alive() for s in self.slots):
                log.error("有 worker 启动即退出 ⇒ 中止（见 %s）", self.st.worker_log_dir)
                raise SystemExit(6)
            time.sleep(0.2)
        log.error("等 worker ready 超时（%ss）", READY_TIMEOUT_S)
        raise SystemExit(6)

    # ---------------------------------------------------------------- 主循环
    def run(self) -> int:
        self.start()
        try:
            while True:
                self._pump()
                self._check_workers()
                if self.job is None:
                    self._pick_job()
                if self.job is not None:
                    self._dispatch()
                    self._maybe_finish_job()
                self._write_state(reason="tick")
                if self._should_stop():
                    break
                time.sleep(self.st.poll_interval)
            log.info("池退出：%s", json.dumps(self.stats, ensure_ascii=False))
            return 0
        finally:
            self._teardown()

    def _should_stop(self) -> bool:
        if self.stopping:
            return True
        if self.only_job and self.job is None and self.job_finished:
            return True
        if self.drain and self.job is None and not self._in_flight():
            if not repository.list_active_jobs(self.st.db_path):
                return True
        return False

    def _in_flight(self) -> bool:
        return any(s.task is not None for s in self.slots) or bool(self.tasks)

    # ---------------------------------------------------------------- 取活 / 派活
    def _pick_job(self) -> None:
        claimed = repository.claim_job(self.st.db_path, job_id=self.only_job)
        if claimed is None:
            return
        pdf_name = claimed["pdf_name"]
        template, alias = books.template_for(pdf_name)
        book_key = books.book_key_for(pdf_name)
        claimed.update({"book_key": book_key, "template": template, "template_alias": alias})
        self.deaths_for_job = 0
        self.job_finished = None
        self.job = claimed
        self._last_job = claimed
        if not books.template_usable(template):
            missing = books.missing_template_keys(template)
            err = f"template_unusable: missing keys {missing}"
            log.error("job %s 模板不可用（缺 %s）⇒ 全部待办页记 FAILED，job 一次落终态", claimed["job_id"], missing)
            self._fail_all_pending(claimed, err)
            # ★ 收口（本轮修复）：模板不可用时**必须当场把 job 写进终态**。
            # 否则 state 停在 `claim_job` 刚置的 `RUNNING` ⇒ 该 job 仍是「活跃 job」，
            # 下一个 tick 又被 `claim_job` 认领 ⇒ 池每 ~0.3 s 无限重试（白烧 CPU、E2 永远「解析中」）。
            # 与常规收尾同源：复用 `maybe_finalize_job`（页全到终态 ⇒ FAILED_PARTIAL），
            # 并把 `jobs.error` 覆写成本次真实原因（而不是泛化的 `failed_pages=`）。
            state = repository.maybe_finalize_job(self.st.db_path, claimed["job_id"], error=err)
            if state is None:  # 理论不可达：`_fail_all_pending` 已把 PENDING/RUNNING 页全部记 FAILED
                log.error("job %s 收尾异常：仍见待办页（state 未落终态）", claimed["job_id"])
            log.error("job %s 收尾 ⇒ %s（error=%s）", claimed["job_id"], state, err)
            self.job = None
            self.job_finished = state or "FAILED_PARTIAL"
            return
        log.info(
            "认领 job %s：pdf=%s book_key=%s 模板别名=%s 页区间=[%s,%s] chunk_size=%s "
            "残留 RUNNING 页退回 PENDING=%s（断点续跑入口）",
            claimed["job_id"],
            claimed["pdf_path"],
            book_key,
            alias,
            claimed["page_from"],
            claimed["page_to"],
            claimed["chunk_size"],
            claimed["reset_running_pages"],
        )

    def _fail_all_pending(self, job: dict, error: str) -> None:
        with db.ro(self.st.db_path) as conn:
            pages = [
                int(r[0])
                for r in db.query_all(
                    conn,
                    "SELECT page FROM job_pages WHERE job_id=? AND state IN ('PENDING','RUNNING') ORDER BY page",
                    (job["job_id"],),
                )
            ]
        repository.fail_pages(self.st.db_path, job_id=job["job_id"], pages=pages, error=error)
        self.stats["pages_failed"] += len(pages)
        log.error("job %s：%d 页记 FAILED（%s）", job["job_id"], len(pages), error)

    def _dispatch(self) -> None:
        job = self.job
        assert job is not None
        idle = [s for s in self.slots if s.task is None and s.alive()]
        while idle:
            chunk = repository.claim_next_chunk(self.st.db_path, job["job_id"])
            if chunk is None:
                return
            slot = idle.pop(0)
            task_id = f"{job['job_id']}#c{chunk['chunk_index']}"
            req = {
                "cmd": "process_chunk",
                "task_id": task_id,
                "pdf_path": job["pdf_path"],
                "book_key": job["book_key"],
                "template": job["template"],
                "pages": chunk["pages"],
                "faces_dir": str(self.st.faces_dir),
                "rel_root": str(REPO_ROOT),
            }
            task = {
                "task_id": task_id,
                "job_id": job["job_id"],
                "chunk_index": chunk["chunk_index"],
                "pages": [int(p) for p in chunk["pages"]],
                "results": {},
                "slot": slot.index,
                "sent_at": time.time(),
            }
            self.tasks[task_id] = task
            if not slot.send(req):
                # 发不出去 ⇒ 立刻退页，不放坏游标（页仍在 PENDING，下轮重派）
                repository.requeue_pages(
                    self.st.db_path, job_id=job["job_id"], pages=task["pages"], error="dispatch_failed"
                )
                del self.tasks[task_id]
                return
            slot.task = task
            log.info(
                "派 chunk c%d（页 %s）→ worker#%d task=%s [并发在飞=%d]",
                chunk["chunk_index"],
                chunk["pages"],
                slot.index,
                task_id,
                len(self.tasks),
            )

    # ---------------------------------------------------------------- 收结果
    def _pump(self, allow_commit: bool = True) -> None:
        while True:
            try:
                msg = self.q.get_nowait()
            except queue.Empty:
                return
            mtype = msg.get("type")
            if mtype == "ready":
                slot = self.slots[msg["slot"]]
                slot.ready = True
                log.info(
                    "worker#%d ready pid=%s python=%s exe=%s cwd=%s paddleocr=%s doc_preprocess=%s "
                    "cpu_threads=%s faces=%s",
                    msg["slot"],
                    msg.get("pid"),
                    msg.get("python"),
                    msg.get("exe"),
                    msg.get("cwd"),
                    msg.get("paddleocr"),
                    msg.get("doc_preprocess"),
                    msg.get("cpu_threads"),
                    msg.get("faces_dir"),
                )
            elif mtype == "page":
                self._on_page(msg, allow_commit)
            elif mtype == "chunk_done":
                task = self.tasks.get(msg.get("task_id", ""))
                if task is not None and allow_commit:
                    missing = [p for p in task["pages"] if p not in task["results"]]
                    if missing:
                        log.warning("task %s chunk_done 但缺页 %s ⇒ 记 FAILED 后提交", task["task_id"], missing)
                    self._commit_task(task)
            elif mtype == "eof":
                log.warning("worker#%d 进程退出（pid=%s）", msg.get("slot"), msg.get("pid"))
            elif mtype == "badline":
                log.warning("worker#%d 输出非 JSON 行（协议污染）：%s", msg.get("slot"), msg.get("line"))
            else:
                log.debug("忽略消息：%s", mtype)

    def _on_page(self, msg: dict, allow_commit: bool) -> None:
        task = self.tasks.get(msg.get("task_id", ""))
        if task is None:
            log.warning("收到未知 task 的页结果：%s（已被收尾？）", msg.get("task_id"))
            return
        task["results"][int(msg["page"])] = msg
        if msg.get("ok"):
            self.stats["detected"] += int(msg.get("detected", 0))
            self.stats["ocr_empty"] += int(msg.get("ocr_empty", 0))
            for item in msg.get("items", []):
                self.stats["imgs_written" if item.get("img_written") else "imgs_reused"] += 1
        if allow_commit and set(task["results"]) >= set(task["pages"]):
            self._commit_task(task)

    def _commit_task(self, task: dict) -> None:
        page_results = []
        for page in task["pages"]:
            m = task["results"].get(page)
            if m is None:
                page_results.append({"page": page, "ok": False, "error": "no result (worker crashed)"})
                continue
            page_results.append(
                {
                    "page": page,
                    "ok": bool(m.get("ok")),
                    "error": m.get("error"),
                    "detected": int(m.get("detected", 0)),
                    "ocr_empty": int(m.get("ocr_empty", 0)),
                    "items": m.get("items", []),
                    "pdf_name": self.job["pdf_name"] if self.job else None,
                }
            )
        res = repository.commit_chunk(
            self.st.db_path,
            job_id=task["job_id"],
            chunk_index=task["chunk_index"],
            page_results=page_results,
            on_conflict=self.on_conflict,
        )
        c = res["counters"]
        self.stats["chunks_committed"] += 1
        self.stats["pages_done"] += sum(1 for pr in page_results if pr["ok"])
        self.stats["pages_failed"] += len(res["failed_pages"])
        for k in ("detected", "inserted", "updated", "skipped", "ocr_empty"):
            self.stats[k] += c[k] if k in c else 0
        log.info(
            "提交 chunk c%d（页 %s）：inserted=%d updated=%d skipped=%d failed=%s | 累计 页=%d chunk=%d",
            task["chunk_index"],
            task["pages"],
            c["inserted"],
            c["updated"],
            c["skipped"],
            res["failed_pages"],
            self.stats["pages_done"],
            self.stats["chunks_committed"],
        )
        slot = self.slots[task["slot"]]
        if slot.task is not None and slot.task["task_id"] == task["task_id"]:
            slot.task = None
        del self.tasks[task["task_id"]]

    # ---------------------------------------------------------------- 收尸 / 续跑
    def _check_workers(self) -> None:
        for slot in self.slots:
            if slot.alive():
                continue
            if slot.proc is None:
                continue
            slot.exits += 1
            task = slot.task
            if task is not None:
                missing = [p for p in task["pages"] if p not in task["results"]]
                self.deaths_for_job += 1
                self.stats["worker_deaths"] += 1
                if self.deaths_for_job > MAX_WORKER_DEATHS_PER_JOB:
                    log.error("worker#%d 反复退出（第 %d 次）⇒ 页 %s 记 FAILED", slot.index, self.deaths_for_job, missing)
                    repository.fail_pages(
                        self.st.db_path,
                        job_id=task["job_id"],
                        pages=missing,
                        error=f"worker_died_repeatedly(slot={slot.index})",
                    )
                    self.stats["pages_failed"] += len(missing)
                else:
                    n = repository.requeue_pages(
                        self.st.db_path,
                        job_id=task["job_id"],
                        pages=missing,
                        error=f"worker_died(slot={slot.index}) → 退回 PENDING 续跑",
                    )
                    self.stats["requeued_pages"] += n
                    log.warning("worker#%d 死在 task %s ⇒ 页 %s 退回 PENDING（%d 行）", slot.index, task["task_id"], missing, n)
                if task["task_id"] in self.tasks:
                    del self.tasks[task["task_id"]]
            slot.reap()
            slot.task = None
            slot.start()  # 立刻补位（常驻池：任何时刻都保持 N 个 worker）
        self._write_state(reason="respawn")

    def _maybe_finish_job(self) -> None:
        job = self.job
        assert job is not None
        inflight = [t for t in self.tasks.values() if t["job_id"] == job["job_id"]]
        st = repository.job_outstanding(self.st.db_path, job["job_id"])
        if inflight or st["pending"] or st["running"]:
            return
        state = repository.maybe_finalize_job(self.st.db_path, job["job_id"])
        if state is None:
            return
        self.job_finished = state
        log.info(
            "job %s 收尾 ⇒ %s（total=%d done=%d failed=%d）",
            job["job_id"],
            state,
            st["total"],
            st["done"],
            st["failed"],
        )
        self.job = None

    # ---------------------------------------------------------------- 状态文件 / 收尾
    def _write_state(self, *, reason: str = "") -> None:
        """写状态文件：**自测 / 运维据此用精确 PID 停进程**（严禁宽匹配 kill）。"""
        payload = {
            "pool_pid": os.getpid(),
            "manager_python": sys.executable,
            "db": str(self.st.db_path),
            "faces_dir": str(self.st.faces_dir),
            "workers": [
                {"index": s.index, "pid": s.pid(), "alive": s.alive(), "ready": s.ready, "spawns": s.spawns,
                 "task": (s.task or {}).get("task_id")}
                for s in self.slots
            ],
            "doc_preprocess": self.st.doc_preprocess,
            "cpu_threads": self.st.cpu_threads,
            "on_conflict": self.on_conflict,
            "job": (self.job or {}).get("job_id"),
            "job_finished": self.job_finished,
            "in_flight_tasks": sorted(self.tasks),
            "stats": self.stats,
            "uptime_s": round(time.time() - self._t0, 1),
            "updated_at": db.now_iso(),
            "reason": reason,
        }
        tmp = self.st.pool_state_path.with_suffix(".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.st.pool_state_path)

    def _teardown(self) -> None:
        for slot in self.slots:
            slot.shutdown()
        try:
            self._write_state(reason="stopped")
        except Exception:
            pass
        if self._lockfh is not None:
            try:
                fcntl.flock(self._lockfh, fcntl.LOCK_UN)
                self._lockfh.close()
            except Exception:
                pass


# --------------------------------------------------------------------------- CLI
def _install_signals(pool: Pool) -> None:
    def handler(signum, _frame):  # noqa: ANN001
        pool.stopping = True
        log.warning("收到信号 %s ⇒ 优雅退出（当前 chunk 提交后停）", signum)

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, handler)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    ap = argparse.ArgumentParser(description="feicui 常驻 worker 池（唯一写者）")
    ap.add_argument("--workers", type=int, default=None, help="worker 进程数（默认 FEICUI_WORKERS / 4）")
    ap.add_argument("--drain", action="store_true", help="跑完当前所有活跃 job 即退出（自测用）")
    ap.add_argument("--job", default=None, help="只跑指定 job_id（调试用）")
    ap.add_argument("--on-conflict", default=None, choices=["skip", "update"], help="行级冲突策略")
    ap.add_argument("--list", action="store_true", help="只列出活跃 job 后退出（只读）")
    args = ap.parse_args(argv)

    st = get_settings()
    if args.list:
        for j in repository.list_active_jobs(st.db_path):
            print(json.dumps(j, ensure_ascii=False))
        return 0

    workers = args.workers or st.workers
    pool = Pool(st, workers=workers, drain=args.drain, only_job=args.job, on_conflict=args.on_conflict)
    _install_signals(pool)
    return pool.run()


if __name__ == "__main__":
    raise SystemExit(main())
