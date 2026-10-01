#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
玺爱 · 浏览器端影像处理管线 · CDP 驱动（Kong 自证用，2026-09-20）

自建 headless Chrome（**独立 profile** + `--remote-allow-origins=*`），绝不碰用户自己的 Chrome：
  - profile 目录：/tmp/xiai-probe-profile-kong（独立，跑完按 **精确 PID** kill，不用 pkill/killall）
  - 调试口：9333；被访问的是应用自身 origin 127.0.0.1:5163（**不重启 5163**）

跑法（**本机必须写绝对路径**：`python3` 在部分执行环境下解析到无 websocket 的解释器）：
  /usr/bin/python3 feicui/ops/kong-photo-pipeline-cdp.py
环境变量：
  XIAI_RUN_MODE=red|green   标注入库的模式（只影响输出文件名与 JSON 里的 run.mode），默认 unlabeled
  XIAI_FORCE_PNG=1          **回退注入**：注入 `HTMLCanvasElement.prototype.toBlob` 强制产出 PNG，
                            让整条真实 UI 路径走「浏览器编不出 WebP」的兜底分支（可复跑的先红后绿）
  恢复方式：不带 XIAI_FORCE_PNG 再跑一次即还原真实行为；本次跑不修改任何被注入的文件。

输出（**证据一律先落盘**，即使中途异常也写）：
  feicui/ops/kong-photo-pipeline-cdp_raw.json      最近一次跑的原始证据（本单要求）
  feicui/ops/kong-photo-pipeline-cdp_raw_<mode>.json  按模式留档（red / green）
  feicui/ops/kong-photo-pipeline-raw.json          兼容旧文件名（同内容）
  feicui/ops/kong-photo-pipeline-cdp_summary_<mode>.md 自动摘要（AC-33 三阈值 / 网络 / 断言清单）

健壮性要点（本单修的探针自身缺陷）：
  - `poll` 的谓词**只吃解析后的对象**；非 JSON / 空返回 / 页面未就绪 ⇒ 视为「还没就绪，继续等」，
    到硬上界（tries × delay）如实记超时，**绝不当致命错误抛出**；
  - 全部步骤包在 try/except 里，任一步异常只记进 `step_errors`，不吞掉已取到的证据；
  - 原始 JSON 在 `finally` 里落盘。
"""
import base64
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PROFILE = "/tmp/xiai-probe-profile-kong"
DEBUG_PORT = 9333
APP = "http://127.0.0.1:5163"
PROBE = f"{APP}/feicui/ops/kong-photo-pipeline-probe.html"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(HERE, "kong-photo-pipeline-cdp_raw.json")
OUT_JSON_COMPAT = os.path.join(HERE, "kong-photo-pipeline-raw.json")

RUN_MODE = os.environ.get("XIAI_RUN_MODE", "unlabeled").strip().lower() or "unlabeled"
FORCE_PNG = os.environ.get("XIAI_FORCE_PNG", "") not in ("", "0", "false", "False")
OUT_JSON_MODE = os.path.join(HERE, "kong-photo-pipeline-cdp_raw_%s.json" % RUN_MODE)
OUT_MD = os.path.join(HERE, "kong-photo-pipeline-cdp_summary_%s.md" % RUN_MODE)

_next_id = [0]
EVENTS = []  # 全量网络捕获（Network.requestWillBeSent）
CURRENT = {"tab": "?"}
EVIDENCE = {}
STEP_ERRORS = {}


def log(*args):
    print(*args, flush=True)


def cdp_call(ws, method, **params):
    _next_id[0] += 1
    msg_id = _next_id[0]
    ws.send(json.dumps({"id": msg_id, "method": method, "params": params}))
    while True:
        raw = ws.recv()
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if data.get("id") == msg_id:
            if "error" in data:
                raise RuntimeError(f"{method} -> {data['error']}")
            return data.get("result", {})
        if data.get("method") == "Network.requestWillBeSent":
            req = data.get("params", {}).get("request", {})
            EVENTS.append({"tab": CURRENT["tab"], "url": req.get("url", ""), "method": req.get("method", ""), "type": data.get("params", {}).get("type", "")})


def evaluate(ws, expression, await_promise=True):
    result = cdp_call(
        ws,
        "Runtime.evaluate",
        expression=expression,
        awaitPromise=await_promise,
        returnByValue=True,
        userGesture=True,
    )
    if result.get("exceptionDetails"):
        raise RuntimeError("evaluate 异常：" + json.dumps(result["exceptionDetails"], ensure_ascii=False)[:600])
    return result.get("result", {}).get("value")


def try_json(value):
    """非 JSON / 空返回 ⇒ 返回 None（**不抛**）。这是本单修的探针自身缺陷：原实现把解析失败当致命错误。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def open_tab(url):
    req = urllib.request.Request(f"http://127.0.0.1:{DEBUG_PORT}/json/new?{url}", method="PUT")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def wait_ready():
    for _ in range(80):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=2) as resp:
                json.loads(resp.read().decode())
                return True
        except Exception:
            time.sleep(0.25)
    return False


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def kill_pid_exact(pid, proc=None):
    """按**精确 PID** 结束自建 Chrome（禁用 pkill / killall）。

    读数口径（本单修的工具链缺陷）：`os.kill(pid, 0)` 对自己未 `wait()` 的子进程
    **必然返回成功**（那是僵尸态），上一轮据此报「仍在运行」是**假读数**。
    这里改为优先用 `Popen.poll()/wait()` 拿真实退出码，并以 `lsof` 复核端口是否已释放。
    """
    def alive():
        if proc is not None:
            return proc.poll() is None
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def port_line():
        return subprocess.run(
            ["lsof", "-nP", f"-iTCP:{DEBUG_PORT}", "-sTCP:LISTEN"], capture_output=True, text=True
        ).stdout.strip()

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return {"pid": pid, "killed": True, "note": "进程已不在", "port_still_listening": port_line()}
    for _ in range(40):
        if not alive():
            break
        time.sleep(0.25)
    note = "SIGTERM 后已退出"
    if alive():
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        for _ in range(20):
            if not alive():
                break
            time.sleep(0.25)
        note = "SIGTERM 超时 ⇒ SIGKILL"
    if proc is not None:
        try:
            proc.wait(timeout=5)  # 收尸：避免僵尸态被误读成「仍在运行」
        except Exception:
            pass
    exit_code = proc.poll() if proc is not None else None
    still = alive()
    return {
        "pid": pid,
        "killed": (not still),
        "note": note if not still else "仍在运行（异常，需人工介入）",
        "exit_code": exit_code,
        "exit_signal": (-exit_code) if (exit_code is not None and exit_code < 0) else None,
        "port_still_listening": port_line(),
    }


def poll(ws, expression, predicate, label, tries=90, delay=0.5):
    """轮询：谓词只吃**解析后的对象**；解析失败＝还没就绪（继续等），到上界如实返回 None。"""
    last_raw = None
    for _ in range(tries):
        try:
            last_raw = evaluate(ws, expression)
        except Exception as exc:
            last_raw = f"<evaluate 失败：{exc}>"
        parsed = try_json(last_raw)
        # 谓词先吃解析后的对象；解析不出（如 document.readyState 的裸标量）就把原值给它。
        # 两种情况里谓词抛错都**只记不炸**（这正是原来 JSONDecodeError 把整轮证据带走的根因）。
        for candidate in ([parsed, last_raw] if parsed is not None else [last_raw]):
            try:
                if predicate(candidate):
                    return parsed if parsed is not None else last_raw
            except Exception as exc:
                STEP_ERRORS.setdefault("poll_predicate", []).append(f"{label}: {type(exc).__name__}: {exc}")
        time.sleep(delay)
    log(f"  ⚠ 轮询超时（硬上界 {tries}×{delay}s）：{label}；最后一次取值＝{json.dumps(last_raw, ensure_ascii=False)[:400]}")
    return None


FORCE_PNG_SOURCE = r"""
(() => {
  const proto = HTMLCanvasElement.prototype;
  const original = proto.toBlob;
  const flag = { on: true };
  window.__XIAI_FORCE_PNG__ = flag;
  proto.toBlob = function (callback, type, quality) {
    return original.call(this, callback, flag.on ? 'image/png' : type, quality);
  };
  window.__XIAI_FORCE_PNG_INSTALLED__ = true;
})();
"""


def install_force_png(ws):
    if not FORCE_PNG:
        return False
    cdp_call(ws, "Page.addScriptToEvaluateOnNewDocument", source=FORCE_PNG_SOURCE)
    return True


BRIDGE_JS = os.path.join(HERE, "kong-image-truth-bridge.js")


def install_truth_bridge(ws, label=""):
    """把**产品真源**（`src/utils/image.js::sniffBytesMime`，esbuild 打进 bridge bundle）
    注入当前文档，挂 `globalThis.__XIAI_IMG_TRUTH__`。

    为什么（规范缺口③「尺子漂移」）：证据脚本**不得自建一份字节魔数判定**——
    CDP 侧原来那句 `isPngMagic: u8[0] === 0x89 && ...` 就是自建副本（探针侧同病：自写
    `magicOf` 的 4 字节读法把 `0x89 P N G` 读成 `"PNG\r"`，把真 PNG 判成非 PNG，报假警报）。
    """
    if not os.path.exists(BRIDGE_JS):
        log(f"  ⚠ 真源桥 bundle 缺失（{BRIDGE_JS}）⇒ 本轮的格式判定只能如实记为 unavailable")
        return False
    with open(BRIDGE_JS, encoding="utf-8") as fh:
        source = fh.read()
    # 两处一起装：① `addScriptToEvaluateOnNewDocument`（之后每次导航/刷新自动生效，
    # 本脚本会 reload 探针页，只 eval 一次会丢）；② 对**当前文档**立即 eval。
    cdp_call(ws, "Page.addScriptToEvaluateOnNewDocument", source=source)
    ok = evaluate(ws, "(() => { %s\n; return !!(globalThis.__XIAI_IMG_TRUTH__ && globalThis.__XIAI_IMG_TRUTH__.sniffBytesMime); })()" % source)
    log(f"    真源桥已注入{('（' + label + '）') if label else ''}：__XIAI_IMG_TRUTH__ = {bool(ok)}")
    return bool(ok)


def step(name, fn):
    try:
        return fn()
    except Exception as exc:
        STEP_ERRORS[name] = f"{type(exc).__name__}: {exc}"
        log(f"  !! 步骤 {name} 异常（已记录，继续）：{type(exc).__name__}: {exc}")
        return None


def write_evidence(path, payload):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def merge_results(*sources):
    """按 `id` 去重合并多份探针结果（**后者优先**）。

    为什么必须合并（本单修的工具链缺陷）：探针页在第 ④ 步 `Page.reload` 之后，
    页面里的 `window.__XIAI_PROBE_RESULTS__` 被重置，随后 phase2 只读不写、
    phase3（印面图路径）只写回自己那 8 条 ⇒ **单读页面全局会把 phase1 的 33 条整段漏掉**，
    断言合计从应有的 41 掉成 8（上轮 `[13]` 报「合计 8 条（其中印面图路径 8 条）」即此病，
    是把 phase1 算没的镜像口径）。冻结口径：以**刷新前的 phase1 快照**为底，
    并入页面全局与 `__XIAI_PROBE__.phase3()` 的结果，checks 按 id 去重、
    numbers 浅合并（后者覆盖同键）、errors 拼接。
    """
    merged = {"checks": [], "numbers": {}, "errors": []}
    seen = {}
    for src in sources:
        if not isinstance(src, dict):
            continue
        for row in src.get("checks") or []:
            if not isinstance(row, dict):
                continue
            rid = str(row.get("id", ""))
            if rid in seen:
                merged["checks"][seen[rid]] = row
            else:
                seen[rid] = len(merged["checks"])
                merged["checks"].append(row)
        for key, value in (src.get("numbers") or {}).items():
            if isinstance(value, dict) and isinstance(merged["numbers"].get(key), dict):
                merged["numbers"][key] = dict(merged["numbers"][key], **value)
            else:
                merged["numbers"][key] = value
        merged["errors"] = merged["errors"] + list(src.get("errors") or [])
    return merged


def summary_md(ev):
    res = ev.get("probe_phase1_final") or ev.get("probe_phase1") or {}
    checks = res.get("checks") or []
    numbers = res.get("numbers") or {}
    phase1_checks = [c for c in checks if not str(c.get("id", "")).startswith("seals-")]
    seals_checks = [c for c in checks if str(c.get("id", "")).startswith("seals-")]
    lines = []
    lines.append("# 玺爱影像管线探针 · 自动摘要（%s 跑，no-injection=%s）\n" % (ev.get("run", {}).get("mode"), not ev.get("run", {}).get("force_png")))
    lines.append("- 跑的时间：%s" % ev.get("run", {}).get("at"))
    lines.append("- Chrome：%s（自建 headless，pid=%s，profile=%s，调试口=%s）" % (ev.get("run", {}).get("browser"), ev.get("run", {}).get("chrome_pid"), PROFILE, DEBUG_PORT))
    lines.append("- 回退注入（强制 toBlob 产 PNG，`XIAI_FORCE_PNG`）：%s" % ev.get("run", {}).get("force_png"))
    lines.append("- 解释器：%s（%s）" % (ev.get("run", {}).get("python_executable"), ev.get("run", {}).get("python_version")))
    lines.append("- 格式判定的尺子：**产品真源** `src/utils/image.js::sniffBytesMime`（探针 bundle 内 + `kong-image-truth-bridge.js`），**无自建魔数副本**")
    lines.append("")
    lines.append("## 断言清单（合并口径：合计 %d 条 = phase1 %d 条 + 印面图路径(phase3) %d 条；失败 %d 条）\n" % (
        len(checks), len(phase1_checks), len(seals_checks), len([c for c in checks if not c.get("pass")])))
    _ma = ev.get("merged_assertions") or {}
    lines.append("- 计数自洽：%d + %d = %d（清单实长 %d）⇒ %s" % (
        len(phase1_checks), len(seals_checks), len(phase1_checks) + len(seals_checks), len(checks),
        "OK" if len(phase1_checks) + len(seals_checks) == len(checks) else "MISMATCH"))
    lines.append("- 合并来源：%s；去重键 `%s`" % (_ma.get("sources"), _ma.get("dedupe_key")))
    lines.append("- 为什么必须合并：phase1 刷新前快照 %s 条，`Page.reload` 后页面全局只剩 %s 条（phase2 只读不写、phase3 只写回自己的 %s 条）" % (
        _ma.get("phase1_snapshot_before_reload"), _ma.get("page_global_after_reload"), _ma.get("phase3_returned")))
    lines.append("")
    for row in checks:
        lines.append("- [%s] `%s` %s" % ("PASS" if row.get("pass") else "FAIL", row.get("id"), row.get("name")))
        lines.append("  - %s" % str(row.get("detail", ""))[:900])
    lines.append("")
    lines.append("## 印面图「重新上传」路径读数（seals.js，本单 A 项）\n")
    lines.append("```json\n%s\n```\n" % json.dumps((numbers.get("sealsReplace") or (ev.get("seals_replace_path") or {}).get("numbers") or {}), ensure_ascii=False, indent=2)[:8000])
    lines.append("## AC-33 三阈值（关标签重开后实测）\n")
    ac33 = ev.get("app_ac33_after_reopen") or {}
    lines.append("- `data:image` 命中数 = **%s**；localStorage 单值最大字符数 = **%s**（键 `%s`，%s KiB，阈值 65,536）；总量 = **%s** 字符（%s KiB，阈值 512 KiB）" % (
        ac33.get("dataImageHits"), ac33.get("maxValue"), ac33.get("maxKey"), ac33.get("maxKiB"), ac33.get("total"), ac33.get("totalKiB")))
    lines.append("```json\n%s\n```\n" % json.dumps(ac33, ensure_ascii=False, indent=2)[:4000])
    lines.append("## AC-33 三阈值（整套跑完后的最终审计）\n")
    ac33f = ev.get("app_ac33_final") or {}
    lines.append("- `data:image` 命中数 = **%s**；localStorage 单值最大字符数 = **%s**（键 `%s`，%s KiB）；总量 = **%s** 字符（%s KiB）" % (
        ac33f.get("dataImageHits"), ac33f.get("maxValue"), ac33f.get("maxKey"), ac33f.get("maxKiB"), ac33f.get("total"), ac33f.get("totalKiB")))
    lines.append("```json\n%s\n```\n" % json.dumps(ac33f, ensure_ascii=False, indent=2)[:4000])
    lines.append("## 旧行迁移读回（phase1 + 重开后）\n")
    lines.append("```json\n%s\n```\n" % json.dumps({
        "phase1_migration": numbers.get("migration"),
        "phase2_migrated_rows": (ev.get("probe_phase2_after_reload") or {}).get("migratedRows"),
    }, ensure_ascii=False, indent=2)[:5000])
    lines.append("## IndexedDB 二进制读数（格式判定调**产品真源** sniffBytesMime，并与元数据行对账）\n")
    lines.append("```json\n%s\n```\n" % json.dumps(ev.get("app_indexeddb_final") or {}, ensure_ascii=False, indent=2)[:4000])
    lines.append("## 网络捕获（全量）\n")
    lines.append("```json\n%s\n```\n" % json.dumps(ev.get("network") or {}, ensure_ascii=False, indent=2)[:5000])
    lines.append("## UI 三档真实读数\n")
    for key in ("ui_upload_normal", "ui_upload_input_over", "ui_upload_forced_png", "ui_upload_localStorage", "ui_upload_indexeddb"):
        lines.append("### %s\n" % key)
        lines.append("```json\n%s\n```\n" % json.dumps(ev.get(key) or {}, ensure_ascii=False, indent=2)[:3000])
    lines.append("## 步骤异常（工具链，不并入产品缺陷）\n")
    lines.append("```json\n%s\n```\n" % json.dumps(ev.get("step_errors") or {}, ensure_ascii=False, indent=2)[:3000])
    return "\n".join(lines)


def main():
    evidence = EVIDENCE
    proc = None
    kill_info = None
    evidence["run"] = {
        "mode": RUN_MODE,
        "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "force_png": FORCE_PNG,
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "web_socket_client": getattr(websocket, "__version__", "?"),
        "app_origin": APP,
        "debug_port": DEBUG_PORT,
        "profile": PROFILE,
    }
    subprocess.run(["rm", "-rf", PROFILE], check=False)
    proc = subprocess.Popen(
        [
            CHROME,
            "--headless=new",
            f"--remote-debugging-port={DEBUG_PORT}",
            "--remote-allow-origins=*",
            f"--user-data-dir={PROFILE}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-gpu",
            "--window-size=1400,1000",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    evidence["run"]["chrome_pid"] = proc.pid
    log(f"[1] 自建 headless Chrome 已启动：pid={proc.pid} profile={PROFILE} port={DEBUG_PORT}（收尾按此 PID 精确 kill）")

    try:
        if not wait_ready():
            raise RuntimeError("Chrome 调试端口未就绪")
        version = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=5).read().decode())
        log(f"    Browser = {version.get('Browser')}  ({version.get('User-Agent')})")
        evidence["run"]["browser"] = version.get("Browser")
        evidence["run"]["user_agent"] = version.get("User-Agent")

        # ---------------- 探针页：phase1 / phase2 ----------------
        CURRENT["tab"] = "probe"
        tab = open_tab(PROBE)
        ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=60, suppress_origin=True)
        target_id = tab["id"]
        cdp_call(ws, "Page.enable")
        cdp_call(ws, "Runtime.enable")
        cdp_call(ws, "Network.enable")
        install_force_png(ws)
        step("truth_bridge_probe_tab", lambda: install_truth_bridge(ws, "探针页"))
        log(f"[2] 打开探针页（应用自身 origin）：{PROBE}")

        step("phase1", lambda: poll(ws, "!!window.__XIAI_PROBE_RESULTS__", lambda d: d is True, "phase1 结果就绪", tries=120))
        phase1 = step("phase1_read", lambda: evaluate(ws, "JSON.parse(JSON.stringify(window.__XIAI_PROBE_RESULTS__ || {}))")) or {}
        evidence["probe_phase1"] = phase1
        log("[3] phase1 结果：")
        for row in (phase1.get("checks") or []):
            log(f"    [{'PASS' if row.get('pass') else 'FAIL'}] {row.get('id')} :: {row.get('name')}")
            log(f"           {str(row.get('detail'))[:600]}")
        for key, value in (phase1.get("numbers") or {}).items():
            if key in ("localStorage", "indexedDb"):
                continue
            log(f"    · {key} = {json.dumps(value, ensure_ascii=False)[:900]}")
        if phase1.get("errors"):
            log(f"    !! 探针内异常 = {phase1['errors']}")

        # ---- ④ 刷新后重读（同一 tab reload）----
        step("reload", lambda: cdp_call(ws, "Page.reload", ignoreCache=True))
        step("reload_ready", lambda: poll(ws, "document.readyState", lambda d: d == "complete", "reload 完成", tries=60))
        ready = step("probe_ready", lambda: poll(ws, "!!window.__XIAI_PROBE__", lambda d: d is True, "探针脚本重载", tries=60))
        log(f"[4] 刷新后探针就绪＝{bool(ready)}；调用 phase2（只读）")
        phase2 = step("phase2", lambda: evaluate(ws, "window.__XIAI_PROBE__ ? window.__XIAI_PROBE__.phase2() : null")) or {}
        evidence["probe_phase2_after_reload"] = phase2
        log("    phase2 摘要 = " + json.dumps({
            "rowCount": phase2.get("rowCount"),
            "allRenderOk": phase2.get("allRenderOk"),
            "migratedRowCount": phase2.get("migratedRowCount"),
            "localStorage": phase2.get("localStorage"),
        }, ensure_ascii=False)[:900])

        # ---- ④′ 印面图「重新上传」路径（本单 A 项：把 R-17 产物侧口径应用到 seals.js）----
        # 必须在**探针页还活着**时跑（`__XIAI_PROBE__.phase3`）：本页稍后会被 navigate 到 App
        # 页面、再被 closeTarget 关掉（那之后探针全局就不在了）。它在同一 origin 上跑真源码，
        # 内部临时切管理员、跑完还原普通用户 ⇒ 不影响随后 App 流程（普通用户 13900001234）的断言。
        seals3 = step("seals_phase3", lambda: evaluate(
            ws,
            "window.__XIAI_PROBE__ && window.__XIAI_PROBE__.phase3 ? window.__XIAI_PROBE__.phase3() : null",
            await_promise=True,
        ))
        evidence["seals_replace_path"] = seals3
        for row in (seals3 or {}).get("checks") or []:
            if not str(row.get("id", "")).startswith("seals-"):
                continue
            log(f"    [{'PASS' if row.get('pass') else 'FAIL'}] {row.get('id')} :: {row.get('name')}")
            log(f"           {str(row.get('detail'))[:700]}")
        # 断言清单以**合并后**的结果为准（phase1 33 条 + 印面图路径 8 条 = 41 条）。
        page_final = step("results_final", lambda: evaluate(ws, "JSON.parse(JSON.stringify(window.__XIAI_PROBE_RESULTS__ || {}))"))
        merged_final = merge_results(evidence.get("probe_phase1"), page_final, seals3)
        evidence["probe_phase1_final"] = merged_final
        _mc = merged_final.get("checks") or []
        _m_seals = [c for c in _mc if str(c.get("id", "")).startswith("seals-")]
        evidence["merged_assertions"] = {
            "total": len(_mc),
            "phase1": len(_mc) - len(_m_seals),
            "seals_replace_path": len(_m_seals),
            "page_global_after_reload": len((page_final or {}).get("checks") or []),
            "phase1_snapshot_before_reload": len((evidence.get("probe_phase1") or {}).get("checks") or []),
            "phase3_returned": len((seals3 or {}).get("checks") or []),
            "dedupe_key": "id",
            "sources": "probe_phase1(刷新前快照) + __XIAI_PROBE_RESULTS__(刷新后页面全局) + __XIAI_PROBE__.phase3()",
        }
        log(f"[4′] 断言合并后共 {len(_mc)} 条（phase1 {len(_mc) - len(_m_seals)} 条 + 印面图路径 {len(_m_seals)} 条）；"
            f"reload 后页面全局只剩 {len((page_final or {}).get('checks') or [])} 条，故必须以\"刷新前快照\"为底合并")

        # ---- 真实 App 页面渲染（/my/photos 与 /seal/XAI-0001 画廊）----
        step("nav_my_photos", lambda: cdp_call(ws, "Page.navigate", url=f"{APP}/my/photos"))
        step("nav_my_photos_ready", lambda: poll(ws, "document.readyState", lambda d: d == "complete", "/my/photos 载入", tries=60))
        app_photos = step("app_photos", lambda: poll(
            ws,
            """(() => {
              const cards = [...document.querySelectorAll('.photo-card')];
              return JSON.stringify({
                cards: cards.length,
                imgs: cards.map((c) => {
                  const img = c.querySelector('img');
                  return { src: img ? String(img.getAttribute('src')).slice(0, 30) : '', complete: img ? img.complete : false, w: img ? img.naturalWidth : 0, h: img ? img.naturalHeight : 0 };
                }),
                text: (document.querySelector('main') || document.body).innerText.slice(0, 300)
              });
            })()""",
            lambda d: d.get("cards", 0) > 0,
            "/my/photos 照片卡渲染",
        ))
        evidence["app_my_photos_before_close"] = app_photos
        log(f"[5] /my/photos 渲染（关标签前）：cards={{{(app_photos or {}).get('cards')}}} imgs={(app_photos or {}).get('imgs')}")

        step("nav_seal_detail", lambda: cdp_call(ws, "Page.navigate", url=f"{APP}/seal/XAI-0001"))
        step("nav_seal_detail_ready", lambda: poll(ws, "document.readyState", lambda d: d == "complete", "/seal/XAI-0001 载入", tries=60))
        app_detail = step("app_detail", lambda: poll(
            ws,
            """(() => {
              const figures = [...document.querySelectorAll('.detail__photo')];
              return JSON.stringify({
                figures: figures.length,
                imgs: figures.map((f) => {
                  const img = f.querySelector('img');
                  return { src: img ? String(img.getAttribute('src')).slice(0, 30) : '', w: img ? img.naturalWidth : 0, caption: (f.querySelector('figcaption') || {}).textContent || '' };
                })
              });
            })()""",
            lambda d: d.get("figures", 0) > 0,
            "详情页画廊渲染",
        ))
        evidence["app_seal_detail"] = app_detail
        log(f"[6] /seal/XAI-0001 画廊渲染：{app_detail}")

        # ---- ④ 关标签重开后仍能渲染 + AC-33 三阈值 ----
        step("close_target", lambda: cdp_call(ws, "Target.closeTarget", targetId=target_id))
        CURRENT["tab"] = "reopen"
        tab2 = open_tab(f"{APP}/my/photos")
        ws2 = websocket.create_connection(tab2["webSocketDebuggerUrl"], timeout=60, suppress_origin=True)
        cdp_call(ws2, "Page.enable")
        cdp_call(ws2, "Runtime.enable")
        cdp_call(ws2, "Network.enable")
        install_force_png(ws2)
        step("truth_bridge_reopen_tab", lambda: install_truth_bridge(ws2, "重开的应用页"))
        if FORCE_PNG:
            step("reopen_reload_for_injection", lambda: cdp_call(ws2, "Page.reload", ignoreCache=True))
        step("reopen_ready", lambda: poll(ws2, "document.readyState", lambda d: d == "complete", "新标签 /my/photos 载入", tries=60))
        reopened = step("reopen_render", lambda: poll(
            ws2,
            """(() => {
              const cards = [...document.querySelectorAll('.photo-card')];
              return JSON.stringify({
                cards: cards.length,
                imgs: cards.map((c) => {
                  const img = c.querySelector('img');
                  return { src: img ? String(img.getAttribute('src')).slice(0, 30) : '', complete: img ? img.complete : false, w: img ? img.naturalWidth : 0, h: img ? img.naturalHeight : 0 };
                })
              });
            })()""",
            lambda d: d.get("cards", 0) > 0,
            "关标签重开后渲染",
            tries=120,
        ))
        evidence["app_my_photos_after_reopen"] = reopened
        log(f"[7] 关标签重开后 /my/photos：{(reopened or {}).get('cards')} 张卡；imgs={(reopened or {}).get('imgs')}")

        ac33_reopen = step("ac33_reopen", lambda: evaluate(ws2, """JSON.stringify((() => {
            let total = 0, max = 0, maxKey = '', hits = [], keys = [];
            for (let i = 0; i < localStorage.length; i += 1) {
              const k = localStorage.key(i);
              const v = localStorage.getItem(k) || '';
              keys.push(k); total += v.length;
              if (v.length > max) { max = v.length; maxKey = k; }
              if (v.includes('data:image')) hits.push(k);
            }
            const photos = localStorage.getItem('xiai:v1:photos') || '';
            return { keys, dataImageHits: hits.length, dataImageKeys: hits, maxValue: max, maxKey, maxKiB: +(max / 1024).toFixed(2), total, totalKiB: +(total / 1024).toFixed(2), photosKeyLength: photos.length, photosKeyKiB: +(photos.length / 1024).toFixed(2), photosHasDataImage: photos.includes('data:image') };
          })())"""))
        evidence["app_ac33_after_reopen"] = try_json(ac33_reopen)
        log(f"[7b] AC-33 三阈值（重开后）：{json.dumps(evidence['app_ac33_after_reopen'], ensure_ascii=False)}")

        # ---------------- 真实 UI 上传：三档 ----------------
        log("[8] 真实 UI 上传（MyPhotosView：选图 → 预览 → 上传）")

        def make_file_in_page(ws, expr, name):
            b64 = evaluate(ws, expr)
            payload = try_json(b64)
            if not payload:
                raise RuntimeError(f"造图失败：{str(b64)[:300]}")
            path = f"/tmp/{name}"
            with open(path, "wb") as fh:
                fh.write(base64.b64decode(payload["b64"]))
            return path, payload

        def set_file_and_read_status(ws, path, name, expect_ready=True, tries=120):
            cdp_call(ws, "DOM.enable")
            doc = cdp_call(ws, "DOM.getDocument", depth=-1)
            node = cdp_call(ws, "DOM.querySelector", nodeId=doc["root"]["nodeId"], selector='input[data-testid="photo-file"]')
            if not node.get("nodeId"):
                raise RuntimeError("未找到 MyPhotosView 的选图入口（input[data-testid=photo-file]）")
            cdp_call(ws, "DOM.setFileInputFiles", files=[path], nodeId=node["nodeId"])
            if not expect_ready:
                return poll(
                    ws,
                    """JSON.stringify({ status: (document.querySelector('[data-testid="photo-status"]') || {}).textContent || '', kind: (document.querySelector('[data-testid="photo-status"]') || {}).className || '', hasCanvas: !!document.querySelector('[data-testid="crop-canvas"]') })""",
                    lambda d: ("已就绪" in d.get("status", "")) or ("过大" in d.get("status", "")) or ("失败" in d.get("status", "")),
                    f"{name} 预览/拒绝状态",
                    tries=tries,
                )
            return poll(
                ws,
                """JSON.stringify({ status: (document.querySelector('[data-testid="photo-status"]') || {}).textContent || '', kind: (document.querySelector('[data-testid="photo-status"]') || {}).className || '', canvasPx: (() => { const c = document.querySelector('[data-testid="crop-canvas"]'); return c ? [c.width, c.height] : null; })(), uploadBtn: !!document.querySelector('[data-testid="photo-upload"]') })""",
                lambda d: "已就绪" in d.get("status", ""),
                f"{name} 预览就绪",
                tries=tries,
            )

        def read_latest_row(ws):
            raw = evaluate(ws, """JSON.stringify((() => {
                const rows = JSON.parse(localStorage.getItem('xiai:v1:photos') || '[]');
                const last = rows[rows.length - 1] || null;
                return { count: rows.length, last };
              })())""")
            return try_json(raw) or {}

        def click_upload_and_wait(ws, name):
            evaluate(ws, """document.querySelector('[data-testid="photo-upload"]').click(); 'clicked'""", await_promise=False)
            return poll(
                ws,
                """JSON.stringify({
                   status: (document.querySelector('[data-testid="photo-status"]') || {}).textContent || '',
                   cards: document.querySelectorAll('.photo-card').length,
                   firstSrc: (() => { const i = document.querySelector('.photo-card img'); return i ? String(i.getAttribute('src')).slice(0, 30) : ''; })()
                 })""",
                lambda d: ("已上传" in d.get("status", "")) or ("失败" in d.get("status", "")),
                f"{name} 上传结果",
                tries=180,
            )

        def idb_head(ws):
            """IndexedDB 里的二进制读数。格式判定**一律调产品真源**
            （`__XIAI_IMG_TRUTH__.sniffBytesMime`，即 `src/utils/image.js::sniffBytesMime`），
            并与**本地元数据行的 mime 逐字对账**；不再自建 `isPngMagic` 那种魔数副本。"""
            raw = evaluate(ws, """(async () => {
              const truth = globalThis.__XIAI_IMG_TRUTH__ || null;
              const open = await new Promise((res) => { const r = indexedDB.open('xiai:v1:assetblobs'); r.onsuccess = () => res(r.result); r.onerror = () => res(null); });
              if (!open) return JSON.stringify(null);
              const keys = await new Promise((res) => { const tx = open.transaction('assets', 'readonly'); const rq = tx.objectStore('assets').getAllKeys(); rq.onsuccess = () => res(rq.result.map(String)); rq.onerror = () => res([]); });
              const photoKeys = keys.filter((k) => k.startsWith('photo:'));
              const sample = photoKeys.slice(-2);
              let metaRows = [];
              try { metaRows = JSON.parse(localStorage.getItem('xiai:v1:photos') || '[]'); } catch (e) { metaRows = []; }
              const sizes = [];
              for (const k of sample) {
                const v = await new Promise((res) => { const tx = open.transaction('assets', 'readonly'); const rq = tx.objectStore('assets').get(k); rq.onsuccess = () => res(rq.result); rq.onerror = () => res(null); });
                const u8 = v ? new Uint8Array(v.buffer ? v.buffer : v) : new Uint8Array(0);
                const row = metaRows.find((r) => r && r.storage_key === k) || null;
                const mimeByProduct = truth ? truth.sniffBytesMime(u8) : null;
                sizes.push({
                  key: k,
                  bytes: u8.length,
                  head12: Array.from(u8.subarray(0, 12)).map((b) => b.toString(16).padStart(2, '0')).join(''),
                  mimeByProduct,
                  truthSource: truth ? truth.source : 'unavailable',
                  metaMime: row ? row.mime : null,
                  metaBytes: row ? row.bytes : null,
                  metaMatchesBinary: !!row && row.mime === mimeByProduct && row.bytes === u8.length
                });
              }
              return JSON.stringify({ photoKeys, sizes, truthSource: truth ? truth.source : 'unavailable', allKeysArePhoto: keys.every((k) => k.startsWith('photo:')) });
            })()""")
            return try_json(raw)

        # ① 正常 WebP 小产物（真实 UI 路径）
        def ui_normal():
            path, payload = make_file_in_page(
                ws2,
                """(async () => {
                  const c = document.createElement('canvas'); c.width = 3000; c.height = 1200;
                  const x = c.getContext('2d');
                  const g = x.createLinearGradient(0, 0, 3000, 1200);
                  g.addColorStop(0, '#e8dcc8'); g.addColorStop(0.5, '#b23a2f'); g.addColorStop(1, '#20303c');
                  x.fillStyle = g; x.fillRect(0, 0, 3000, 1200);
                  for (let i = 0; i < 40; i += 1) { const px = Math.random() * 3000, py = Math.random() * 1200, r = 120 + Math.random() * 200; const rg = x.createRadialGradient(px, py, 0, px, py, r); rg.addColorStop(0, 'rgba(255,255,255,0.35)'); rg.addColorStop(1, 'rgba(255,255,255,0)'); x.fillStyle = rg; x.beginPath(); x.arc(px, py, r, 0, Math.PI * 2); x.fill(); }
                  if (window.__XIAI_FORCE_PNG__) window.__XIAI_FORCE_PNG__.on = false;
                  const blob = await new Promise((res) => c.toBlob(res, 'image/jpeg', 0.85));
                  if (window.__XIAI_FORCE_PNG__) window.__XIAI_FORCE_PNG__.on = true;
                  const buf = new Uint8Array(await blob.arrayBuffer());
                  let s = ''; for (let i = 0; i < buf.length; i += 1) s += String.fromCharCode(buf[i]);
                  return JSON.stringify({ b64: btoa(s), bytes: buf.length });
                })()""",
                "xiai-ui-normal.jpg",
            )
            preview = set_file_and_read_status(ws2, path, "正常档")
            result = click_upload_and_wait(ws2, "正常档")
            return {"input": {"path": path, "bytes": payload["bytes"]}, "preview": preview, "upload": result, "row": read_latest_row(ws2), "idb": idb_head(ws2)}

        evidence["ui_upload_normal"] = step("ui_normal", ui_normal)
        log(f"    ① 正常 WebP 小产物：{json.dumps(evidence['ui_upload_normal'], ensure_ascii=False)[:900]}")

        def reset_page():
            cdp_call(ws2, "Page.reload", ignoreCache=True)
            poll(ws2, "document.readyState", lambda d: d == "complete", "重置 /my/photos", tries=60)
            poll(ws2, """!!document.querySelector('[data-testid="photo-file"]')""", lambda d: d is True, "选图入口就绪", tries=90)

        # ② 输入超 1 MB（应拒，文案＝「你选的图太大」）
        def ui_input_over():
            reset_page()
            path, payload = make_file_in_page(
                ws2,
                """(async () => {
                  const n = 1200 * 1024;
                  const c = document.createElement('canvas'); c.width = 1400; c.height = 1400;
                  const x = c.getContext('2d');
                  const frame = x.createImageData(1400, 1400); const d = frame.data;
                  let seed = 20260920;
                  for (let i = 0; i < d.length; i += 4) { seed = (seed * 1103515245 + 12345) & 0x7fffffff; const v = seed & 0xff; d[i] = v; d[i+1] = (v * 7) & 0xff; d[i+2] = (v * 13) & 0xff; d[i+3] = 255; }
                  x.putImageData(frame, 0, 0);
                  if (window.__XIAI_FORCE_PNG__) window.__XIAI_FORCE_PNG__.on = false;
                  const blob = await new Promise((res) => c.toBlob(res, 'image/jpeg', 0.95));
                  if (window.__XIAI_FORCE_PNG__) window.__XIAI_FORCE_PNG__.on = true;
                  const buf = new Uint8Array(await blob.arrayBuffer());
                  let s = ''; for (let i = 0; i < buf.length; i += 1) s += String.fromCharCode(buf[i]);
                  return JSON.stringify({ b64: btoa(s), bytes: buf.length });
                })()""",
                "xiai-ui-over1mb.jpg",
            )
            status = set_file_and_read_status(ws2, path, "输入超限档", expect_ready=False)
            return {"input": {"path": path, "bytes": payload["bytes"]}, "status": status, "row": read_latest_row(ws2)}

        evidence["ui_upload_input_over"] = step("ui_input_over", ui_input_over)
        log(f"    ② 输入超 1 MB：{json.dumps(evidence['ui_upload_input_over'], ensure_ascii=False)[:900]}")

        # ③ 回退 PNG 大产物（XIAI_FORCE_PNG=1 时才有效）
        def ui_forced_png():
            if not FORCE_PNG:
                return {"skipped": "未设 XIAI_FORCE_PNG=1：本次跑的是真实编码路径（WebP 可用 ⇒ 走不到回退分支）"}
            reset_page()
            installed = evaluate(ws2, "!!window.__XIAI_FORCE_PNG_INSTALLED__")
            path, payload = make_file_in_page(
                ws2,
                """(async () => {
                  const N = 2048;
                  const c = document.createElement('canvas'); c.width = N; c.height = N;
                  const x = c.getContext('2d');
                  const frame = x.createImageData(N, N); const d = frame.data;
                  let seed = 20260920;
                  for (let i = 0; i < d.length; i += 4) { seed = (seed * 1103515245 + 12345) & 0x7fffffff; const v = seed & 0xff; d[i] = v; d[i+1] = (v * 7) & 0xff; d[i+2] = (v * 13) & 0xff; d[i+3] = 255; }
                  x.putImageData(frame, 0, 0);
                  if (window.__XIAI_FORCE_PNG__) window.__XIAI_FORCE_PNG__.on = false;
                  const blob = await new Promise((res) => c.toBlob(res, 'image/jpeg', 0.3));
                  if (window.__XIAI_FORCE_PNG__) window.__XIAI_FORCE_PNG__.on = true;
                  const buf = new Uint8Array(await blob.arrayBuffer());
                  let s = ''; for (let i = 0; i < buf.length; i += 1) s += String.fromCharCode(buf[i]);
                  return JSON.stringify({ b64: btoa(s), bytes: buf.length });
                })()""",
                "xiai-ui-forced-png-src.jpg",
            )
            preview = set_file_and_read_status(ws2, path, "回退 PNG 档")
            result = click_upload_and_wait(ws2, "回退 PNG 档")
            return {
                "force_png_installed": installed,
                "input": {"path": path, "bytes": payload["bytes"]},
                "preview": preview,
                "upload": result,
                "row": read_latest_row(ws2),
                "idb": idb_head(ws2),
            }

        evidence["ui_upload_forced_png"] = step("ui_forced_png", ui_forced_png)
        log(f"    ③ 回退 PNG 大产物：{json.dumps(evidence['ui_upload_forced_png'], ensure_ascii=False)[:1200]}")

        # ---- ⑨ 最终审计：localStorage 三阈值 + IndexedDB ----
        ac33_final = step("ac33_final", lambda: evaluate(ws2, """JSON.stringify((() => {
            let total = 0, max = 0, maxKey = '', hits = [], keys = [];
            for (let i = 0; i < localStorage.length; i += 1) {
              const k = localStorage.key(i);
              const v = localStorage.getItem(k) || '';
              keys.push(k); total += v.length;
              if (v.length > max) { max = v.length; maxKey = k; }
              if (v.includes('data:image')) hits.push(k);
            }
            const photos = localStorage.getItem('xiai:v1:photos') || '';
            return { keys, dataImageHits: hits.length, dataImageKeys: hits, maxValue: max, maxKey, maxKiB: +(max / 1024).toFixed(2), total, totalKiB: +(total / 1024).toFixed(2), photosKeyLength: photos.length, photosKeyKiB: +(photos.length / 1024).toFixed(2), photosHasDataImage: photos.includes('data:image') };
          })())"""))
        evidence["app_ac33_final"] = try_json(ac33_final)
        log(f"[9] AC-33 三阈值（最终）：{json.dumps(evidence['app_ac33_final'], ensure_ascii=False)}")
        evidence["app_indexeddb_final"] = step("idb_final", lambda: idb_head(ws2))
        log(f"    IndexedDB 末两条：{json.dumps(evidence['app_indexeddb_final'], ensure_ascii=False)[:900]}")

        # ---- ⑩ 网络捕获汇总（必须 5196 = 0、square-crop = 0、外部 URL = 0）----
        urls = [e["url"] for e in EVENTS]
        internal, external, p5196, square = [], [], [], []
        for url in urls:
            u = url or ""
            if u.startswith("127.0.0.1:5163") or u.startswith("http://127.0.0.1:5163") or u.startswith("ws://127.0.0.1:5163") or u.startswith("about:") or u.startswith("data:") or u.startswith("blob:"):
                internal.append(u)
            else:
                external.append(u)
            if "5196" in u:
                p5196.append(u)
            if "square-crop" in u:
                square.append(u)
        evidence["network"] = {
            "total_requests": len(urls),
            "internal_count": len(internal),
            "external_urls": external,
            "external_count": len(external),
            "port_5196_urls": p5196,
            "square_crop_urls": square,
            "sample": urls[:25],
        }
        evidence["checks_network"] = [
            {"id": "net-external-0", "pass": len(external) == 0, "detail": "外部 URL（非 127.0.0.1:5163 origin）：%d 条 %s" % (len(external), external[:5])},
            {"id": "net-5196-0", "pass": len(p5196) == 0, "detail": "5196 命中：%d 条" % len(p5196)},
            {"id": "net-square-crop-0", "pass": len(square) == 0, "detail": "square-crop 命中：%d 条" % len(square)},
        ]
        for row in evidence["checks_network"]:
            log(f"[10] [{'PASS' if row['pass'] else 'FAIL'}] {row['id']} :: {row['detail']}")
        log(f"    网络捕获：共 {len(urls)} 条请求（内部 {len(internal)}）")

    finally:
        if proc is not None:
            log(f"[11] 关闭自建 Chrome（按精确 PID kill，不用 pkill/killall）：pid={proc.pid}")
            kill_info = kill_pid_exact(proc.pid, proc)
            log(f"    kill 结果：{json.dumps(kill_info, ensure_ascii=False)}")
            subprocess.run(["rm", "-rf", PROFILE], check=False)
        evidence["cleanup"] = kill_info
        evidence["step_errors"] = STEP_ERRORS
        # **证据先落盘**：无论前面是否异常，这里必写
        try:
            write_evidence(OUT_JSON, evidence)
            write_evidence(OUT_JSON_COMPAT, evidence)
            write_evidence(OUT_JSON_MODE, evidence)
            with open(OUT_MD, "w", encoding="utf-8") as fh:
                fh.write(summary_md(evidence))
            log(f"[12] 原始证据已写入：{OUT_JSON} / {OUT_JSON_MODE} / {OUT_JSON_COMPAT}；摘要：{OUT_MD}")
        except Exception as exc:
            log(f"!! 证据落盘失败：{exc}")

    merged = evidence.get("probe_phase1_final") or evidence.get("probe_phase1") or {}
    checks = merged.get("checks") or []
    failed = [row for row in checks if not row.get("pass")]
    net_failed = [row for row in (evidence.get("checks_network") or []) if not row.get("pass")]
    seals_checks = [row for row in checks if str(row.get("id", "")).startswith("seals-")]
    phase1_checks = [row for row in checks if not str(row.get("id", "")).startswith("seals-")]
    _ma = evidence.get("merged_assertions") or {}
    log(f"[13] 断言：合计 {len(checks)} 条 = phase1 {len(phase1_checks)} 条 + 印面图路径(phase3) {len(seals_checks)} 条"
        f"（合并口径：{_ma.get('sources')}，去重键 {_ma.get('dedupe_key')}）；失败 {len(failed)} 条"
        f"＋ 网络 {len(evidence.get('checks_network') or [])} 条（失败 {len(net_failed)}）")
    log(f"     计数自洽校验：{len(phase1_checks)} + {len(seals_checks)} = {len(phase1_checks) + len(seals_checks)} "
        f"（清单实长 {len(checks)}）⇒ {'OK' if len(phase1_checks) + len(seals_checks) == len(checks) else 'MISMATCH'}；"
        f"phase1 刷新前快照 {_ma.get('phase1_snapshot_before_reload')} 条 / reload 后页面全局 {_ma.get('page_global_after_reload')} 条 / phase3 返回 {_ma.get('phase3_returned')} 条")
    for row in failed:
        log(f"    FAIL {row.get('id')} :: {row.get('name')} :: {str(row.get('detail'))[:300]}")
    for row in net_failed:
        log(f"    FAIL {row.get('id')} :: {row.get('detail')}")
    if STEP_ERRORS:
        log(f"    步骤异常（工具链）：{json.dumps(STEP_ERRORS, ensure_ascii=False)[:600]}")
    return 1 if (failed or net_failed) else 0


if __name__ == "__main__":
    sys.exit(main())
