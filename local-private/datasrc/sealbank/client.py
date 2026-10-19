#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sealbank（真微印網 sealbank.net）研究抓取器 —— 纯逻辑层，零 GUI。

纪律（硬约束）：
  * 请求间隔默认 2.2s/请求（可配，硬下限 1.5s）；
  * UA＝feicui-research/1.0 (sealbank study; contact: repo issues)；
  * 429/5xx/超时 指数退避重试（≤3 次）；
  * 全站 Big5（decode('big5', errors='replace')）；
  * 所有对外返回均为结构化 dict（带 ok / error），**不抛异常**；
  * cookies 只经 _cookie_header 进请求头，绝不写入日志 / 报错 / 产出文本。

数据产出（out/，均不入库）：
  persons.ndjson / entries.ndjson（逐行 flush）
  PROGRESS.json（断点续传：已完成 编号+页码 跳过；失败清单重跑时补抓）
  requests.log（时间戳 间隔 状态 URL —— 限速实测与去重对账用，不含 cookie）
  boundary_scan.json（编号定界扫描）

CLI（各子命令打印 JSON 摘要）：
  python3 client.py probe  <url|path>                 # 单页探针
  python3 client.py index-probe                       # 索引页形态探针（5 请求）
  python3 client.py index                             # 全量印人索引（400 姓氏槽，断点续传）
  python3 client.py index-spotcheck                   # 索引→编年链路抽样对拍（每前缀 1 人）
  python3 client.py m1-catalog                        # 真微印庫人物社團全目錄（10 页 7,482 筆）
  python3 client.py index-union                       # 索引 ∪ 目錄 并集（对拍官网 10,487）
  python3 client.py scan                              # Layer1 编号定界扫描
  python3 client.py persons --ids Q9901,Q9902,Q9910   # Layer1 编年抓取（断点续传）
  python3 client.py seals   --ids 1799-061,...        # Layer2 会员详情样本
  python3 client.py thumb   --id Q9901001             # 缩图直链可达性（1 张）
  python3 client.py report                            # 完整度/计数对拍
  python3 client.py selftest                          # 假 transport 直测（零网络）
"""

from __future__ import annotations

import argparse
import html as _html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# ── 常量 ────────────────────────────────────────────────────────────────────

BASE_URL = "http://www.sealbank.net"
USER_AGENT = "feicui-research/1.0 (sealbank study; contact: repo issues)"
DEFAULT_RATE = 2.2          # 秒/请求
HARD_MIN_RATE = 1.5         # 硬下限
DEFAULT_TIMEOUT = 40        # 秒
MAX_RETRIES = 3             # 429/5xx/超时 额外重试次数
SOURCE_LABEL = "真微印網 sealbank.net"

PERSON_URL = BASE_URL + "/m2MainFind.asp?LM=2&L1=2&L2=2&L3=0&LS=C&SRCHTXT={pid}&SK=MV"
PERSON_PAGE_URL = (
    BASE_URL + "/m2MainFind.asp?LM=2&L1=2&L2=2&L3=0&LS=C&SRCHTXT={pid}&SK=MV&VALL=&PN={page}&PNRN=0"
)
SEAL_URL = (
    BASE_URL + "/m2ImgShow.asp?STOP=M2IMGS&LM=2&L1=2&L2=1&L3=0&LS=C&SRCHTXT={sid}"
)
THUMB_URL = BASE_URL + "/SBYBImg/red80/{sid}.gif"

# 索引页（唯一可靠的全量印人入口；编号为多字母段 Q/P/R/S/O…）
INDEX_URL = BASE_URL + "/m2ViewIndex.asp?LM=2&L1=2&L2=2&L3=0&LS=C"
INDEX_SURNAME_URL = INDEX_URL + "&n1sttxt={n}"

# ── cookie 装载（绝不打印值）────────────────────────────────────────────────


def load_cookie_string(path: str) -> str:
    """读 cookies.txt，返回可直接放进 Cookie: 头的字符串。

    支持两种形态：header-style 单行（name=value; ...）与 Netscape 制表符格式。
    只返回头串；调用方负责不打印 / 不落盘。
    """
    with open(path, "rb") as f:
        raw = f.read().decode("utf-8", errors="replace")
    pairs = []
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "\t" in s:
            f7 = s.split("\t")
            if len(f7) >= 7:
                pairs.append(f"{f7[5]}={f7[6]}")
        else:
            pairs = [s]  # header-style：整行即头串
            break
    return "; ".join(pairs) if len(pairs) > 1 or not pairs else pairs[0]


# ── 默认 transport（urllib；可注入替换）────────────────────────────────────


def urllib_transport(url: str, headers: dict, timeout: float):
    """(status:int|None, body:bytes, final_url:str)；异常向上抛由 client 收敛。"""
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read(), resp.geturl()


def _sanitize(msg: str, cookie: str) -> str:
    """报错文本里抹掉 cookie 痕迹。"""
    if cookie and cookie in msg:
        msg = msg.replace(cookie, "[REDACTED]")
    return re.sub(r"[\w.+-]+@[\w.-]+", "[EMAIL]", msg)


# ── 客户端 ──────────────────────────────────────────────────────────────────


class SealBankClient:
    """限速 + 退避重试 + Big5 的 HTTP 客户端；所有方法返回结构化 dict，不抛。"""

    def __init__(
        self,
        base_url: str = BASE_URL,
        rate_limit: float = DEFAULT_RATE,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
        transport=None,
        cookie_string: str = "",
        request_log=None,
        warm_start_ts: float = 0.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.rate_limit = max(float(rate_limit), HARD_MIN_RATE)  # 硬下限 1.5s
        self.timeout = float(timeout)
        self.max_retries = int(max_retries)
        self.transport = transport or urllib_transport
        self._cookie = cookie_string or ""
        # 跨进程限速：以上一进程最后请求时刻暖启动（epoch 秒；0=无状态）
        if warm_start_ts > 0:
            self._last_ts = time.monotonic() - (time.time() - warm_start_ts)
        else:
            self._last_ts = 0.0
        self.request_count = 0
        self.request_log = request_log  # 可写文件对象 / None

    # —— 限速 ——
    def _throttle(self):
        now = time.monotonic()
        wait = self._last_ts + self.rate_limit - now
        if wait > 0:
            time.sleep(wait)
        self._last_ts = time.monotonic()

    def _log(self, status, elapsed_ms, url, start_epoch=0.0):
        self.request_count += 1
        if self.request_log:
            try:
                st = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(start_epoch)) + \
                    ('.%03d' % int((start_epoch % 1) * 1000)) if start_epoch else \
                    time.strftime('%Y-%m-%dT%H:%M:%S')
                self.request_log.write(
                    f"{st} {elapsed_ms:6d}ms {status if status is not None else '-'} {url}\n"
                )
                self.request_log.flush()
            except Exception:
                pass

    # —— 核心 GET ——
    def get(self, path: str, params: str = "", binary: bool = False) -> dict:
        """GET；返回 {ok,status,url,final_url,bytes,text|body,elapsed_ms,retries,error}。"""
        url = path if path.startswith("http") else self.base_url + ("/" + path.lstrip("/"))
        if params:
            url += ("&" if "?" in url else "?") + params
        headers = {"User-Agent": USER_AGENT}
        if self._cookie:
            headers["Cookie"] = self._cookie
        attempt, retries, err = 0, 0, None
        while True:
            self._throttle()
            start_epoch = time.time()
            t0 = time.time()
            status, body, final_url, error = None, b"", url, None
            try:
                status, body, final_url = self.transport(url, headers, self.timeout)
            except urllib.error.HTTPError as e:
                status = e.code
                try:
                    body = e.read() if e.fp else b""
                except Exception:
                    body = b""
                error = f"HTTP {e.code}"
            except Exception as e:  # 超时 / 连接错误等
                error = _sanitize(f"{type(e).__name__}: {e}", self._cookie)
            elapsed_ms = int((time.time() - t0) * 1000)
            self._log(status, elapsed_ms, url, start_epoch)
            retryable = status is None or status == 429 or (status is not None and 500 <= status < 600)
            if not retryable:
                break
            if retries >= self.max_retries:
                break
            backoff = min(2.0 * (2 ** retries), 30.0)
            time.sleep(backoff)
            retries += 1
            attempt += 1
        ok = status == 200 and not error
        out = {
            "ok": ok,
            "status": status,
            "url": url,
            "final_url": final_url,
            "bytes": len(body),
            "elapsed_ms": elapsed_ms,
            "retries": retries,
            "error": error,
        }
        if binary:
            out["body"] = body
        else:
            out["text"] = body.decode("big5", errors="replace") if body else ""
        return out

    # —— Layer 1：印人编年页 ——
    def get_person_page(self, pid: str, page: int = 1) -> dict:
        url = PERSON_URL.format(pid=pid) if page <= 1 else PERSON_PAGE_URL.format(pid=pid, page=page)
        r = self.get(url)
        if r["ok"]:
            r["parsed"] = parse_person_page(r["text"], pid=pid, page=page)
        return r

    # —— Layer 2：印章详情（会员面）——
    def get_seal_detail(self, sid: str) -> dict:
        r = self.get(SEAL_URL.format(sid=sid))
        r["seal_id"] = sid
        if r["ok"]:
            r["parsed"] = parse_seal_detail(r["text"])
        return r

    # —— 缩图直链（匿名 200）——
    def get_thumb(self, sid: str) -> dict:
        return self.get(THUMB_URL.format(sid=sid), binary=True)


# ── 解析：印人编年页 ────────────────────────────────────────────────────────

_TAG_P = re.compile(r"<p\b[^>]*>", re.I)
_TAG_P_END = re.compile(r"</p\s*>", re.I)
_TAG_BR = re.compile(r"<br\s*/?>", re.I)
_TAG_ANY = re.compile(r"<[^>]+>")


def _strip(s: str) -> str:
    s = _TAG_BR.sub("\n", s)
    s = _TAG_ANY.sub("", s)
    s = _html.unescape(s)
    s = s.replace("\u00a0", " ").replace("\r", "")
    s = "\n".join(ln.strip() for ln in s.split("\n"))
    return re.sub(r"[ \t]+", " ", s).strip()


def parse_person_page(text: str, pid: str = "", page: int = 1) -> dict:
    """编年列表页 → 结构化。无效编号返回 found=False（字段全空/零条）。"""
    out = {
        "person_id": pid,
        "page": page,
        "found": False,
        "name": "",
        "zi_hao": "",
        "years": None,
        "place": "",
        "bio_head": "",
        "total": None,
        "total_pages": None,
        "has_next": False,
        "prev_id": "",
        "prev_name": "",
        "next_id": "",
        "next_name": "",
        "entries": [],
        "parse_error": "",
    }
    try:
        m = re.search(r"姓名檢索＞\s*([^<＜\s][^<＜]*)", text)
        if not m or "共有" not in text:
            return out  # 会员墙/错误页/空号
        out["found"] = True
        out["name"] = _strip(m.group(1))
        mz = re.search(r"．\s*(\d{4})\s*∼\s*(\d{4})", text)
        if mz:
            out["years"] = [int(mz.group(1)), int(mz.group(2))]
        mzi = re.search(r"（([^）]{1,40})）</font>(?:<font[^>]*>)?．\s*\d{4}\s*∼", text)
        if mzi:
            out["zi_hao"] = mzi.group(1)
        mt = re.search(r"共有\s*(\d+)\s*則", text)
        if mt:
            out["total"] = int(mt.group(1))
        mp = re.search(r"總(?:&nbsp;|\s)*(\d+)(?:&nbsp;|\s)*頁", text)
        if mp:
            out["total_pages"] = int(mp.group(1))
        # 小页面无「總 N 頁」栏：以「下1頁」活动链接判断还有下一页（total_pages 缺省由抓取端兜底）
        if re.search(r"[Hh]ref='[^']*PN=\d+[^']*'[^>]*>(?:<[^>]+>)*\s*下1頁", text):
            out["has_next"] = True
        # 更小页面用「頁次 1 2 …」数字链：max(链接 PN) 即总页数（该栏列出全部页）
        mtop = re.search(r"頁次(?:&nbsp;|\s)*.*?</TR>", text, re.S)
        if mtop:
            pns = [int(x) for x in re.findall(r"PN=(\d+)", mtop.group(0))]
            if pns and max(pns) > 1:
                out["max_linked_page"] = max(pns)
                if out["total_pages"] is None:
                    out["total_pages"] = max(pns)
        # 上一人 / 下一人（SRCHTXT 可能是 P/S/Q 前缀）
        mn = re.search(r"↑<a HREF='m2MainFind\.asp[^']*SRCHTXT=([A-Z]\d+)&[^>]*>(?:<font[^>]*>)?([^<]+?)</font>", text, re.S)
        if mn:
            out["prev_id"], out["prev_name"] = mn.group(1), _strip(mn.group(2))
        else:
            mn = re.search(r">↑</font>.*?SRCHTXT=([A-Z]\d+)&[^>]*>\s*(?:<font[^>]*>)?([^<]+)", text, re.S)
            if mn:
                out["prev_id"], out["prev_name"] = mn.group(1), _strip(mn.group(2))
        mf = re.search(r"SRCHTXT=([A-Z]\d+)&[^>]*>\s*(?:<font[^>]*>)?([^<]+)</font>\s*</a>↓", text, re.S)
        if mf:
            out["next_id"], out["next_name"] = mf.group(1), _strip(mf.group(2))

        # 条目行：<tr bgcolor='#FFFFDD'> … 每行一个编年条目（含缩图格）
        rows = re.split(r"<tr bgcolor='#FFFFDD'>", text)[1:]
        seq = (page - 1) * 15  # 每页至多 15 条；序号跨页累加（近似，页内另有 name 锚）
        for row in rows:
            if "m2MainFind.asp" not in row and "m2ImgShow.asp" not in row:
                continue
            anchor = re.search(r"<a name='(\d+)'", row)
            if not anchor:
                continue
            seq = int(anchor.group(1)) - 1 + (page - 1) * 15 if page > 1 else int(anchor.group(1)) - 1
            e = {"seq": seq, "year": None, "year_link": "", "category": "", "text": "",
                 "entry_no": None, "book_ref": "", "note": "", "seal_ids": [], "thumb": ""}
            my = re.search(r"SRCHTXT=(\d{4})&SK=YV", row)
            if my:
                e["year"] = int(my.group(1))
                e["year_link"] = my.group(1)
            mc = re.search(r"m2ReadSamplePopup\.asp#(\d+)'\)\s*\"[^>]*>\s*([^<]+?)\s*</a>", row)
            if mc:
                e["category"] = _strip(mc.group(2))
            # 正文：<p style='line-height: 150%'>…（到 全文與/真微書屋註/格尾）
            body_m = re.search(r"<p style='line-height: 150%'>(.*?)(?:<p align='center'|</td)", row, re.S)
            if body_m:
                t = _strip(body_m.group(1)).replace("\n", "")
                if "真微書屋註：" in t:
                    t, note_inline = t.split("真微書屋註：", 1)
                    if note_inline:
                        e["note"] = note_inline.strip()
                e["text"] = t.strip()
            mno = re.search(r"／之(\d+)", e["text"] or "")
            if mno:
                e["entry_no"] = int(mno.group(1))
            # 真微書屋註
            note_m = re.search(r"真微書屋註：?(.*?)(?:<p align='center'|</td)", row, re.S)
            if note_m and not e["note"]:
                e["note"] = _strip(note_m.group(1)).replace("\n", "")
            # 书籍版对照（全文與《篆刻年歷1051-1911》書籍版YYYY年之NNN則）
            mb = re.search(r"書籍版(\d{4})年之(\d+)則", row)
            if mb:
                e["book_ref"] = f"{mb.group(1)}-{mb.group(2)}"
            # 印章链接 + 缩图
            for link, seal_id, thumb in re.findall(
                r"href='(m2ImgShow\.asp[^']*SRCHTXT=([\d]+-[\d]+)[^']*)'[^>]*>\s*<img[^>]*src='([^']+)'", row
            ):
                e["seal_ids"].append(seal_id)
                e["thumb"] = thumb
            if not e["seal_ids"]:
                m2 = re.findall(r"m2ImgShow\.asp[^']*SRCHTXT=([\d]+-[\d]+)", row)
                e["seal_ids"] = sorted(set(m2))
            out["entries"].append(e)

        # 头段补充：place / bio_head 取自首条（生）条目
        if out["entries"]:
            first = out["entries"][0]
            mp2 = re.search(r"([\u4e00-\u9fff]{2,8}（[^）]{1,12}）[\u4e00-\u9fff]{0,4})人", first["text"])
            if mp2:
                out["place"] = mp2.group(1) + "人"
            out["bio_head"] = first["text"][:160]
        # 页内条目数与 a-name 锚一致性检查
        if out["found"] and out["total_pages"] and page > out["total_pages"]:
            out["parse_error"] = f"page {page} > total_pages {out['total_pages']}"
    except Exception as e:  # 防御：解析失败不抛，带回原错误串
        out["parse_error"] = f"{type(e).__name__}: {e}"
    return out


# ── 解析：印章详情页（会员面）──────────────────────────────────────────────


def parse_seal_detail(text: str) -> dict:
    """m2ImgShow 详情页 → 结构化。餘點 0/未登录 ⇒ 会员墙，fields 全空。"""
    out = {
        "member_wall": True,
        "points_left": None,
        "fields": {
            "seal_wen": "", "transcription": "", "side_ins": "", "material": "",
            "size": "", "provenance": "", "dynasty": "", "author": "",
        },
        "image_urls": [],
        "hint": "",
    }
    if "會員餘點" in text:
        mp = re.search(r"會員餘點(\d+)", text)
        if mp:
            out["points_left"] = int(mp.group(1))
    if "請先輸入會員帳號及密碼" in text:
        out["hint"] = "anonymous_login_wall"
        return out
    if "目前只能作有限度瀏覽" in text:
        out["hint"] = "limited_browse_points_0"
    # 有限度瀏覽实测：页面仅剩站点框架（无印章字段/图 URL）；以下解析为
    # 「若未来有點數」的字段兜底 —— 出现即抓，不出现即为空。
    if "印文" in text or "SBYBImg" in text:
        out["member_wall"] = False
        plain = _strip(text)
        for key, pat in [
            ("seal_wen", r"印文[：:]\s*([^\n]+)"),
            ("transcription", r"釋文[：:]\s*([^\n]+)"),
            ("side_ins", r"邊款[：:]\s*([^\n]+)"),
            ("material", r"石料[：:]\s*([^\n]+)"),
            ("size", r"尺寸[：:]\s*([^\n]+)"),
            ("provenance", r"出處[：:]\s*([^\n]+)"),
            ("dynasty", r"朝代[：:]\s*([^\n]+)"),
            ("author", r"作者[：:]\s*([^\n]+)"),
        ]:
            m = re.search(pat, plain)
            if m:
                out["fields"][key] = m.group(1).strip()
        out["image_urls"] = sorted(set(re.findall(r"(?:src|href)='(SBYBImg/[^']+\.(?:gif|jpg|png))'", text)))
        out["image_urls"] = [u for u in out["image_urls"] if not u.startswith("SBYBImg/red80")]
    return out


# ── GIF 尺寸（缩图验证用）──────────────────────────────────────────────────


def gif_dimensions(body: bytes):
    if len(body) < 10 or body[:3] != b"GIF":
        return None
    w = body[6] | (body[7] << 8)
    h = body[8] | (body[9] << 8)
    return [w, h]


# ── 编号定界扫描（Layer 1 前置）────────────────────────────────────────────

COARSE_IDS = ["Q8000", "Q8500", "Q9000", "Q9500", "Q9999", "Q10000", "Q11000", "Q12000", "Q15000"]
FINE_SEEDS = ["Q9890", "Q9895", "Q9898", "Q9899", "Q9900", "Q9901", "Q9902", "Q9903",
              "Q9904", "Q9905", "Q9906", "Q9907", "Q9908", "Q9909", "Q9910", "Q9911",
              "Q9912", "Q9915", "Q9920", "Q9950"]


def scan_boundaries(client: SealBankClient, coarse=None, fine_seeds=None) -> dict:
    """从 Q9901 向两侧粗探＋细化；返回 {probes:[{id,status,found,name,total,bytes}],...}。

    判定：parse.found=True ⇒ 命中（有效印人）；False/非 200 ⇒ 空。
    细化：对相邻「一命中一未命中」的粗探区间做对分（步长 500→250→…→50，深度≤4）。
    """
    coarse = list(coarse) if coarse else COARSE_IDS
    fine_seeds = list(fine_seeds) if fine_seeds else FINE_SEEDS
    probes = {}

    def probe(pid):
        if pid in probes:
            return probes[pid]
        r = client.get_person_page(pid)
        p = r.get("parsed") or {}
        rec = {
            "id": pid,
            "status": r["status"],
            "ok": r["ok"],
            "found": bool(p.get("found")),
            "name": p.get("name", ""),
            "total": p.get("total"),
            "total_pages": p.get("total_pages"),
            "bytes": r["bytes"],
            "error": r["error"],
        }
        probes[pid] = rec
        return rec

    for pid in fine_seeds:
        probe(pid)
    for pid in coarse:
        probe(pid)

    # 对分细化：在每对相邻（按数值序）一命中一空的探针之间
    def num(p):
        return int(p[1:])

    ids = sorted(probes, key=num)
    queue = []
    for a, b in zip(ids, ids[1:]):
        if probes[a]["found"] != probes[b]["found"] and num(b) - num(a) > 50:
            queue.append((a, b, 0))
    while queue:
        a, b, depth = queue.pop(0)
        if depth >= 4:
            continue
        mid = f"Q{(num(a) + num(b)) // 2}"
        if mid in probes:
            continue
        r = probe(mid)
        if probes[a]["found"] != r["found"] and num(mid) - num(a) > 50:
            queue.append((a, mid, depth + 1))
        if r["found"] != probes[b]["found"] and num(b) - num(mid) > 50:
            queue.append((mid, b, depth + 1))

    hits = sorted([p for p in probes.values() if p["found"]], key=lambda p: num(p["id"]))
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": SOURCE_LABEL,
        "probes": [probes[k] for k in sorted(probes, key=num)],
        "probe_count": len(probes),
        "hit_count": len(hits),
        "hit_ids": [p["id"] for p in hits],
        "note": "编号稠密带洞；found=编年列表页含「共有N則」。有效区间=命中覆盖的数值范围（内部仍有洞）。",
    }
    if hits:
        report["effective_low"] = hits[0]["id"]
        report["effective_high"] = hits[-1]["id"]
    return report


# ── 索引页：全量印人普查（依人物瀏覽＞姓名檢索）─────────────────────────────
#
# 形态（2026-10-19 实测）：索引按**姓氏首字的繁體筆劃**分组（2–24 劃），第一层列出
# 400 个姓氏首字链接（`&n1sttxt=1..400`，N 互不重复）；每个 N 的页是**单人页、无分页**，
# 页头「共 N 筆資料」，每人一格：`姓名` + `．字號．生卒．N則`，链接带印人编号
# （多字母段 Q/P/R/S/O…）。⇒ 全量印人 = 遍历这 400 个 N。

_STROKE_HDR = re.compile(r"<font[^>]*>(\d+)\s*劃-姓氏首字</font>")
_CHAR_LINK = re.compile(r"n1sttxt=(\d+)#CURRENTFN'[^>]*>\s*<font[^>]*>([^<]+)</font>")
_REC_LINK = re.compile(
    r"<a HREF='m2MainFind\.asp\?[^']*SRCHTXT=([A-Z]\d+)&SK=MV'[^>]*>(.*?)</a>"
    r"(.*?)(?=</TD>|</TR>)",
    re.S,
)
_HEADER_COUNT = re.compile(r"共(?:&nbsp;|\s)*(\d+)(?:&nbsp;|\s)*筆資料")


def parse_index_shelf(text: str) -> dict:
    """索引首页 → {chars:[{n,char,stroke}], unique_n, n_links, strokes}。"""
    chars = []
    stroke = None
    # 按出现顺序同时扫描「N 劃-姓氏首字」与字符链接，记录每字所属笔画
    events = []
    for m in _STROKE_HDR.finditer(text):
        events.append((m.start(), "stroke", m.group(1)))
    for m in _CHAR_LINK.finditer(text):
        events.append((m.start(), "char", (m.group(1), m.group(2).strip())))
    events.sort()
    for _, kind, val in events:
        if kind == "stroke":
            stroke = int(val)
        else:
            chars.append({"n": int(val[0]), "char": val[1], "stroke": stroke})
    by_n = {}
    for c in chars:
        by_n.setdefault(c["n"], []).append(c["char"])
    return {
        "chars": chars,
        "n_links": len(chars),
        "unique_n": len(by_n),
        "stroke_groups": sorted({c["stroke"] for c in chars if c["stroke"]}),
        # 同一 n1sttxt 槽挂多个字（异体/同槽）：审计用，抓取时按 n 去重
        "multi_char_slots": [
            {"n": n, "chars": cs} for n, cs in sorted(by_n.items()) if len(cs) > 1
        ],
    }


def _parse_entry_meta(detail_html: str) -> dict:
    """`．字號．1879 ∼ 1949．20則` → 结构化（缺项留空/None）。"""
    plain = _strip(detail_html).replace("\n", "")
    out = {"zi_hao": "", "years_raw": "", "year_start": None, "year_end": None,
           "entry_count": None, "entry_count_raw": ""}
    m = re.search(r"(\d+)\s*則", plain)
    if m:
        out["entry_count"] = int(m.group(1))
        out["entry_count_raw"] = m.group(0)
    segs = [s for s in re.split(r"[．·]", plain) if s.strip()]
    for s in segs:
        s = s.strip()
        if "則" in s:
            continue
        if re.search(r"\d{3,4}", s) or ("？" in s and ("∼" in s or "〜" in s or "~" in s)):
            if not out["years_raw"]:
                out["years_raw"] = s
        elif not out["zi_hao"]:
            out["zi_hao"] = s
    if out["years_raw"]:
        ys = re.findall(r"\d{3,4}", out["years_raw"])
        if ys:
            out["year_start"] = int(ys[0])
        if len(ys) > 1:
            out["year_end"] = int(ys[1])
    return out


def parse_surname_page(text: str, n: int = 0) -> dict:
    """单个姓氏首字页 → {n, char, declared, records, ...}。"""
    out = {"n": n, "char": "", "declared": None, "records": [],
           "current_char": "", "parse_error": ""}
    try:
        mh = _HEADER_COUNT.search(text)
        if mh:
            out["declared"] = int(mh.group(1))
        mc = re.search(r"<a Name='CURRENTFN'>(.*?)</a>", text, re.S)
        if mc:
            out["char"] = _strip(mc.group(1))
        for pid, anchor, tail in _REC_LINK.findall(text):
            name = _strip(anchor)
            meta = _parse_entry_meta(tail)
            rec = {
                "id": pid,
                "prefix": pid[0],
                "name": name,
                "zi_hao": meta["zi_hao"],
                "years_raw": meta["years_raw"],
                "year_start": meta["year_start"],
                "year_end": meta["year_end"],
                "entry_count": meta["entry_count"],
                "surname_slot": n,
                "surname_char": out["char"],
                "href": "m2MainFind.asp?LM=2&L1=2&L2=2&L3=0&LS=C&SRCHTXT=%s&SK=MV" % pid,
            }
            out["records"].append(rec)
        if out["declared"] is not None and out["declared"] != len(out["records"]):
            out["parse_error"] = f"declared {out['declared']} != parsed {len(out['records'])}"
    except Exception as e:
        out["parse_error"] = f"{type(e).__name__}: {e}"
    return out


def probe_index(client: SealBankClient, out_dir: str, sample_n=(1, 34, 208, 389)) -> dict:
    """小样本探索引形态（首页 + 若干姓氏槽），落 out/index_probe.json。"""
    os.makedirs(out_dir, exist_ok=True)
    r = client.get(INDEX_URL)
    shelf = parse_index_shelf(r["text"]) if r["ok"] else {"chars": [], "n_links": 0, "unique_n": 0}
    pages = []
    for n in sample_n:
        rp = client.get(INDEX_SURNAME_URL.format(n=n))
        p = parse_surname_page(rp["text"], n=n) if rp["ok"] else {"n": n, "records": [], "declared": None}
        per_char = {}
        for rec in p.get("records", []):
            per_char[rec["prefix"]] = per_char.get(rec["prefix"], 0) + 1
        pages.append({
            "n": n,
            "status": rp["status"],
            "bytes": rp["bytes"],
            "char": p.get("char"),
            "declared": p.get("declared"),
            "parsed": len(p.get("records", [])),
            "prefix_dist": per_char,
            "sample": p.get("records", [])[:3],
            "parse_error": p.get("parse_error", ""),
        })
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": SOURCE_LABEL,
        "index_url": INDEX_URL,
        "surname_url_template": INDEX_SURNAME_URL,
        "shelf_status": r["status"],
        "shelf_bytes": r["bytes"],
        "shelf_char_links": shelf.get("n_links"),
        "shelf_unique_n": shelf.get("unique_n"),
        "shelf_stroke_groups": shelf.get("stroke_groups"),
        "shelf_duplicate_n": shelf.get("multi_char_slots"),
        "organization": "姓氏首字（繁體筆劃分组）→ 该姓氏下印人清单（单人页，表格式，2 列/行）",
        "pagination": "姓氏首字页无分页（无 PN= 链接）；首页为全字表，无分页",
        "per_record_fields": ["id(SRCHTXT)", "prefix", "name", "zi_hao", "years", "entry_count(則)"],
        "pages": pages,
    }
    path = os.path.join(out_dir, "index_probe.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    out["path"] = path
    return out


def fetch_index(client: SealBankClient, out_dir: str, limit: int = 0, refetch: bool = False) -> dict:
    """遍历 400 个姓氏槽 → out/index_pages/<n>.json → out/index.ndjson + index_summary.json。

    断点续传：已存在的 index_pages/<n>.json 直接复用（`--refetch` 强制重抓）；
    NDJSON 每次从页缓存**重建**（不 append，避免重跑去重问题）。
    """
    pages_dir = os.path.join(out_dir, "index_pages")
    os.makedirs(pages_dir, exist_ok=True)
    # 1) 索引首页（字表）—— 缓存
    shelf_path = os.path.join(out_dir, "index_shelf.json")
    shelf = None
    if os.path.exists(shelf_path) and not refetch:
        try:
            shelf = json.load(open(shelf_path, encoding="utf-8"))
        except Exception:
            shelf = None
    if shelf is None:
        r = client.get(INDEX_URL)
        if not r["ok"]:
            return {"ok": False, "error": f"shelf fetch failed: {r['status']} {r['error']}"}
        shelf = parse_index_shelf(r["text"])
        shelf["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with open(shelf_path, "w", encoding="utf-8") as f:
            json.dump(shelf, f, ensure_ascii=False, indent=1)

    ns = sorted({c["n"] for c in shelf["chars"]})
    stat = {"shelf_chars": len(shelf["chars"]), "shelf_unique_n": len(ns),
            "pages_fetched": 0, "pages_cached": 0, "pages_failed": [], "requested": 0}
    for n in ns:
        if limit and stat["requested"] >= limit:
            break
        p = os.path.join(pages_dir, f"{n}.json")
        if os.path.exists(p) and not refetch:
            stat["pages_cached"] += 1
            continue
        r = client.get(INDEX_SURNAME_URL.format(n=n))
        if not r["ok"]:
            stat["pages_failed"].append({"n": n, "status": r["status"], "error": r["error"]})
            stat["requested"] += 1
            continue
        page = parse_surname_page(r["text"], n=n)
        page["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        page["bytes"] = r["bytes"]
        with open(p, "w", encoding="utf-8") as f:
            json.dump(page, f, ensure_ascii=False, indent=1)
        stat["pages_fetched"] += 1
        stat["requested"] += 1

    # 2) 重建 NDJSON + 汇总
    summary = assemble_index(out_dir)
    summary.update({k: stat[k] for k in ("shelf_chars", "shelf_unique_n", "pages_fetched",
                                         "pages_cached", "pages_failed")})
    return summary


def spotcheck_index(client: SealBankClient, out_dir: str, count: int = 10) -> dict:
    """抽样核验索引 → 编年链路：取 count 个**不同前缀**的印人，各抓编年页 1，
    对拍「姓名 / 則数」是否与索引一致（只抓第 1 页，不跑全量）。"""
    nd_path = os.path.join(out_dir, "index.ndjson")
    if not os.path.exists(nd_path):
        return {"ok": False, "error": "index.ndjson missing; run `index` first"}
    records = [json.loads(l) for l in open(nd_path, encoding="utf-8") if l.strip()]
    by_prefix = {}
    for rec in records:
        by_prefix.setdefault(rec["prefix"], []).append(rec)
    picks = []
    # 每个前缀取「則数」中位偏上的一人（避开 1 則与超大户，兼顾代表性）
    for pre in sorted(by_prefix):
        group = sorted([r for r in by_prefix[pre] if r.get("entry_count")],
                       key=lambda r: r["entry_count"])
        if group:
            picks.append(group[len(group) * 2 // 3])
    picks = picks[:count] if count else picks
    results = []
    for rec in picks:
        r = client.get_person_page(rec["id"], 1)
        p = r.get("parsed") or {}
        name_ok = (p.get("name") or "").strip() == rec["name"].strip()
        count_ok = rec.get("entry_count") is None or p.get("total") == rec["entry_count"]
        results.append({
            "id": rec["id"],
            "prefix": rec["prefix"],
            "index_name": rec["name"],
            "index_entry_count": rec.get("entry_count"),
            "status": r["status"],
            "found": bool(p.get("found")),
            "page1_name": p.get("name"),
            "page1_total": p.get("total"),
            "page1_total_pages": p.get("total_pages"),
            "name_match": name_ok,
            "count_match": count_ok,
            "ok": bool(r["ok"] and p.get("found") and name_ok and count_ok),
        })
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": SOURCE_LABEL,
        "method": "每前缀取 1 人，抓编年第 1 页，对比 姓名 + 頁面「共有N則」",
        "sample_size": len(results),
        "distinct_prefixes": sorted({r["prefix"] for r in results}),
        "all_pass": all(x["ok"] for x in results) if results else False,
        "results": results,
    }
    path = os.path.join(out_dir, "index_spotcheck.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    out["path"] = path
    return out


OFFICIAL_TARGETS = {"persons": 10487, "entries": 133883, "seals": 81281}


_GLYPH_NOTE = re.compile(r"◎\{([^}]*)\}")


def _enrich(rec: dict) -> dict:
    """站点自造字记法 `◎{左禾右犀}` → 保留原 name，另给 name_plain + glyph_notes。"""
    notes = _GLYPH_NOTE.findall(rec["name"])
    rec["name_plain"] = _strip(_GLYPH_NOTE.sub("", rec["name"]))
    rec["glyph_notes"] = notes
    rec["has_glyph_placeholder"] = bool(notes) or "◎" in rec["name"]
    return rec


def assemble_index(out_dir: str) -> dict:
    """从 index_pages/*.json 重建 index.ndjson（按编号去重）+ index_summary.json。"""
    pages_dir = os.path.join(out_dir, "index_pages")
    files = sorted(
        [f for f in os.listdir(pages_dir) if f.endswith(".json")],
        key=lambda x: int(x[:-5]) if x[:-5].isdigit() else 0,
    ) if os.path.isdir(pages_dir) else []
    seen, records, dups = {}, [], []
    page_audit = []
    declared_sum = 0
    for fn in files:
        page = json.load(open(os.path.join(pages_dir, fn), encoding="utf-8"))
        if page.get("declared") is not None:
            declared_sum += page["declared"]
        parsed = len(page.get("records", []))
        if page.get("parse_error") or (page.get("declared") not in (None, parsed)):
            page_audit.append({"file": fn, "n": page.get("n"), "char": page.get("char"),
                               "declared": page.get("declared"), "parsed": parsed,
                               "error": page.get("parse_error", "")})
        for rec in page.get("records", []):
            pid = rec["id"]
            if pid in seen:
                dups.append({"id": pid, "name": rec["name"],
                             "slots": [seen[pid]["surname_slot"], rec["surname_slot"]]})
                continue
            seen[pid] = _enrich(rec)
            records.append(seen[pid])

    nd_path = os.path.join(out_dir, "index.ndjson")
    with open(nd_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()

    prefix_dist = {}
    for rec in records:
        prefix_dist[rec["prefix"]] = prefix_dist.get(rec["prefix"], 0) + 1
    with_count = [r for r in records if r.get("entry_count") is not None]
    entry_sum = sum(r["entry_count"] for r in with_count)
    zero_count = [r for r in with_count if r["entry_count"] == 0]

    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": SOURCE_LABEL,
        "index_url": INDEX_URL,
        "surname_pages_read": len(files),
        "declared_sum_from_pages": declared_sum,
        "unique_persons": len(records),
        "raw_records": len(records) + len(dups),
        "duplicate_ids": dups,
        "prefix_dist": dict(sorted(prefix_dist.items())),
        "with_entry_count": len(with_count),
        "without_entry_count": len(records) - len(with_count),
        "with_entry_count_pct": round(100.0 * len(with_count) / len(records), 2) if records else 0.0,
        "entry_count_sum": entry_sum,
        "zero_entry_persons": len(zero_count),
        "glyph_placeholder_persons": sum(1 for r in records if r.get("has_glyph_placeholder")),
        "page_count_mismatch": page_audit,
        "official_targets": OFFICIAL_TARGETS,
        "person_delta_vs_official": len(records) - OFFICIAL_TARGETS["persons"],
        "entries_delta_vs_official": entry_sum - OFFICIAL_TARGETS["entries"],
        "paths": {"ndjson": nd_path, "summary": os.path.join(out_dir, "index_summary.json")},
    }
    with open(os.path.join(out_dir, "index_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    return summary


# ── 真微印庫目錄（m1 人物社團全目錄）：印人档的另一半 ──────────────────────
#
# `m1IndexAll.asp?LM=1&L1=5&L2=1&L3=0&LS=D` 首頁自述「人物社團全目錄共7482筆」，
# 每頁 749 筆、10 页；条目链接 `m1MainFind.asp?...SRCHTXT=<ID>&SK=MV`，
# **与篆刻年歷共用同一印人编号空间**（G/I/J/K/L/M/N/O/P/Q/R/S…）。
# 但此目录**不带「則数」**（只有 生卒/字號/籍貫 简介）⇒ entry_count 为 None。

M1_CATALOG_URL = BASE_URL + "/m1IndexAll.asp?LM=1&L1=5&L2=1&L3={page}&LS=D&FILTER=&PN={page}"
M1_CATALOG_TOTAL = re.compile(r"人物社團全目錄共(?:&nbsp;|\s)*([\d,]+)(?:&nbsp;|\s)*筆")
_M1_REC = re.compile(
    r"<a Href='m1MainFind\.asp\?[^']*SRCHTXT=([A-Z]\d+)&SK=MV'[^>]*>(.*?)</a>(.*?)</font>",
    re.S | re.I,
)


def parse_m1_catalog_page(text: str, page: int = 1) -> dict:
    out = {"page": page, "declared_total": None, "records": [], "per_page": None, "parse_error": ""}
    mt = M1_CATALOG_TOTAL.search(text)
    if mt:
        out["declared_total"] = int(mt.group(1).replace(",", ""))
    mp = re.search(r"本頁計呈現(?:&nbsp;|\s)*([\d,]+)(?:&nbsp;|\s)*筆", text)
    if mp:
        out["per_page"] = int(mp.group(1).replace(",", ""))
    for pid, anchor, bio in _M1_REC.findall(text):
        plain = _strip(bio).replace("\n", "")
        plain = plain.lstrip("，, ").strip()
        yrs = re.findall(r"(\d{3,4})\s*[∼~〜﹣-]\s*(\d{3,4}|？)", plain)
        out["records"].append({
            "id": pid,
            "prefix": pid[0],
            "name": _strip(anchor),
            "bio": plain,
            "year_start": int(yrs[0][0]) if yrs else None,
            "year_end": int(yrs[0][1]) if yrs and yrs[0][1].isdigit() else None,
            "entry_count": None,  # 目录不带則数
            "source_section": "m1_catalog",
            "href": "m1MainFind.asp?LM=1&L1=1&L2=3&L3=0&LS=C&SRCHTXT=%s&SK=MV" % pid,
            "page": page,
        })
    if out["per_page"] and out["per_page"] != len(out["records"]):
        out["parse_error"] = f"per_page {out['per_page']} != parsed {len(out['records'])}"
    return out


def fetch_m1_catalog(client: SealBankClient, out_dir: str, pages: int = 10, refetch: bool = False) -> dict:
    """m1 人物社團目錄 → out/m1_catalog.ndjson（断点续传：out/m1_catalog_pages/<p>.json）。"""
    pdir = os.path.join(out_dir, "m1_catalog_pages")
    os.makedirs(pdir, exist_ok=True)
    stat = {"pages_fetched": 0, "pages_cached": 0, "failed": [], "declared_total": None}
    for p in range(1, pages + 1):
        fp = os.path.join(pdir, f"{p}.json")
        if os.path.exists(fp) and not refetch:
            stat["pages_cached"] += 1
            continue
        r = client.get(M1_CATALOG_URL.format(page=p))
        if not r["ok"]:
            stat["failed"].append({"page": p, "status": r["status"], "error": r["error"]})
            continue
        page = parse_m1_catalog_page(r["text"], page=p)
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(page, f, ensure_ascii=False, indent=1)
        stat["pages_fetched"] += 1
    recs, seen = [], set()
    files = sorted([f for f in os.listdir(pdir) if f.endswith(".json")],
                   key=lambda x: int(x[:-5]))
    for fn in files:
        page = json.load(open(os.path.join(pdir, fn), encoding="utf-8"))
        if page.get("declared_total"):
            stat["declared_total"] = page["declared_total"]
        for rec in page["records"]:
            if rec["id"] in seen:
                continue
            seen.add(rec["id"])
            rec["name_plain"] = _strip(_GLYPH_NOTE.sub("", rec["name"]))
            recs.append(rec)
    with open(os.path.join(out_dir, "m1_catalog.ndjson"), "w", encoding="utf-8") as f:
        for rec in recs:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
    stat["unique_persons"] = len(recs)
    stat["pages_read"] = len(files)
    stat["page_audit"] = [
        {"file": fn, "parsed": len(json.load(open(os.path.join(pdir, fn), encoding="utf-8"))["records"])}
        for fn in files
    ]
    return stat


def union_summary(out_dir: str) -> dict:
    """篆刻年歷索引 ∪ m1 人物目錄 → 编号并集，并与官网 10,487 对拍。"""
    def load(name):
        p = os.path.join(out_dir, name)
        if not os.path.exists(p):
            return []
        return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]

    m2 = load("index.ndjson")
    m1 = load("m1_catalog.ndjson")
    m2_ids, m1_ids = {r["id"] for r in m2}, {r["id"] for r in m1}
    union = m2_ids | m1_ids
    prefix = {}
    for pid in union:
        prefix[pid[0]] = prefix.get(pid[0], 0) + 1
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": SOURCE_LABEL,
        "m2_chronology_persons": len(m2_ids),
        "m1_catalog_persons": len(m1_ids),
        "overlap": len(m2_ids & m1_ids),
        "m2_only": len(m2_ids - m1_ids),
        "m1_only": len(m1_ids - m2_ids),
        "union_persons": len(union),
        "prefix_dist_union": dict(sorted(prefix.items())),
        "official_target": OFFICIAL_TARGETS["persons"],
        "delta_vs_official": len(union) - OFFICIAL_TARGETS["persons"],
        "note": ("m2=篆刻年歷人名索引（带則数）；m1=真微印庫人物社團全目錄（不带則数）。"
                 "两者共用同一编号空间，并集即公开可枚举的印人全集；"
                 "官网 10,487 为「印人档」口径（含未进目录的档案人物），差额即未公开枚举部分。"),
    }
    with open(os.path.join(out_dir, "index_union_summary.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out


# ── 断点续传抓取（Layer 1 主任务）──────────────────────────────────────────


class Progress:
    """out/PROGRESS.json：persons{pid:{total_pages,pages_done[],entries,status,error}}。

    重跑跳过已完成 (pid,page)；失败页重跑时补抓。
    """

    def __init__(self, path: str):
        self.path = path
        self.data = {"persons": {}, "updated_at": "", "source": SOURCE_LABEL}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                self.data.setdefault("persons", {})
            except Exception:
                pass  # 损坏则从头（NDJSON 为 append-only，可能重复——见 README 重跑须知）

    def get(self, pid: str) -> dict:
        return self.data["persons"].setdefault(
            pid, {"total_pages": None, "pages_done": [], "entries": 0, "status": "new", "error": ""}
        )

    def save(self):
        self.data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)


def _ndjson_writer(path: str):
    """append 逐行 flush。"""
    def write(obj: dict):
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            f.flush()
    return write


def fetch_persons(client: SealBankClient, ids, out_dir: str, max_pages: int = 0) -> dict:
    """抓取印人编年全部分页 → persons/entries NDJSON + PROGRESS。

    断点续传：PROGRESS 里 pages_done 已含的页跳过；max_pages>0 限页（中断模拟/试跑）。
    """
    os.makedirs(out_dir, exist_ok=True)
    prog = Progress(os.path.join(out_dir, "PROGRESS.json"))
    write_person = _ndjson_writer(os.path.join(out_dir, "persons.ndjson"))
    write_entry = _ndjson_writer(os.path.join(out_dir, "entries.ndjson"))
    summary = {"requested": list(ids), "fetched_pages": 0, "skipped_pages": 0,
               "entries": 0, "failed": [], "persons_done": []}

    for pid in ids:
        pid = pid.strip()
        if not pid:
            continue
        rec = prog.get(pid)
        total_pages = rec.get("total_pages") or 0
        pages_done = set(rec.get("pages_done") or [])
        limit = max_pages if max_pages > 0 else 10 ** 6

        # 先补页1拿 total_pages（若尚未完成）
        if 1 not in pages_done:
            r = client.get_person_page(pid, 1)
            if not r["ok"] or not (r.get("parsed") or {}).get("found"):
                rec["status"] = "failed"
                rec["error"] = r["error"] or "not_found_or_wall"
                summary["failed"].append({"id": pid, "page": 1, "error": rec["error"]})
                prog.save()
                continue
            p = r["parsed"]
            total_pages = p["total_pages"] or (2 if p.get("has_next") else 1)
            rec["total_pages"] = total_pages
            rec["name"] = p["name"]
            _emit_page(write_person, write_entry, prog, pid, p)
            pages_done.add(1)
            rec["pages_done"] = sorted(pages_done)
            rec["entries"] = rec.get("entries", 0) + len(p["entries"])
            rec["status"] = "partial" if total_pages > 1 else "done"
            summary["fetched_pages"] += 1
            summary["entries"] += len(p["entries"])
            prog.save()
        else:
            summary["skipped_pages"] += 1

        for page in range(2, min(total_pages, limit) + 1):
            if page in pages_done:
                summary["skipped_pages"] += 1
                continue
            r = client.get_person_page(pid, page)
            p = r.get("parsed") or {}
            if r["ok"] and p.get("found"):
                if not p["entries"] and not p.get("has_next"):
                    # 越过末页（total_pages 兜底偏大时）：以空页收尾，不算失败
                    rec["status"] = "done" if len(pages_done) >= 1 else "partial"
                    rec["total_pages"] = page - 1
                    prog.save()
                    break
                _emit_page(write_person, write_entry, prog, pid, p)
                pages_done.add(page)
                rec["pages_done"] = sorted(pages_done)
                rec["entries"] = rec.get("entries", 0) + len(p["entries"])
                rec["status"] = "done" if len(pages_done) >= total_pages else "partial"
                summary["fetched_pages"] += 1
                summary["entries"] += len(p["entries"])
                prog.save()
            else:
                rec["status"] = "partial"
                rec["error"] = r["error"] or "parse_or_fetch_failed"
                summary["failed"].append({"id": pid, "page": page, "error": rec["error"]})
                prog.save()

        if rec.get("status") != "failed":
            if rec.get("status") == "done":
                summary["persons_done"].append(pid)
        # person 行在页1时已写（_emit_page 里 persons 逐人一行，仅页1写）
    prog.save()
    return summary


def _emit_page(write_person, write_entry, prog, pid: str, parsed: dict):
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    if parsed.get("page", 1) == 1:
        write_person({
            "id": pid,
            "name": parsed.get("name", ""),
            "zi_hao": parsed.get("zi_hao", ""),
            "years": parsed.get("years"),
            "place": parsed.get("place", ""),
            "bio_head": parsed.get("bio_head", ""),
            "total": parsed.get("total"),
            "total_pages": parsed.get("total_pages"),
            "prev_id": parsed.get("prev_id", ""),
            "next_id": parsed.get("next_id", ""),
            "source": SOURCE_LABEL,
            "scraped_at": ts,
        })
    for e in parsed.get("entries", []):
        e2 = dict(e)
        e2["person_id"] = pid
        e2["source"] = SOURCE_LABEL
        e2["scraped_at"] = ts
        write_entry(e2)


# ── Layer 2 样本 + 缩图验证 ────────────────────────────────────────────────


def sample_seals(client: SealBankClient, ids, out_dir: str, download_thumb_of: str = "") -> dict:
    os.makedirs(os.path.join(out_dir, "sample"), exist_ok=True)
    results = []
    for sid in ids:
        r = client.get_seal_detail(sid.strip())
        rec = {
            "seal_id": sid,
            "status": r["status"],
            "ok": r["ok"],
            "bytes": r["bytes"],
            "error": r["error"],
            "parsed": r.get("parsed"),
        }
        results.append(rec)
        with open(os.path.join(out_dir, "sample", f"seal_{sid}.json"), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=1)
    out = {"seals": results, "thumb": None}
    if download_thumb_of:
        tr = client.get_thumb(download_thumb_of)
        dims = gif_dimensions(tr.get("body") or b"")
        dest = os.path.join(out_dir, "sample", f"{download_thumb_of}.gif")
        saved = False
        if tr["ok"] and tr.get("body"):
            with open(dest, "wb") as f:
                f.write(tr["body"])
            saved = True
        out["thumb"] = {
            "id": download_thumb_of, "status": tr["status"], "ok": tr["ok"],
            "bytes": tr["bytes"], "gif_dimensions": dims, "saved": saved, "path": dest if saved else "",
            "error": tr["error"],
        }
    return out


# ── 报告：完整度 + 计数对拍 ────────────────────────────────────────────────


def report(out_dir: str) -> dict:
    persons_path = os.path.join(out_dir, "persons.ndjson")
    entries_path = os.path.join(out_dir, "entries.ndjson")
    persons = [json.loads(l) for l in open(persons_path, encoding="utf-8") if l.strip()] \
        if os.path.exists(persons_path) else []
    entries = [json.loads(l) for l in open(entries_path, encoding="utf-8") if l.strip()] \
        if os.path.exists(entries_path) else []
    prog = json.load(open(os.path.join(out_dir, "PROGRESS.json"), encoding="utf-8")) \
        if os.path.exists(os.path.join(out_dir, "PROGRESS.json")) else {"persons": {}}

    per_person = {}
    for e in entries:
        d = per_person.setdefault(e["person_id"], {"entries": 0, "with_year": 0, "with_text": 0,
                                                   "with_seal": 0, "with_note": 0, "with_entry_no": 0})
        d["entries"] += 1
        d["with_year"] += 1 if e.get("year") else 0
        d["with_text"] += 1 if e.get("text") else 0
        d["with_seal"] += 1 if e.get("seal_ids") else 0
        d["with_note"] += 1 if e.get("note") else 0
        d["with_entry_no"] += 1 if e.get("entry_no") else 0

    fields = {}
    for p in persons:
        for k in ["name", "years", "place", "bio_head", "total", "total_pages"]:
            fields.setdefault(k, {"nonempty": 0, "of": 0})
            fields[k]["of"] += 1
            if p.get(k) not in (None, "", []):
                fields[k]["nonempty"] += 1

    checks = []
    for pid, rec in sorted(per_person.items()):
        pw = next((x for x in persons if x["id"] == pid), {})
        declared = pw.get("total")
        got = rec["entries"]
        checks.append({
            "person_id": pid,
            "declared_total": declared,
            "parsed_entries": got,
            "match": (declared == got) if declared else None,
            "declared_pages": pw.get("total_pages"),
            "pages_done": len(prog["persons"].get(pid, {}).get("pages_done", [])),
        })
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "persons": len(persons),
        "entries": len(entries),
        "person_field_completeness": fields,
        "per_person": per_person,
        "count_checks": checks,
        "progress": {pid: {"status": r.get("status"), "pages_done": len(r.get("pages_done", [])),
                           "total_pages": r.get("total_pages"), "error": r.get("error", "")}
                     for pid, r in sorted(prog["persons"].items())},
    }


# ── selftest（假 transport 直测，零网络）──────────────────────────────────


class FakeClockTransport:
    """记录调用间隔，返回预制响应。用于直测限速/重试/解析。"""

    def __init__(self, responses=None, fail_times=None):
        self.responses = responses or {}
        self.fail_times = fail_times or {}  # url_prefix -> 剩余失败次数
        self.calls = []
        self.t = 1000.0

    def __call__(self, url, headers, timeout):
        self.calls.append({"url": url, "t": self.t, "ua": headers.get("User-Agent", ""),
                           "cookie": headers.get("Cookie", "")})
        self.t += 0.0  # 时间由 client 的 throttle 推进（真实 sleep）
        for pre, n in list(self.fail_times.items()):
            if url.startswith(pre) and n > 0:
                self.fail_times[pre] = n - 1
                raise urllib.error.URLError("simulated failure")
        key = url
        if key not in self.responses:  # 宽松前缀匹配
            for k, v in self.responses.items():
                if url.startswith(k):
                    key = k
                    break
        if key not in self.responses:
            raise urllib.error.HTTPError(url, 404, "nf", {}, None)
        status, body = self.responses[key]
        return status, body, url


FIXTURE_PERSON = """
<html><body>
<font>&nbsp;印學在線＞篆刻年歷＞依人物瀏覽＞姓名檢索＞測試人</font>
<td width='100' align='left'>↑<a HREF='m2MainFind.asp?LM=2&L1=2&L2=2&L3=0&LS=C&SRCHTXT=P5202&SK=MV'>吳熙</a></td>
<font color='#000088' size='2'>共有 2 則</font>
<font>&nbsp;總&nbsp;1&nbsp;頁&nbsp;</font>
<tr bgcolor='#FFFFDD'><td width='45'><b><a name='1'><a HREF='m2MainFind.asp?LM=2&L1=1&L2=2&L3=0&LS=C&SRCHTXT=1799&SK=YV'><font>1799</font></a></a></b>
<td><a href='JavaScript://' onClick="JavaScript:newopen('m2ReadSamplePopup.asp#26')">生</a></td>
<td><p style='line-height: 150%'><b>測試人</b>（甲生）．一歲／測試（某地）人，生平測試。／之1</p>
<p align='center'><font size='2' color='#669999'>全文與《篆刻年歷1051-1911》書籍版1799年之001則相同。</font></td>
<td width='75'><a href='m2ImgShow.asp?STOP=M2IMGS&LM=2&L1=2&L2=1&L3=0&LS=C&SRCHTXT=1799-001'><img src='SBYBImg/red80/Q9901998.gif'></a></td></tr>
<tr bgcolor='#FFFFDD'><td width='45'><b><a name='2'><a HREF='m2MainFind.asp?LM=2&L1=1&L2=2&L3=0&LS=C&SRCHTXT=1850&SK=YV'><font>1850</font></a></a></b>
<td><a href='JavaScript://' onClick="JavaScript:newopen('m2ReadSamplePopup.asp#12')">印</a></td>
<td><p style='line-height: 150%'><b>測試人</b>（甲生）．五十二歲／刻〔測試〕正方朱文印。／之2</p></td><td width='75'></td></tr>
</body></html>
""".encode("big5", errors="replace")

FIXTURE_SEAL_WALL = "請先輸入會員帳號及密碼 會員專屬".encode("big5", errors="replace")


def selftest() -> dict:
    """假 transport：限速间隔 / 重试 / 解析 / 续传（临时目录）。"""
    import tempfile
    results = {}
    # 1) 限速：3 连发，间隔应 ≥ rate
    ft = FakeClockTransport({PERSON_URL.format(pid="QTEST"): (200, FIXTURE_PERSON)})
    c = SealBankClient(rate_limit=1.5, transport=ft)
    t0 = time.monotonic()
    c.get_person_page("QTEST")
    c.get_person_page("QTEST")
    c.get_person_page("QTEST")
    span = time.monotonic() - t0
    gaps = [round(ft.calls[i + 1]["t"] - ft.calls[i]["t"], 2) for i in range(len(ft.calls) - 1)]
    real_gaps = [(ft.calls[i + 1]["t"]) for i in range(len(ft.calls) - 1)]
    results["rate_limit"] = {"calls": len(ft.calls), "wall_seconds": round(span, 2),
                             "min_expected": 2 * 1.5, "pass": span >= 2 * 1.5 - 0.05}
    results["ua"] = ft.calls[0]["ua"]
    # 2) 重试：先失败 2 次 → 第 3 次成功
    ft2 = FakeClockTransport(
        {PERSON_URL.format(pid="QTEST"): (200, FIXTURE_PERSON)},
        fail_times={PERSON_URL.format(pid="QTEST").split("&SRCHTXT")[0]: 2},
    )
    c2 = SealBankClient(rate_limit=HARD_MIN_RATE, transport=ft2)
    r = c2.get_person_page("QTEST")
    results["retry"] = {"ok": r["ok"], "retries": r["retries"], "pass": r["ok"] and r["retries"] == 2}
    # 3) 解析
    p = parse_person_page(FIXTURE_PERSON.decode("big5"), pid="QTEST", page=1)
    results["parse"] = {
        "found": p["found"], "name": p["name"], "total": p["total"], "total_pages": p["total_pages"],
        "entries": len(p["entries"]), "first_year": p["entries"][0]["year"] if p["entries"] else None,
        "first_entry_no": p["entries"][0]["entry_no"] if p["entries"] else None,
        "seal_ids": p["entries"][0]["seal_ids"] if p["entries"] else [],
        "book_ref": p["entries"][0]["book_ref"] if p["entries"] else "",
        "pass": p["found"] and p["total"] == 2 and len(p["entries"]) == 2
        and p["entries"][0]["seal_ids"] == ["1799-001"],
    }
    # 4) 会员墙解析
    w = parse_seal_detail(FIXTURE_SEAL_WALL.decode("big5"))
    results["seal_wall"] = {"member_wall": w["member_wall"], "hint": w["hint"],
                            "pass": w["member_wall"] and w["hint"] == "anonymous_login_wall"}
    # 5) 续传：max_pages=1 后重跑，第 2 次不重复请求页 1（此处单页 fixture，验证 skip 逻辑）
    with tempfile.TemporaryDirectory() as td:
        ft3 = FakeClockTransport({PERSON_URL.format(pid="QTEST"): (200, FIXTURE_PERSON)})
        c3 = SealBankClient(rate_limit=HARD_MIN_RATE, transport=ft3,
                            request_log=open(os.path.join(td, "requests.log"), "w"))
        s1 = fetch_persons(c3, ["QTEST"], td, max_pages=1)
        n1 = len(ft3.calls)
        s2 = fetch_persons(c3, ["QTEST"], td)  # 重跑：应 0 次新请求
        n2 = len(ft3.calls) - n1
        prog = json.load(open(os.path.join(td, "PROGRESS.json")))
        results["resume"] = {"first_run_pages": s1["fetched_pages"], "second_run_new_requests": n2,
                             "status": prog["persons"]["QTEST"]["status"],
                             "pass": s1["fetched_pages"] == 1 and n2 == 0
                             and prog["persons"]["QTEST"]["status"] == "done"}
    results["pass_all"] = all(
        v.get("pass", True) for k, v in results.items() if isinstance(v, dict)
    )
    return results


# ── CLI ────────────────────────────────────────────────────────────────────


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="sealbank research client (礼貌纪律: ≥2.2s/req)")
    ap.add_argument("--rate", type=float, default=DEFAULT_RATE, help="秒/请求（下限 1.5）")
    ap.add_argument("--out", default=os.path.join(here, "out"))
    ap.add_argument("--cookies", default=os.path.join(here, "cookies.txt"),
                    help="cookies.txt 路径（存在即注入；绝不打印）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("probe")
    sp.add_argument("url")

    sub.add_parser("scan")

    sp = sub.add_parser("index-probe", help="探索引页形态（首页 + 4 个姓氏槽）")
    sp.add_argument("--sample", default="1,34,208,389", help="抽查的 n1sttxt 槽")

    sp = sub.add_parser("index", help="全量印人索引（400 姓氏槽，断点续传）")
    sp.add_argument("--limit", type=int, default=0, help="本次最多抓 N 个姓氏槽（0=全部）")
    sp.add_argument("--refetch", action="store_true", help="忽略页缓存强制重抓")

    sp = sub.add_parser("index-spotcheck", help="抽样对拍索引→编年链路（每前缀 1 人）")
    sp.add_argument("--count", type=int, default=10)

    sp = sub.add_parser("m1-catalog", help="真微印庫人物社團全目錄（10 页 / 7,482 筆）")
    sp.add_argument("--pages", type=int, default=10)
    sp.add_argument("--refetch", action="store_true")

    sub.add_parser("index-union", help="篆刻年歷索引 ∪ m1 目錄 → 并集对拍 10,487")

    sp = sub.add_parser("persons")
    sp.add_argument("--ids", required=True, help="逗号分隔印人编号")
    sp.add_argument("--max-pages", type=int, default=0, help="每人最多抓 N 页（0=不限；试跑/中断模拟）")

    sp = sub.add_parser("seals")
    sp.add_argument("--ids", required=True, help="逗号分隔印章编号「年-序」")
    sp.add_argument("--download-thumb", default="", help="另下载 1 张缩图（编号如 Q9901001）")

    sp = sub.add_parser("thumb")
    sp.add_argument("--id", required=True)

    sub.add_parser("report")
    sub.add_parser("selftest")

    args = ap.parse_args(argv)

    cookie = ""
    if os.path.exists(args.cookies):
        try:
            cookie = load_cookie_string(args.cookies)
        except Exception:
            cookie = ""
    os.makedirs(args.out, exist_ok=True)
    log_path = os.path.join(args.out, "requests.log")
    # 跨进程限速暖启动：读上一进程最后请求的起始时刻（epoch 秒）
    warm = 0.0
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()[-1:]
            if lines:
                parts = lines[0].split()
                ts = time.mktime(time.strptime(parts[0], "%Y-%m-%dT%H:%M:%S"))
                warm = ts  # 旧格式=完成时刻（下界）；新格式=起始时刻
        except Exception:
            warm = 0.0
    log_f = open(log_path, "a", encoding="utf-8")
    client = SealBankClient(rate_limit=args.rate, cookie_string=cookie, request_log=log_f,
                            warm_start_ts=warm)

    if args.cmd == "probe":
        r = client.get(args.url)
        text = r.pop("text", "") or ""
        r.pop("body", None)
        if r.get("ok"):
            if "共有" in text and "姓名檢索" in text:
                r["page_kind"] = "person_list"
            elif "請先輸入會員帳號及密碼" in text:
                r["page_kind"] = "anonymous_login_wall"
            elif "目前只能作有限度瀏覽" in text:
                r["page_kind"] = "member_limited_browse"
            else:
                r["page_kind"] = "other"
        print(json.dumps(r, ensure_ascii=False, indent=1))
    elif args.cmd == "scan":
        rep = scan_boundaries(client)
        path = os.path.join(args.out, "boundary_scan.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        slim = {k: rep[k] for k in ["probe_count", "hit_count", "hit_ids", "effective_low",
                                    "effective_high"] if k in rep}
        slim["path"] = path
        print(json.dumps(slim, ensure_ascii=False, indent=1))
    elif args.cmd == "index-probe":
        sample = tuple(int(x) for x in args.sample.split(",") if x.strip())
        out = probe_index(client, args.out, sample_n=sample)
        out.pop("shelf_stroke_groups", None)
        print(json.dumps(out, ensure_ascii=False, indent=1))
    elif args.cmd == "index":
        s = fetch_index(client, args.out, limit=args.limit, refetch=args.refetch)
        slim = {k: s.get(k) for k in ("shelf_unique_n", "pages_fetched", "pages_cached",
                                      "pages_failed", "surname_pages_read", "unique_persons",
                                      "prefix_dist", "entry_count_sum", "person_delta_vs_official",
                                      "entries_delta_vs_official", "with_entry_count_pct",
                                      "page_count_mismatch")}
        print(json.dumps(slim, ensure_ascii=False, indent=1))
    elif args.cmd == "m1-catalog":
        print(json.dumps(fetch_m1_catalog(client, args.out, pages=args.pages,
                                          refetch=args.refetch), ensure_ascii=False, indent=1))
    elif args.cmd == "index-union":
        print(json.dumps(union_summary(args.out), ensure_ascii=False, indent=1))
    elif args.cmd == "index-spotcheck":
        s = spotcheck_index(client, args.out, count=args.count)
        print(json.dumps(s, ensure_ascii=False, indent=1))
    elif args.cmd == "persons":
        ids = args.ids.split(",")
        s = fetch_persons(client, ids, args.out, max_pages=args.max_pages)
        print(json.dumps(s, ensure_ascii=False, indent=1))
    elif args.cmd == "seals":
        s = sample_seals(client, args.ids.split(","), args.out, download_thumb_of=args.download_thumb)
        for rec in s["seals"]:
            if isinstance(rec.get("parsed"), dict):
                rec["parsed"].pop("fields", None) and None
        print(json.dumps(s, ensure_ascii=False, indent=1))
    elif args.cmd == "thumb":
        s = sample_seals(client, [], args.out, download_thumb_of=args.id)
        print(json.dumps(s["thumb"], ensure_ascii=False, indent=1))
    elif args.cmd == "report":
        print(json.dumps(report(args.out), ensure_ascii=False, indent=1))
    elif args.cmd == "selftest":
        print(json.dumps(selftest(), ensure_ascii=False, indent=1))
    log_f.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
