"""印章采集线（seal-ingest，批 1）——Kong。

**权威口径**：Kevin 2026-10-10 三条裁定（范围＝全量 3679；影像全量入包；关联随包 sidecar）。
远端源 `https://yin.fudan.edu.cn`（**只读**：GET/POST 取数，**不上传任何数据**）。

**采集主链路**：
  `seal/list`（1 次，`pageRows=5000` 一次取全 **3679** 枚；**保留 `audit_status` 字段与分布**）
  → **行内字段直接构建关联 sidecar**（印章↔印谱↔印人，见下「关联口径」）
  → 归一化（繁正 ＋ `*_chs` 副字段 ＋ 派生 `seal_ys_label`）→ 落**独立库** `var/seal_ingest.db`
  → 影像全量下载（`iiif_proxy` IIIF 裁切图，落 `var/seal_images/<kind>/<seqid>.jpg` 作缓存 ＋ 台账）
  → xiai 就绪包（`seals.jsonl` ＋ `seal_links.jsonl` ＋ `manifest.json` ＋ `images/`）。

**关键源事实（实测，见 ops/seal-ingest/）**：
  * `seal/list` 行 **65 键**；`seqid` 3679/3679 且**唯一**（＝幂等键）；`delFlag` 全 `'0'`；`sealFl` 全 `'印章'`。
  * `seal/list` 与 `seal/detail` **不同构**（与 person 侧相反）：list 独有全部 `*Chs` 简体副字段；
    detail 独有 `sealYsXzLabel`（形製可读值）/ `sealYzRefId` / `auditUser`。**形製标签已由码表本地派生** ⇒ detail
    降 best-effort（**默认关**，仅补 `seal_ys_ref_id` / `audit_user` / 真源标签校对）。
  * **影像（IIIF 裁切图）**：`https://yin.fudan.edu.cn/iiif_proxy/api/char_proxy/<ref>` ⇒ **302** ⇒
    跟跳转得 `image/jpeg`（urlopen 默认跟跳转）。`NaN_` 开头 ref 预期无图 ⇒ **登记为「源侧无图」而非采集失败**。
  * **429 陷阱**：站点限流形态为 **HTTP 200** ＋ 信封 `{"code":"429", …}` ＋ 无 `data`（`status` 仍可能 `true`）。
    **禁止**把这种回包计为成功；一律指数退避（5s→60s）重试，退避耗尽才落失败清单。

**关联口径（本单裁定，理由见 manifest.link_policy）**：**行内字段直接构建**（`source_face='seal_row'`），
**不逐枚调 `graph/seal`**：
  * 行内 `asBookId`＋`relatedBook` ⇒ 印谱链（3679/3679）；`sealYz`＋`sealYzPersonName` ⇒ 印主链（2379）；
    `sealYzzkzId`＋`sealYzzkz` ⇒ 篆者链（2652）；`sealBkzkzId`＋`sealBkzkz` ⇒ 边款篆者链（254）。
  * 三类 person id（`sealYz` / `sealYzzkzId` / `sealBkzkzId`）与 `var/person_ingest.db` 的
    `persons.source_person_id` **同域**；`asBookId` 经 `var/item_ingest.db` 的 `items.as_book_id`
    **桥接**到印谱 `source_item_id`（写入 link 的 `bridge_item_id`）。
  * `graph/seal` 只多给「印谱 canonical `seqid`」，而该值可由 `asBookId` 桥接**本地派生**；故零额外联网
    即 100% 覆盖，且不与影像下载抢同一站点的请求额度（`--with-graph` 可开，默认关）。

纪律：
  * **只加法**：不改既有 E1〜E7 / persons / items；**不碰** `yinpu.db`、`var/person_ingest.db`、
    `var/item_ingest.db`、`exports/person_*`、`exports/item_*`；
  * **独立库**：本线一律写 `feicui/var/seal_ingest.db`；影像缓存 `feicui/var/seal_images/`；
  * **HTTP 客户端只用 stdlib**（`urllib.request`），不改 `server/requirements.txt`；
  * **礼貌限速**：串行 + 请求间隔 + 抖动；**可断点续跑**；**不把源站打到 429**，429 不得当成功；
  * **不得丢源**：源列表行（＋可选 detail / graph）一律入 `raw_json`；
  * **失败不静默**：逐条失败写进批次包 `report.json` 的失败清单（**不写进 `seals.jsonl`**）。

**繁简口径**：**繁体为正字段、简体入 `*_chs` 副字段**，**不做任何转换改写**。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("feicui.api.seals")

SEAL_SCHEMA_VERSION = "feicui.seal_ingest/1"
MANIFEST_SCHEMA_VERSION = 1

# ── 形製码表（**Kevin 标定：每码 2 枚 × 20 次调用 × 0 冲突 ⇒ 纯函数可派生**）──────────────
# **源侧原文写作「异性」（非「异形」）——逐字照登，不得代改为「异形」**。
SEAL_YS_XZ_LOOKUP: dict[int, str] = {
    1: "白文方印",
    2: "朱文方印",
    3: "白文圆印",
    4: "朱文圆印",
    5: "白文长方印",
    6: "朱文长方印",
    7: "白文椭圆印",
    8: "朱文椭圆印",
    9: "朱文异性印",
    10: "白文异性印",
}

# ── auditStatus 语义（源侧枚举，仅作读数说明，不改写源值）──────────────────────────────
AUDIT_STATUS_NOTE: dict[str, str] = {
    "0": "未审",
    "1": "已审（默认发布子集，实测 2929）",
    "2": "已发布（statistic.sealCount，实测 716）",
    "9": "其它/退稿（实测 31）",
}

# ── seal 本体字段（键序即 JSONL 键序；繁正 ＋ *_chs 副字段）──────────────────────────────
SEAL_FIELDS: list[str] = [
    "source_seal_id",        # seqid —— 幂等键（原样字符串）
    "seal_uri",              # sealUri
    "category",              # sealFl（恒「印章」）
    "seal_wen",              # sealYwSmwz —— 印文释文（繁）
    "seal_wen_chs",          # sealYwSmwzChs（简）
    "seal_wen_pinyin",       # sealYwSwpy
    "seal_wen_wzly",         # sealYwWzly（文字来源，繁）
    "seal_wen_wzly_chs",     # sealYwWzlyChs
    "seal_wen_yssw",         # sealYwYssw（印文…，繁）
    "seal_wen_yssw_chs",     # sealYwYsswChs
    "seal_wen_wyz",          # sealYwWwyz
    "seal_wen_zjsw",         # sealYwZjsw（繁）
    "seal_wen_zjsw_chs",     # sealYwZjswChs
    "seal_ys_xz",            # sealYsXz —— 形製码（**整数或 null，644 行 null 合法**）
    "seal_ys_label",         # 派生：SEAL_YS_XZ_LOOKUP[sealYsXz]（码 null 时为 null）
    "seal_ys_kf",            # sealYsKf
    "seal_ys_st",            # sealYsSt
    "seal_zyz",              # sealZyz
    "seal_yz",               # sealYz —— 印主 person id
    "seal_yz_person_name",   # sealYzPersonName（繁）
    "seal_yz_person_name_chs",  # sealYzPersonNameChs（简）
    "seal_yz_name",          # sealYzName（实测全 null）
    "seal_yz_ref_id",        # sealYzRefId —— **detail 独有**（默认 null）
    "seal_yzzkz",            # sealYzzkz —— 篆者名（繁）
    "seal_yzzkz_chs",        # sealYzzkzChs
    "seal_yzzkz_id",         # sealYzzkzId —— 篆者 person id
    "seal_bk",               # sealBk —— 边款（繁）
    "seal_bk_chs",           # sealBkChs
    "seal_bkzkz",            # sealBkzkz —— 边款篆者（繁）
    "seal_bkzkz_chs",        # sealBkzkzChs
    "seal_bkzkz_id",         # sealBkzkzId —— 边款篆者 person id
    "as_book_id",            # asBookId —— 桥接印谱（items.as_book_id）
    "related_book",          # relatedBook —— 所属印谱名（繁）
    "seal_yt_url",           # sealYtUrl —— 印面图 ref
    "seal_ytsw_url",         # sealYtswUrl —— 印体释文图 ref
    "seal_yzbk_url",         # sealYzbkUrl —— 边款图 ref
    "seal_yzqt_url",         # sealYzqtUrl（实测 3）
    "seal_threed_url",       # sealThreedUrl（实测全 null）
    "seal_title",            # sealTitle（实测全 null）
    "seal_title_chs",        # sealTitleChs
    "seal_org",              # sealOrg（实测全 null）
    "seal_org_name",         # sealOrgName（实测全 null）
    "seal_cz",               # sealCz（实测全 null）
    "seal_cc",               # sealCc（实测全 null）
    "seal_ly",               # sealLy（实测全 null）
    "seal_yn",               # sealYn
    "seal_yksj_lsjn",        # sealYksjLsjn —— 印刻时间（繁）
    "seal_yksj_lsjn_chs",    # sealYksjLsjnChs
    "seal_yksj_gyjn",        # sealYksjGyjn —— 印刻公元年
    "audit_status",          # auditStatus —— **保留字段**（分布见 manifest）
    "misc",                  # 低频/审计元字段子对象
    "raw_json",              # 源原文：{"list": 列表行, "detail": 详情行|null, "graph": 图|null}
]
SEAL_CONTENT_COLS = SEAL_FIELDS  # 内容指纹参与列（排除 batch_id / updated_at）

# ── sidecar `seal_links`（印章↔印谱/印人）字段 ─────────────────────────────────────────
LINK_FIELDS: list[str] = [
    "source_seal_id", "link_kind", "ref_id", "ref_name", "ref_name_chs",
    "creator_type", "bridge_item_id", "source_face", "seq",
]
LINK_CONTENT_COLS = LINK_FIELDS

# ── 影像台账字段 ─────────────────────────────────────────────────────────────────────
IMAGE_FIELDS: list[str] = [
    "seqid", "kind", "source_ref", "source_url", "local_path",
    "bytes", "sha256", "status", "error", "no_source_reason",
    # —— TIFF 转换面（内容寻址，供 xiai 影像库；§口径变更 2026-10-10）——
    "tiff_path", "tiff_sha256", "tiff_bytes", "width", "height", "upscaled",
]

# ── xiai 影像库权威契约（读源码 `xiai/server/app/store.py` ＋ `codec.py` 照此对齐）──────────
#   * 端点 POST /api/image/store；读 GET /api/image/original/{sha256}（另 slices|thumb|download）
#   * **只收 TIFF 容器**（魔数 `II*\0` / `MM\0*`；不回落、不冒充），违则 NOT_IMAGE
#   * 上限：产物侧 STORED_MAX_BYTES = 4 MiB；输入侧 MAX_INPUT_BYTES = 1 MB
#   * 内容寻址路径形状 ＝ <sha256[:2]>/<sha256>.tiff（sha256 ＝ TIFF 字节的 sha256，即索引键）
XIAI_STORED_MAX_BYTES = 4 * 1024 * 1024
XIAI_MAX_INPUT_BYTES = 1 * 1024 * 1024
TIFF_MAGIC_LE = b"II*\x00"   # little-endian
TIFF_MAGIC_BE = b"MM\x00*"   # big-endian
CONVERSION_TAG = "jpeg->tiff(lossless container)"

# 关联来源面
FACE_SEAL_ROW = "seal_row"       # 行内字段直接构建（**主源**）
FACE_SEAL_GRAPH = "seal_graph"   # graph/seal（best-effort，默认关）

# 影像种类
IMAGE_KINDS = ("yt", "ytsw", "yzbk")
IMAGE_SRC_FIELD = {
    "yt": "sealYtUrl",       # 印面图 3679
    "ytsw": "sealYtswUrl",   # 印体释文图 2627
    "yzbk": "sealYzbkUrl",   # 边款图 459
}
# 表内列名（snake_case）——collect_image_refs 用
IMAGE_SRC_COL = {
    "yt": "seal_yt_url",
    "ytsw": "seal_ytsw_url",
    "yzbk": "seal_yzbk_url",
}
IMAGE_KIND_NOTE = {
    "yt": "印面图（sealYtUrl）",
    "ytsw": "印体释文图（sealYtswUrl）",
    "yzbk": "边款图（sealYzbkUrl）",
}

# 影像 ledger 状态（三态）
IMG_OK = "ok"
IMG_FAIL = "failed"                 # **只留给可重试的瞬态错误**（收尾应为空）
IMG_NO_SOURCE = "source_no_image"   # 源侧无图 / 源侧坏图（**非采集失败**）

# `source_no_image` 的子因（分开记；`no_source_reason` 列）
NO_SOURCE_NAN_REF = "nan_ref"       # ref 以 `NaN_` 开头 ⇒ 源侧无图
NO_SOURCE_HTTP_500 = "http_500"     # 有界重试后仍 HTTP 500 ⇒ 源侧坏图
NO_SOURCE_BAD_BYTES = "bad_bytes"   # HTTP 200 ＋ content-type=image/jpeg，但正文非可解码影像 ⇒ 源侧坏字节
NO_SOURCE_REASON_NOTE = {
    NO_SOURCE_NAN_REF: "ref 以 NaN_ 开头（源侧无图）",
    NO_SOURCE_HTTP_500: "有界重试后仍 HTTP 500（源侧坏图；站点同图页面 naturalWidth=0）",
    NO_SOURCE_BAD_BYTES: "HTTP 200 且 content-type=image/jpeg，但正文非可解码影像（源侧坏字节；持久复现）",
}

# 源侧 5xx（坏图）**有界重试**：3 轮 2/8/30s 退避（与 429 退避分开——500 按 ref 恒定、非限流）
SERVER_RETRY_BACKOFFS = (2.0, 8.0, 30.0)


MISC_SOURCE_KEYS = [
    "createdTime", "updateTime", "sortNum", "delFlag", "createdUser", "createdUserName",
    "updatedUser", "updatedUserName", "sealQtrw", "cache",
    "auditTime", "auditUser", "auditUserUri", "auditRemark", "auditLogSeqid",
]

RATE_LIMIT_MARKER = '{"code":"429", ...}'  # 陷阱形态（字符串 code）

# ── 限速自适应（与 items 线同口径）────────────────────────────────────────────────────
RL_COOLDOWN_BASE = 45.0
RL_COOLDOWN_MAX = 180.0
RL_MAX_ATTEMPTS = 6
RL_DELAY_GROWTH = 1.6
RL_DELAY_MAX = 3.0


class FetchError(RuntimeError):
    """单条取数失败 ⇒ 计入失败清单，**不静默跳过**。"""


class RateLimited(FetchError):
    """源侧限速（HTTP **200** + 信封 `code:"429"` + 无 `data`）⇒ 退避重试。"""


class ServerUnavailable(FetchError):
    """源侧 5xx（如 HTTP 500）——对单张影像按 ref **恒定**（非限流）；有界重试后仍失败 ⇒ 判源侧坏图。"""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status



class ImportPackageError(RuntimeError):
    """生成 xiai 就绪包失败（结构化错误 ⇒ 路由层落 404/409 JSON）。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# ═══════════════════════════════════════════════════════════════════════════ HTTP（stdlib）
def _one_call(url: str, *, method: str, data: bytes | None, headers: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            http_status = resp.status
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise RateLimited(f"HTTP 429 {url}") from exc
        if 500 <= exc.code < 600:
            raise ServerUnavailable(f"HTTP {exc.code} {url}", status=exc.code) from exc
        raise FetchError(f"HTTP {exc.code} {url}") from exc
    except Exception as exc:
        raise FetchError(f"{type(exc).__name__}: {exc} @ {url}") from exc
    if http_status != 200:
        raise FetchError(f"HTTP {http_status} {url}")
    try:
        body = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise FetchError(f"非 JSON 响应 @ {url}: {exc}") from exc
    if not isinstance(body, dict):
        raise FetchError(f"响应信封非对象 @ {url}")
    code = body.get("code")
    if str(code) == "429" or any(h in str(body.get("msg") or "") for h in ("频密", "频繁")):
        raise RateLimited(f"源侧限速 code={code!r} msg={body.get('msg')!r} @ {url}")
    return body


def _http_json(base: str, path: str, *, method: str = "GET", payload: dict | None = None,
               timeout: float = 30.0, retries: int = 5, backoff: float = 5.0) -> dict:
    """带**限速退避**的取数：命中 429 时指数退避重试（5→10→20→40→60 秒，上限 60s）。"""
    url = f"{base.rstrip('/')}{path}"
    data = None
    headers = {"Accept": "application/json", "User-Agent": "feicui-seal-ingest/1"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            body = _one_call(url, method=method, data=data, headers=headers, timeout=timeout)
            code = body.get("code")
            if code not in (200, "200"):
                raise FetchError(f"源信封 code={code!r} msg={body.get('msg')!r} @ {url}")
            return body
        except RateLimited as exc:
            last = exc
            if attempt >= retries:
                break
            sleep_s = min(backoff * (2 ** attempt), 60.0)
            log.warning("源侧限速，退避 %.1fs（第 %d/%d 次重试）：%s", sleep_s, attempt + 1, retries, url)
            time.sleep(sleep_s)
    raise last or FetchError(f"取数失败 @ {url}")


def fetch_seals_list(base: str, *, page_rows: int = 5000, audit_status: str | None = None,
                     timeout: float = 30.0) -> tuple[list[dict], int]:
    """列表页：`POST seal/list`，`pageRows=5000` 一次取全（源 `total`＝3679）。"""
    payload: dict[str, Any] = {"pageNum": 1, "pageRows": int(page_rows)}
    if audit_status is not None:
        payload["auditStatus"] = str(audit_status)
    body = _http_json(base, "/seal/list", method="POST", payload=payload, timeout=timeout)
    rows = body.get("data") or []
    total = int(body.get("total") or len(rows))
    return list(rows), total


def fetch_seal_detail(base: str, seqid: str, *, timeout: float = 30.0, retries: int = 5) -> dict:
    """详情页：`GET seal/detail/<seqid>`（**路径参数＝ seqid**）。

    **best-effort（默认关）**：仅补 `seal_ys_ref_id` / `audit_user` / 真源标签校对。
    """
    body = _http_json(base, f"/seal/detail/{seqid}", timeout=timeout, retries=retries, backoff=5.0)
    data = body.get("data")
    if not isinstance(data, dict):
        raise FetchError(f"detail 无 data 字段：{seqid}")
    return data


def fetch_seal_graph(base: str, seqid: str, *, timeout: float = 30.0, retries: int = 3) -> dict:
    """关联图：`GET graph/seal/<seqid>`（**路径参数＝ seqid**）。**best-effort（默认关）**。

    形态：`{"children":[{"name":"印谱","children":[{creatorType,name,id(=book seqid),type:'印谱'}]},
    {"name":"印人","children":[{creatorType,name,id(=personGrbsm),type:'印人'}]}]}`。
    """
    body = _http_json(base, f"/graph/seal/{seqid}", timeout=timeout, retries=retries, backoff=5.0)
    data = body.get("data")
    if not isinstance(data, dict):
        raise FetchError(f"graph 无 data 字段：{seqid}")
    return data


def iiif_host(base: str) -> str:
    """由 source base 推出 IIIF host（`.../service_yinpu` → `https://yin.fudan.edu.cn`）。"""
    b = base.rstrip("/")
    if b.endswith("/service_yinpu"):
        b = b[: -len("/service_yinpu")]
    return b


def image_url(base: str, ref: str) -> str:
    """IIIF 裁切图 URL：`<host>/iiif_proxy/api/char_proxy/<ref>`（**302 ⇒ 跟跳转得 image/jpeg**）。"""
    return f"{iiif_host(base)}/iiif_proxy/api/char_proxy/{ref}"


# ═══════════════════════════════════════════════════════════════════════════ 归一化
def _text(v: Any) -> str | None:
    """文本：源原文照录；`None` / 空串 ⇒ `None`（不设空串特值）。"""
    if v is None:
        return None
    s = str(v)
    return s if s != "" else None


def _int_or_null(v: Any) -> int | None:
    """整数或 `null`：非纯整数 / 空 ⇒ `None`（**不设 0 特值**——0 不在形製码域内）。"""
    if v is None:
        return None
    s = str(v).strip()
    if s == "":
        return None
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def derive_seal_ys_label(seal_ys_xz: Any) -> str | None:
    """形製码 ⇒ 可读值（纯函数；码 null / 越界 ⇒ null）。"""
    n = _int_or_null(seal_ys_xz)
    if n is None:
        return None
    return SEAL_YS_XZ_LOOKUP.get(n)


def normalize_seal(list_row: dict, detail_row: dict | None = None) -> dict:
    """归一化一条 `seals` 记录。取值优先 **列表行**（**list 是本体主源**；detail 仅补两字段）。"""
    src = list_row if isinstance(list_row, dict) else {}
    dsrc = detail_row if isinstance(detail_row, dict) else {}
    seqid = str(src.get("seqid") if src.get("seqid") is not None
                else dsrc.get("seqid") or "").strip()
    ys_xz = _int_or_null(src.get("sealYsXz"))
    misc = {k: _text(src.get(k)) for k in MISC_SOURCE_KEYS}
    return {
        "source_seal_id": seqid,
        "seal_uri": _text(src.get("sealUri")),
        "category": _text(src.get("sealFl")),
        "seal_wen": _text(src.get("sealYwSmwz")),
        "seal_wen_chs": _text(src.get("sealYwSmwzChs")),
        "seal_wen_pinyin": _text(src.get("sealYwSwpy")),
        "seal_wen_wzly": _text(src.get("sealYwWzly")),
        "seal_wen_wzly_chs": _text(src.get("sealYwWzlyChs")),
        "seal_wen_yssw": _text(src.get("sealYwYssw")),
        "seal_wen_yssw_chs": _text(src.get("sealYwYsswChs")),
        "seal_wen_wyz": _text(src.get("sealYwWwyz")),
        "seal_wen_zjsw": _text(src.get("sealYwZjsw")),
        "seal_wen_zjsw_chs": _text(src.get("sealYwZjswChs")),
        "seal_ys_xz": ys_xz,
        "seal_ys_label": derive_seal_ys_label(ys_xz),
        "seal_ys_kf": _text(src.get("sealYsKf")),
        "seal_ys_st": _text(src.get("sealYsSt")),
        "seal_zyz": _text(src.get("sealZyz")),
        "seal_yz": _text(src.get("sealYz")),
        "seal_yz_person_name": _text(src.get("sealYzPersonName")),
        "seal_yz_person_name_chs": _text(src.get("sealYzPersonNameChs")),
        "seal_yz_name": _text(src.get("sealYzName")),
        "seal_yz_ref_id": _text(dsrc.get("sealYzRefId")),
        "seal_yzzkz": _text(src.get("sealYzzkz")),
        "seal_yzzkz_chs": _text(src.get("sealYzzkzChs")),
        "seal_yzzkz_id": _text(src.get("sealYzzkzId")),
        "seal_bk": _text(src.get("sealBk")),
        "seal_bk_chs": _text(src.get("sealBkChs")),
        "seal_bkzkz": _text(src.get("sealBkzkz")),
        "seal_bkzkz_chs": _text(src.get("sealBkzkzChs")),
        "seal_bkzkz_id": _text(src.get("sealBkzkzId")),
        "as_book_id": _text(src.get("asBookId")),
        "related_book": _text(src.get("relatedBook")),
        "seal_yt_url": _text(src.get("sealYtUrl")),
        "seal_ytsw_url": _text(src.get("sealYtswUrl")),
        "seal_yzbk_url": _text(src.get("sealYzbkUrl")),
        "seal_yzqt_url": _text(src.get("sealYzqtUrl")),
        "seal_threed_url": _text(src.get("sealThreedUrl")),
        "seal_title": _text(src.get("sealTitle")),
        "seal_title_chs": _text(src.get("sealTitleChs")),
        "seal_org": _text(src.get("sealOrg")),
        "seal_org_name": _text(src.get("sealOrgName")),
        "seal_cz": _text(src.get("sealCz")),
        "seal_cc": _text(src.get("sealCc")),
        "seal_ly": _text(src.get("sealLy")),
        "seal_yn": _text(src.get("sealYn")),
        "seal_yksj_lsjn": _text(src.get("sealYksjLsjn")),
        "seal_yksj_lsjn_chs": _text(src.get("sealYksjLsjnChs")),
        "seal_yksj_gyjn": _text(src.get("sealYksjGyjn")),
        "audit_status": _text(src.get("auditStatus")),
        "misc": misc,
        "raw_json": {"list": list_row, "detail": detail_row},
    }


def links_from_row(seqid: str, row: dict, bridge: dict[str, str] | None = None) -> list[dict]:
    """来源（**主源**）：行内字段直接构建关联（`source_face='seal_row'`）。

    产四类链：
      * `book`        —— 印谱（`asBookId`＋`relatedBook`；`bridge_item_id`＝经 items.as_book_id 桥到的印谱 source_item_id）
      * `person_yz`   —— 印主（`sealYz`＋`sealYzPersonName`）
      * `person_zzkz` —— 篆者（`sealYzzkzId`＋`sealYzzkz`）
      * `person_bkzkz`—— 边款篆者（`sealBkzkzId`＋`sealBkzkz`）
    仅当 `ref_id` 非空时落链（**不编造**）。
    """
    bridge = bridge or {}
    out: list[dict] = []
    as_book_id = _text(row.get("asBookId"))
    if as_book_id:
        out.append({
            "source_seal_id": seqid, "link_kind": "book", "ref_id": as_book_id,
            "ref_name": _text(row.get("relatedBook")), "ref_name_chs": None,
            "creator_type": None, "bridge_item_id": bridge.get(as_book_id),
            "source_face": FACE_SEAL_ROW, "seq": 0,
        })
    yz = _text(row.get("sealYz"))
    if yz:
        out.append({
            "source_seal_id": seqid, "link_kind": "person_yz", "ref_id": yz,
            "ref_name": _text(row.get("sealYzPersonName")),
            "ref_name_chs": _text(row.get("sealYzPersonNameChs")),
            "creator_type": None, "bridge_item_id": None,
            "source_face": FACE_SEAL_ROW, "seq": 0,
        })
    zzkz = _text(row.get("sealYzzkzId"))
    if zzkz:
        out.append({
            "source_seal_id": seqid, "link_kind": "person_zzkz", "ref_id": zzkz,
            "ref_name": _text(row.get("sealYzzkz")),
            "ref_name_chs": _text(row.get("sealYzzkzChs")),
            "creator_type": None, "bridge_item_id": None,
            "source_face": FACE_SEAL_ROW, "seq": 0,
        })
    bkzkz = _text(row.get("sealBkzkzId"))
    if bkzkz:
        out.append({
            "source_seal_id": seqid, "link_kind": "person_bkzkz", "ref_id": bkzkz,
            "ref_name": _text(row.get("sealBkzkz")),
            "ref_name_chs": _text(row.get("sealBkzkzChs")),
            "creator_type": None, "bridge_item_id": None,
            "source_face": FACE_SEAL_ROW, "seq": 0,
        })
    return out


def links_from_graph(seqid: str, graph_data: dict | None) -> list[dict]:
    """来源②（best-effort）：`graph/seal/<seqid>` 的「印谱」/「印人」子项（`source_face='seal_graph'`）。

    「印谱」子项 `id` ＝ 印谱 canonical `seqid`（可桥接 items.source_item_id）；
    「印人」子项 `id` ＝ `personGrbsm`；`creatorType` 如实取。
    """
    out: list[dict] = []
    if not isinstance(graph_data, dict):
        return out
    for cat in (graph_data.get("children") or []):
        cname = str(cat.get("name") or "").strip()
        for seq, c in enumerate(cat.get("children") or []):
            if not isinstance(c, dict):
                continue
            if cname == "印谱":
                out.append({
                    "source_seal_id": seqid, "link_kind": "book",
                    "ref_id": _text(c.get("id")), "ref_name": _text(c.get("name")),
                    "ref_name_chs": None, "creator_type": _text(c.get("creatorType")),
                    "bridge_item_id": _text(c.get("id")),  # graph 直接给印谱 seqid
                    "source_face": FACE_SEAL_GRAPH, "seq": seq,
                })
            elif cname == "印人":
                out.append({
                    "source_seal_id": seqid, "link_kind": "person_graph",
                    "ref_id": _text(c.get("id")), "ref_name": _text(c.get("name")),
                    "ref_name_chs": None, "creator_type": _text(c.get("creatorType")),
                    "bridge_item_id": None, "source_face": FACE_SEAL_GRAPH, "seq": seq,
                })
    return out


def merge_links(seqid: str, primary: list[dict], secondary: list[dict]) -> list[dict]:
    """合并并按 **(link_kind, ref_id)** 去重（保首见；主源在前）。"""
    seen: set[tuple] = set()
    out: list[dict] = []
    for l in list(primary) + list(secondary):
        key = (l.get("link_kind"), l.get("ref_id"))
        if key in seen:
            continue
        seen.add(key)
        out.append(l)
    return out


# ═══════════════════════════════════════════════════════════════════════════ 存储（独立库）
SCHEMA_SQL = [
    """CREATE TABLE IF NOT EXISTS seal_import_batches (
        batch_id TEXT PRIMARY KEY,
        created_at TEXT, updated_at TEXT, status TEXT,
        source_total INTEGER, fetched INTEGER, seals_ok INTEGER, links_ok INTEGER,
        failed_count INTEGER, elapsed_s REAL, package_dir TEXT, report_path TEXT,
        content_fingerprint TEXT, params_json TEXT, notes TEXT,
        last_run_kind TEXT, last_run_fetched INTEGER, last_run_skipped INTEGER,
        last_run_elapsed_s REAL, last_run_at TEXT,
        images_ok INTEGER, images_failed INTEGER, images_no_source INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS seals (
        source_seal_id TEXT PRIMARY KEY,
        seal_uri TEXT, category TEXT,
        seal_wen TEXT, seal_wen_chs TEXT, seal_wen_pinyin TEXT,
        seal_wen_wzly TEXT, seal_wen_wzly_chs TEXT, seal_wen_yssw TEXT, seal_wen_yssw_chs TEXT,
        seal_wen_wyz TEXT, seal_wen_zjsw TEXT, seal_wen_zjsw_chs TEXT,
        seal_ys_xz INTEGER, seal_ys_label TEXT, seal_ys_kf TEXT, seal_ys_st TEXT,
        seal_zyz TEXT, seal_yz TEXT, seal_yz_person_name TEXT, seal_yz_person_name_chs TEXT,
        seal_yz_name TEXT, seal_yz_ref_id TEXT,
        seal_yzzkz TEXT, seal_yzzkz_chs TEXT, seal_yzzkz_id TEXT,
        seal_bk TEXT, seal_bk_chs TEXT, seal_bkzkz TEXT, seal_bkzkz_chs TEXT, seal_bkzkz_id TEXT,
        as_book_id TEXT, related_book TEXT,
        seal_yt_url TEXT, seal_ytsw_url TEXT, seal_yzbk_url TEXT, seal_yzqt_url TEXT, seal_threed_url TEXT,
        seal_title TEXT, seal_title_chs TEXT, seal_org TEXT, seal_org_name TEXT,
        seal_cz TEXT, seal_cc TEXT, seal_ly TEXT, seal_yn TEXT,
        seal_yksj_lsjn TEXT, seal_yksj_lsjn_chs TEXT, seal_yksj_gyjn TEXT,
        audit_status TEXT, misc TEXT, raw_json TEXT,
        batch_id TEXT, updated_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS seal_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_seal_id TEXT, link_kind TEXT, ref_id TEXT, ref_name TEXT, ref_name_chs TEXT,
        creator_type TEXT, bridge_item_id TEXT, source_face TEXT, seq INTEGER, batch_id TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS seal_images (
        seqid TEXT, kind TEXT, source_ref TEXT, source_url TEXT, local_path TEXT,
        bytes INTEGER, sha256 TEXT, status TEXT, error TEXT, no_source_reason TEXT, updated_at TEXT,
        tiff_path TEXT, tiff_sha256 TEXT, tiff_bytes INTEGER,
        width INTEGER, height INTEGER, upscaled INTEGER,
        PRIMARY KEY (seqid, kind)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_seal_links_seal ON seal_links(source_seal_id)",
    "CREATE INDEX IF NOT EXISTS idx_seal_links_ref ON seal_links(link_kind, ref_id)",
    "CREATE INDEX IF NOT EXISTS idx_seals_audit ON seals(audit_status)",
    "CREATE INDEX IF NOT EXISTS idx_seals_ys_xz ON seals(seal_ys_xz)",
    "CREATE INDEX IF NOT EXISTS idx_seals_as_book_id ON seals(as_book_id)",
    "CREATE INDEX IF NOT EXISTS idx_seal_images_status ON seal_images(status)",
]

BATCH_EXTRA_COLUMNS: list[tuple[str, str]] = [
    ("last_run_kind", "TEXT"),
    ("last_run_fetched", "INTEGER"),
    ("last_run_skipped", "INTEGER"),
    ("last_run_elapsed_s", "REAL"),
    ("last_run_at", "TEXT"),
    ("images_ok", "INTEGER"),
    ("images_failed", "INTEGER"),
    ("images_no_source", "INTEGER"),
]

# seal_images 增量列（老库补列）
IMAGE_EXTRA_COLUMNS: list[tuple[str, str]] = [
    ("no_source_reason", "TEXT"),
    ("tiff_path", "TEXT"),
    ("tiff_sha256", "TEXT"),
    ("tiff_bytes", "INTEGER"),
    ("width", "INTEGER"),
    ("height", "INTEGER"),
    ("upscaled", "INTEGER"),
]


def _connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def _now() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def ensure_schema(db_path: Path | str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        for sql in SCHEMA_SQL:
            conn.execute(sql)
        have = {r[1] for r in conn.execute("PRAGMA table_info(seal_import_batches)")}
        for name, decl in BATCH_EXTRA_COLUMNS:
            if name not in have:
                conn.execute(f"ALTER TABLE seal_import_batches ADD COLUMN {name} {decl}")
        have_img = {r[1] for r in conn.execute("PRAGMA table_info(seal_images)")}
        for name, decl in IMAGE_EXTRA_COLUMNS:
            if name not in have_img:
                conn.execute(f"ALTER TABLE seal_images ADD COLUMN {name} {decl}")
        conn.commit()
    finally:
        conn.close()


def seal_exists(db_path: Path | str, seqid: str) -> bool:
    conn = _connect(db_path)
    try:
        return conn.execute("SELECT 1 FROM seals WHERE source_seal_id=?", (seqid,)).fetchone() is not None
    finally:
        conn.close()


def upsert_seal(db_path: Path | str, rec: dict, batch_id: str) -> None:
    cols = list(SEAL_FIELDS)
    placeholders = ", ".join("?" for _ in cols)
    update = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "source_seal_id")
    vals = []
    for c in cols:
        v = rec.get(c)
        if c in ("misc", "raw_json"):
            v = json.dumps(v, ensure_ascii=False)
        elif c == "seal_ys_xz":
            v = v if v is None else int(v)
        vals.append(v)
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            f"INSERT INTO seals ({', '.join(cols)}, batch_id, updated_at) "
            f"VALUES ({placeholders}, ?, ?) "
            f"ON CONFLICT(source_seal_id) DO UPDATE SET {update}, batch_id=excluded.batch_id, "
            f"updated_at=excluded.updated_at",
            vals + [batch_id, _now()],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def replace_seal_links(db_path: Path | str, seqid: str, links: list[dict], batch_id: str) -> int:
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM seal_links WHERE source_seal_id=?", (seqid,))
        for l in links:
            conn.execute(
                "INSERT INTO seal_links (source_seal_id, link_kind, ref_id, ref_name, ref_name_chs, "
                "creator_type, bridge_item_id, source_face, seq, batch_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (l.get("source_seal_id"), l.get("link_kind"), l.get("ref_id"), l.get("ref_name"),
                 l.get("ref_name_chs"), l.get("creator_type"), l.get("bridge_item_id"),
                 l.get("source_face"), l.get("seq"), batch_id),
            )
        conn.commit()
        return len(links)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def content_fingerprint(conn: sqlite3.Connection) -> str:
    """seals + seal_links 的**内容指纹**（排除 batch_id / updated_at / 自增 id）。"""
    h = hashlib.sha256()
    for row in conn.execute(f"SELECT {', '.join(SEAL_CONTENT_COLS)} FROM seals ORDER BY source_seal_id"):
        h.update(json.dumps([row[i] for i in range(len(SEAL_CONTENT_COLS))], ensure_ascii=False).encode("utf-8"))
        h.update(b"\n")
    for row in conn.execute(
        f"SELECT {', '.join(LINK_CONTENT_COLS)} FROM seal_links "
        f"ORDER BY source_seal_id, link_kind, ref_id, source_face, seq"
    ):
        h.update(json.dumps([row[i] for i in range(len(LINK_CONTENT_COLS))], ensure_ascii=False).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def db_counts(db_path: Path | str) -> dict:
    conn = _connect(db_path)
    try:
        return {
            "seals": conn.execute("SELECT COUNT(*) FROM seals").fetchone()[0],
            "links": conn.execute("SELECT COUNT(*) FROM seal_links").fetchone()[0],
            "images": conn.execute("SELECT COUNT(*) FROM seal_images").fetchone()[0],
            "batches": conn.execute("SELECT COUNT(*) FROM seal_import_batches").fetchone()[0],
        }
    finally:
        conn.close()


def batch_db_counts(db_path: Path | str, batch_id: str) -> dict:
    conn = _connect(db_path)
    try:
        return {
            "seals": conn.execute("SELECT COUNT(*) FROM seals WHERE batch_id=?", (batch_id,)).fetchone()[0],
            "links": conn.execute("SELECT COUNT(*) FROM seal_links WHERE batch_id=?", (batch_id,)).fetchone()[0],
        }
    finally:
        conn.close()


# ── 批次 ──────────────────────────────────────────────────────────────────────────────────
def next_batch_id(export_root: Path, when: datetime | None = None) -> str:
    when = when or datetime.now()
    stamp = when.strftime("%Y%m%d")
    prefix = f"seal_{stamp}_"
    used = set()
    if Path(export_root).is_dir():
        for p in Path(export_root).iterdir():
            if p.is_dir() and p.name.startswith(prefix):
                used.add(p.name)
    nn = 1
    while f"{prefix}{nn:02d}" in used:
        nn += 1
    return f"{prefix}{nn:02d}"


def get_batch(db_path: Path | str, batch_id: str) -> dict | None:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM seal_import_batches WHERE batch_id=?", (batch_id,)).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def create_batch(db_path: Path | str, batch_id: str, params: dict, source_total: int | None = None) -> None:
    """开批次。**幂等**：同 `batch_id` 重跑**保留** `created_at` 与既有采集计数（绝不归零）。"""
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO seal_import_batches "
            "(batch_id, created_at, updated_at, status, source_total, fetched, seals_ok, "
            " links_ok, failed_count, elapsed_s, package_dir, report_path, content_fingerprint, params_json, notes) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(batch_id) DO UPDATE SET "
            "  updated_at=excluded.updated_at, status='RUNNING', "
            "  source_total=excluded.source_total, params_json=excluded.params_json",
            (batch_id, _now(), _now(), "RUNNING", source_total, 0, 0, 0, 0, 0.0,
             None, None, None, json.dumps(params, ensure_ascii=False), None),
        )
        conn.commit()
    finally:
        conn.close()


BATCH_FINISH_FIELDS = [
    "status", "source_total", "fetched", "seals_ok", "links_ok", "failed_count", "elapsed_s",
    "package_dir", "report_path", "content_fingerprint",
    "last_run_kind", "last_run_fetched", "last_run_skipped", "last_run_elapsed_s", "last_run_at",
    "images_ok", "images_failed", "images_no_source", "notes",
]


def finish_batch(db_path: Path | str, batch_id: str, **kw: Any) -> None:
    """更新批次计数。**只更新显式传入的字段**（未传者保留原值）——
    避免影像子流程只报 `images_*` 时把 `source_total` / `seals_ok` 等无关字段清空。"""
    present = [f for f in BATCH_FINISH_FIELDS if f in kw]
    fields = ["updated_at"] + present
    values = [_now()] + [kw[f] for f in present]
    conn = _connect(db_path)
    try:
        conn.execute(
            f"UPDATE seal_import_batches SET {', '.join(f'{f}=?' for f in fields)} WHERE batch_id=?",
            values + [batch_id],
        )
        conn.commit()
    finally:
        conn.close()


def list_batches(db_path: Path | str) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT batch_id, created_at, updated_at, status, source_total, fetched, seals_ok, links_ok, "
            "failed_count, elapsed_s, package_dir, report_path, content_fingerprint, "
            "last_run_kind, last_run_fetched, last_run_skipped, last_run_elapsed_s, last_run_at, "
            "images_ok, images_failed, images_no_source, notes "
            "FROM seal_import_batches ORDER BY batch_id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════ 印谱侧桥接（只读）
def read_item_bridge(item_db_path: Path | None) -> dict[str, str]:
    """**只读**读印谱独立库：返回 `as_book_id → items.source_item_id`（**只 SELECT**，源库零写入）。"""
    bridge: dict[str, str] = {}
    if item_db_path is None or not Path(item_db_path).is_file():
        return bridge
    try:
        conn = sqlite3.connect(str(item_db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        try:
            for r in conn.execute(
                "SELECT as_book_id, source_item_id FROM items WHERE as_book_id IS NOT NULL AND as_book_id<>''"
            ):
                if r["source_item_id"] is not None:
                    bridge[str(r["as_book_id"])] = str(r["source_item_id"])
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        log.warning("读取印谱独立库失败（桥接缺省为空）：%r", exc)
    return bridge


# ═══════════════════════════════════════════════════════════════════════════ 采集主流程
def run_sync(
    *,
    db_path: Path,
    export_root: Path,
    base: str,
    item_db_path: Path | None = None,
    batch_id: str | None = None,
    resume: bool = True,
    delay: float = 0.5,
    limit: int | None = None,
    timeout: float = 30.0,
    page_rows: int = 5000,
    with_detail: bool = False,
    with_graph: bool = False,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """列表（1 次全量 3679）→ **行内字段构建关联** → 归一化 → 落库 → 就绪包。

    * `--with-graph`（默认关）⇒ best-effort 逐枚 `graph/seal/<seqid>` 补 `source_face='seal_graph'` 的链；
    * `--with-detail`（默认关）⇒ best-effort 逐枚 `seal/detail/<seqid>` 补 `seal_ys_ref_id` / `audit_user`；
    * `resume` ⇒ 已入库者跳过；`limit` ⇒ 本轮最多新增取数（分片续跑）。
    """
    ensure_schema(db_path)
    t0 = time.time()

    bridge = read_item_bridge(item_db_path)
    rows, total = fetch_seals_list(base, page_rows=page_rows, timeout=timeout)

    if batch_id is None:
        batch_id = next_batch_id(export_root)
    params = {"resume": resume, "delay": delay, "limit": limit, "page_rows": page_rows,
              "with_detail": with_detail, "with_graph": with_graph}
    prev_row = get_batch(db_path, batch_id) or {}
    create_batch(db_path, batch_id, params, source_total=total)

    failures: list[dict] = []
    detail_unconfirmed: list[dict] = []
    graph_unconfirmed: list[dict] = []
    seals_ok = 0
    links_ok = 0
    skipped = 0
    fetched = 0
    cur_delay = float(delay)

    def _jittered() -> float:
        return max(0.05, cur_delay * (1.0 + random.uniform(-0.25, 0.25)))

    for idx, row in enumerate(rows, start=1):
        seqid = str(row.get("seqid") or "").strip()
        if not seqid:
            failures.append({"source_seal_id": None, "stage": "row", "error": "行缺 seqid"})
            continue
        if resume and seal_exists(db_path, seqid):
            skipped += 1
            seals_ok += 1
            continue
        if limit is not None and fetched >= int(limit):
            break

        detail: dict | None = None
        if with_detail:
            try:
                detail = fetch_seal_detail(base, seqid, timeout=timeout, retries=1)
                fetched += 1
            except FetchError as exc:
                detail_unconfirmed.append({"source_seal_id": seqid, "error": str(exc)})

        graph: dict | None = None
        if with_graph:
            try:
                graph = fetch_seal_graph(base, seqid, timeout=timeout, retries=2)
                fetched += 1
            except FetchError as exc:
                graph_unconfirmed.append({"source_seal_id": seqid, "error": str(exc)})

        try:
            rec = normalize_seal(row, detail)
            rec["raw_json"]["graph"] = graph
            rec_links = merge_links(
                seqid,
                links_from_row(seqid, row, bridge),
                links_from_graph(seqid, graph) if graph else [],
            )
            upsert_seal(db_path, rec, batch_id)
            links_ok += replace_seal_links(db_path, seqid, rec_links, batch_id)
            seals_ok += 1
        except Exception as exc:  # noqa: BLE001
            failures.append({"source_seal_id": seqid, "stage": "store",
                             "error": f"{type(exc).__name__}: {exc}"})

        if with_detail or with_graph:
            time.sleep(_jittered())
        if progress and (idx % 200 == 0 or idx == len(rows)):
            progress({"done": idx, "total": len(rows), "seals_ok": seals_ok,
                      "fetched": fetched, "failed": len(failures)})

    pkg = write_package(db_path=db_path, export_root=export_root, batch_id=batch_id, base=base,
                        source_total=total, params=params, failures=failures, rows_seen=len(rows),
                        item_db_path=item_db_path, with_detail=with_detail, with_graph=with_graph,
                        detail_unconfirmed=detail_unconfirmed, graph_unconfirmed=graph_unconfirmed,
                        images_root=None)

    run_elapsed = round(time.time() - t0, 3)
    is_replay = (len(rows) > 0 and skipped == len(rows) and fetched == 0)
    run_kind = "idempotent_replay" if is_replay else "live_ingest"
    prev_fetched = int(prev_row.get("fetched") or 0)
    prev_elapsed = float(prev_row.get("elapsed_s") or 0.0)
    acq_fetched = prev_fetched if is_replay else prev_fetched + fetched
    acq_elapsed = prev_elapsed if is_replay else prev_elapsed + run_elapsed
    counts = batch_db_counts(db_path, batch_id)
    remaining = total - counts["seals"]
    img = image_status_counts(db_path)

    finish_batch(
        db_path, batch_id, status="DONE", source_total=total,
        fetched=acq_fetched, seals_ok=counts["seals"], links_ok=counts["links"],
        failed_count=len(failures), elapsed_s=round(acq_elapsed, 3),
        package_dir=str(pkg["package_dir"]), report_path=str(pkg["report_path"]),
        content_fingerprint=pkg["fingerprint"],
        last_run_kind=run_kind, last_run_fetched=fetched, last_run_skipped=skipped,
        last_run_elapsed_s=run_elapsed, last_run_at=_now(),
        images_ok=img["ok"], images_failed=img["failed"], images_no_source=img["source_no_image"],
        notes=json.dumps({"skipped_resume": skipped, "run_kind": run_kind,
                          "counters_source": "db_counts(batch_id) + acquisition_run_cumulative"},
                         ensure_ascii=False),
    )
    return {
        "batch_id": batch_id, "run_kind": run_kind, "source_total": total,
        "rows_seen": len(rows), "fetched_requests": fetched,
        "fetched_requests_cumulative": acq_fetched, "skipped_resume": skipped,
        "seals_ok": counts["seals"], "links_ok": counts["links"], "remaining": remaining,
        "failed_count": len(failures), "failures": failures,
        "detail_requests": 0, "detail_unconfirmed_count": len(detail_unconfirmed),
        "graph_unconfirmed_count": len(graph_unconfirmed),
        "package_dir": str(pkg["package_dir"]), "report_path": str(pkg["report_path"]),
        "content_fingerprint": pkg["fingerprint"], "elapsed_s": round(acq_elapsed, 3),
        "last_run_elapsed_s": run_elapsed, "counts": db_counts(db_path),
    }


# ═══════════════════════════════════════════════════════════════════════════ 影像
def image_status_counts(db_path: Path | str) -> dict:
    conn = _connect(db_path)
    try:
        out: dict[str, Any] = {"ok": 0, "failed": 0, "source_no_image": 0}
        for st in (IMG_OK, IMG_FAIL, IMG_NO_SOURCE):
            out[st] = conn.execute("SELECT COUNT(*) FROM seal_images WHERE status=?", (st,)).fetchone()[0]
        out["total"] = conn.execute("SELECT COUNT(*) FROM seal_images").fetchone()[0]
        # 子因分解（NaN_ ref / 持久 HTTP 500）——同归 source_no_image，但分开记
        out["source_no_image_by_reason"] = {
            r[0] or "(unset)": r[1]
            for r in conn.execute(
                "SELECT no_source_reason, COUNT(*) FROM seal_images WHERE status=? "
                "GROUP BY no_source_reason ORDER BY no_source_reason", (IMG_NO_SOURCE,))
        }
        return out
    finally:
        conn.close()


def image_kind_status(db_path: Path | str) -> dict:
    """按 kind 分解的影像状态计数（目标/成功/失败/源侧无图 ＋ 源侧无图子因分解）。"""
    conn = _connect(db_path)
    try:
        out: dict[str, dict] = {k: {"target": 0, "ok": 0, "failed": 0, "source_no_image": 0,
                                    "source_no_image_by_reason": {}} for k in IMAGE_KINDS}
        for r in conn.execute(
            "SELECT kind, status, COUNT(*) c FROM seal_images GROUP BY kind, status"
        ):
            k = r["kind"]
            if k not in out:
                out[k] = {"target": 0, "ok": 0, "failed": 0, "source_no_image": 0,
                          "source_no_image_by_reason": {}}
            out[k][r["status"]] = r["c"]
            out[k]["target"] += r["c"]
        for r in conn.execute(
            "SELECT kind, no_source_reason, COUNT(*) c FROM seal_images WHERE status=? "
            "GROUP BY kind, no_source_reason", (IMG_NO_SOURCE,)
        ):
            k = r["kind"]
            if k in out:
                out[k]["source_no_image_by_reason"][r["no_source_reason"] or "(unset)"] = r["c"]
        return out
    finally:
        conn.close()


def collect_image_refs(db_path: Path | str) -> list[tuple[str, str, str]]:
    """从 `seals` 表汇集全部影像 ref：[(seqid, kind, ref)]（ref 非空者）。"""
    conn = _connect(db_path)
    try:
        out: list[tuple[str, str, str]] = []
        cols = {k: IMAGE_SRC_COL[k] for k in IMAGE_KINDS}
        sel = ", ".join(["source_seal_id"] + list(cols.values()))
        for r in conn.execute(f"SELECT {sel} FROM seals ORDER BY source_seal_id"):
            seqid = r["source_seal_id"]
            for kind, col in cols.items():
                ref = r[col]
                if ref:
                    out.append((str(seqid), kind, str(ref)))
        return out
    finally:
        conn.close()


def image_ledger_get(db_path: Path | str, seqid: str, kind: str) -> dict | None:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM seal_images WHERE seqid=? AND kind=?", (seqid, kind)).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def image_ledger_put(db_path: Path | str, rec: dict) -> None:
    cols = [c for c in IMAGE_FIELDS if c not in ("seqid", "kind")]
    all_cols = ["seqid", "kind"] + cols + ["updated_at"]
    placeholders = ", ".join("?" for _ in all_cols)
    update = ", ".join(f"{c}=excluded.{c}" for c in cols) + ", updated_at=excluded.updated_at"
    vals = [rec.get("seqid"), rec.get("kind")] + [_coerce_img(c, rec.get(c)) for c in cols] + [_now()]
    conn = _connect(db_path)
    try:
        conn.execute(
            f"INSERT INTO seal_images ({', '.join(all_cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT(seqid, kind) DO UPDATE SET {update}",
            vals,
        )
        conn.commit()
    finally:
        conn.close()


def _coerce_img(col: str, v: Any) -> Any:
    if col in ("bytes", "tiff_bytes", "width", "height", "upscaled"):
        return v if v is None else int(v)
    return v


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_image_bytes(url: str, *, timeout: float = 30.0) -> tuple[bytes, str]:
    """取一张影像（**跟跳转**：urllib 默认跟随 302）。返回 (bytes, content_type)。

    非 200 / 非 image 一律抛 `FetchError`；429 ⇒ `RateLimited`。
    """
    req = urllib.request.Request(url, headers={"Accept": "image/*", "User-Agent": "feicui-seal-ingest/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            ctype = resp.headers.get("Content-Type") or ""
            data = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise RateLimited(f"HTTP 429 {url}") from exc
        if 500 <= exc.code < 600:
            raise ServerUnavailable(f"HTTP {exc.code} {url}", status=exc.code) from exc
        raise FetchError(f"HTTP {exc.code} {url}") from exc
    except Exception as exc:
        raise FetchError(f"{type(exc).__name__}: {exc} @ {url}") from exc
    if status != 200:
        raise FetchError(f"HTTP {status} {url}")
    if img_kind_from_content_type(ctype) is None:
        raise FetchError(f"非影像响应 Content-Type={ctype!r} @ {url}")
    return data, ctype


def img_kind_from_content_type(ctype: str) -> str | None:
    c = (ctype or "").lower()
    if "jpeg" in c or "jpg" in c:
        return "jpeg"
    if "png" in c:
        return "png"
    if "webp" in c:
        return "webp"
    return None


def image_local_path(images_root: Path, kind: str, seqid: str) -> Path:
    return Path(images_root) / kind / f"{seqid}.jpg"


def jpeg_size(path: Path) -> tuple[int | None, int | None]:
    """纯 stdlib 解析 JPEG 宽高（扫 SOF 标记）。失败 ⇒ (None, None)。"""
    try:
        with Path(path).open("rb") as fh:
            data = fh.read()
        if len(data) < 4 or data[0:2] != b"\xff\xd8":
            return None, None
        i = 2
        n = len(data)
        while i < n - 1:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0xD9, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            if i + 4 > n:
                break
            seglen = (data[i + 2] << 8) | data[i + 3]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB,
                          0xCD, 0xCE, 0xCF):
                if i + 9 > n:
                    break
                height = (data[i + 5] << 8) | data[i + 6]
                width = (data[i + 7] << 8) | data[i + 8]
                return width, height
            i += 2 + seglen
        return None, None
    except Exception:
        return None, None


NO_IMAGE_PREFIXES = ("NaN_",)


def _is_source_no_image(ref: str) -> bool:
    return any(ref.startswith(p) for p in NO_IMAGE_PREFIXES)


# ── 源侧缺图 / 坏图清单（按 子因 / ref 前缀 / kind 聚合 ＋ 计数 ＋ 样例 seqid）───────────────
def _ref_prefix(ref: str | None) -> str:
    """ref 前缀：`62_3894_1` ⇒ `62`；`11_1203_2` ⇒ `11`；非数字前缀原样返回。"""
    head = str(ref or "").split("_", 1)[0]
    return head or "(empty)"


def _no_source_reason_of(rec: dict) -> str:
    r = rec.get("no_source_reason")
    if r in (NO_SOURCE_NAN_REF, NO_SOURCE_HTTP_500, NO_SOURCE_BAD_BYTES):
        return r
    ref = str(rec.get("source_ref") or "")
    return NO_SOURCE_NAN_REF if _is_source_no_image(ref) else NO_SOURCE_HTTP_500


def source_no_image_rows(db_path: Path | str) -> list[dict]:
    """取全部 `source_no_image` 行（含子因 / ref / 错误）。"""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT seqid, kind, source_ref, source_url, error, no_source_reason "
            "FROM seal_images WHERE status=? ORDER BY kind, source_ref",
            (IMG_NO_SOURCE,)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def build_source_missing_summary(db_path: Path | str, *, sample_per_group: int = 5) -> dict:
    """源侧缺图 / 坏图清单：**按子因 / ref 前缀 / kind** 聚合 ＋ 计数 ＋ 样例 seqid（进 report.json 与证据）。"""
    rows = source_no_image_rows(db_path)
    by_reason: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    groups: dict[tuple, dict] = {}
    for r in rows:
        reason = _no_source_reason_of(r)
        kind = str(r.get("kind") or "?")
        prefix = _ref_prefix(r.get("source_ref"))
        by_reason[reason] = by_reason.get(reason, 0) + 1
        by_kind[kind] = by_kind.get(kind, 0) + 1
        g = groups.setdefault((kind, prefix, reason), {"kind": kind, "prefix": prefix, "reason": reason,
                                                       "count": 0, "sample_seqids": []})
        g["count"] += 1
        if len(g["sample_seqids"]) < sample_per_group:
            g["sample_seqids"].append(r.get("seqid"))
    by_prefix = sorted(groups.values(),
                       key=lambda g: (g["kind"], _prefix_sort_key(g["prefix"]), g["reason"]))
    return {
        "total": len(rows),
        "by_reason": {k: by_reason[k] for k in sorted(by_reason)},
        "by_reason_note": {k: NO_SOURCE_REASON_NOTE.get(k, "") for k in by_reason},
        "by_kind": by_kind,
        "by_prefix": by_prefix,
        "rows": rows,
    }


def _prefix_sort_key(p: str):
    s = str(p)
    return (0, int(s), "") if s.isdigit() else (1, 0, s)


# ── TIFF 容器转换（JPEG → TIFF 无损容器；供 xiai 影像库）─────────────────────────────────
def tiff_container_ok(path: Path) -> bool:
    """TIFF 容器魔数判据（`II*\\0` / `MM\\0*`；**与 xiai `codec.py` 同口径**）。"""
    try:
        with Path(path).open("rb") as fh:
            head = fh.read(4)
    except Exception:
        return False
    return head == TIFF_MAGIC_LE or head == TIFF_MAGIC_BE


def tiff_path_for(tiff_dir: Path, sha256: str) -> Path:
    """内容寻址路径形状 ＝ `<tiff_dir>/<sha256[:2]>/<sha256>.tiff`（**镜像 xiai 影像库**）。"""
    return Path(tiff_dir) / sha256[:2] / f"{sha256}.tiff"


def is_undecodable_image_error(exc: BaseException) -> bool:
    """Pillow 无法识别/解码正文 ⇒ True（**源侧坏字节**；持久复现，非限流/非瞬时）。

    典型：iipsrv 把自身响应头当正文吐出 ⇒ HTTP 200 ＋ `image/jpeg` 但正文非 JPEG
    ⇒ `Image.open` 抛 `UnidentifiedImageError('cannot identify image file …')`。
    """
    try:
        from PIL import UnidentifiedImageError  # 延迟导入（Pillow 为运行期依赖）
        if isinstance(exc, UnidentifiedImageError):
            return True
    except Exception:  # noqa: BLE001
        pass
    msg = str(exc)
    return ("cannot identify image file" in msg) or ("UnidentifiedImageError" in msg)


def convert_jpeg_to_tiff(jpeg_path: Path, tiff_dir: Path) -> dict:
    """JPEG → TIFF **无损容器转换**：解码 RAW JPEG 像素 → 原样装进 TIFF（**不重采样、不二次有损编码**）。

    TIFF 用 RGB；压缩 `tiff_deflate`（**无损**）。返回 sha256 ＝ **TIFF 字节**的 sha256（内容寻址键）。
    Pillow 为运行期依赖（`server/.venv/bin/pip install pillow`）——**延迟导入**，缺则明确报错。
    """
    try:
        from PIL import Image
    except Exception as exc:  # noqa: BLE001
        raise FetchError(f"缺少 Pillow（请 `server/.venv/bin/pip install pillow`）：{exc}") from exc
    with Image.open(jpeg_path) as im:
        rgb = im.convert("RGB")            # JPEG 已是 RGB ⇒ 无损直通；不缩放、不重采样
        w, h = rgb.size
        tdir = Path(tiff_dir)
        tdir.mkdir(parents=True, exist_ok=True)
        buf = tdir / f".convert-{os.getpid()}-{random.randint(0, 1 << 30)}.part"
        rgb.save(buf, format="TIFF", compression="tiff_deflate")
    data = buf.read_bytes()
    buf.unlink(missing_ok=True)
    sha = hashlib.sha256(data).hexdigest()
    out = tiff_path_for(tiff_dir, sha)
    if not out.is_file():
        out.parent.mkdir(parents=True, exist_ok=True)
        part = out.with_suffix(".part")
        part.write_bytes(data)
        os.replace(part, out)
    if not tiff_container_ok(out):
        raise FetchError(f"TIFF 魔数校验失败：{out}")
    return {"tiff_path": str(out), "tiff_sha256": sha, "tiff_bytes": len(data), "width": w, "height": h}


def _tiff_ready(prev: dict | None, tiff_dir: Path | None) -> bool:
    if not prev or not tiff_dir:
        return False
    sha = prev.get("tiff_sha256")
    if not sha:
        return False
    p = tiff_path_for(tiff_dir, sha)
    return p.is_file() and sha256_file(p) == sha


def convert_missing_tiffs(*, db_path: Path | str, images_root: Path, tiff_dir: Path,
                          limit: int | None = None,
                          progress: Callable[[dict], None] | None = None) -> dict:
    """把已下载的 JPEG 源缓存补转 TIFF（**不联网、不重下**）——口径变更后的补转入口。

    已存在且 sha256 一致的 TIFF ⇒ 跳过（可续跑）。
    """
    ensure_schema(db_path)
    Path(tiff_dir).mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    try:
        recs = conn.execute(
            "SELECT seqid, kind, local_path, tiff_sha256 FROM seal_images WHERE status='ok'"
        ).fetchall()
    finally:
        conn.close()
    done = converted = skipped = missing = failed = 0
    failures: list[dict] = []
    for r in recs:
        if limit is not None and done >= int(limit):
            break
        if _tiff_ready({"tiff_sha256": r["tiff_sha256"]}, Path(tiff_dir)):
            skipped += 1
            done += 1
            continue
        jpeg = Path(r["local_path"]) if r["local_path"] else (Path(images_root) / r["kind"] / f"{r['seqid']}.jpg")
        if not jpeg.is_file():
            missing += 1
            done += 1
            continue
        try:
            tinfo = convert_jpeg_to_tiff(jpeg, Path(tiff_dir))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            failures.append({"seqid": r["seqid"], "kind": r["kind"], "error": str(exc)})
            done += 1
            continue
        full = image_ledger_get(db_path, r["seqid"], r["kind"]) or {}
        full.update(tinfo)
        full["status"] = IMG_OK
        full["error"] = None
        image_ledger_put(db_path, full)
        converted += 1
        done += 1
        if progress and (done % 200 == 0):
            progress({"done": done, "total": len(recs), "converted": converted, "failed": failed})
    return {"total": len(recs), "done": done, "converted": converted, "skipped": skipped,
            "missing": missing, "failed": failed, "failures": failures}


def _fetch_convert_one(seqid: str, kind: str, ref: str, jpeg_path: Path, url: str,
                       tiff_dir: Path | None, convert: bool, timeout: float,
                       delay: float) -> dict:
    """工作线程体：**纯 I/O ＋ 转换，不碰 DB**（DB 写入一律回主线程）。

    含内联 429 指数退避（每个 worker 自节流）。返回结构化结果给主线程落台账。
    """
    rl_attempt = 0
    sv_attempt = 0
    while True:
        try:
            data, ctype = fetch_image_bytes(url, timeout=timeout)
            break
        except RateLimited as exc:
            rl_attempt += 1
            if rl_attempt > RL_MAX_ATTEMPTS:
                return {"seqid": seqid, "kind": kind, "ref": ref, "url": url,
                        "status": "rate_limited", "error": str(exc)}
            time.sleep(min(RL_COOLDOWN_BASE * (2 ** (rl_attempt - 1)), RL_COOLDOWN_MAX))
        except ServerUnavailable as exc:
            # 源侧 5xx（坏图）：3 轮 2/8/30s 退避后仍失败 ⇒ 判「源侧无图（坏图）」交主线程落 source_no_image
            if sv_attempt >= len(SERVER_RETRY_BACKOFFS):
                return {"seqid": seqid, "kind": kind, "ref": ref, "url": url,
                        "status": "no_source_500", "error": f"HTTP {exc.status or 500}"}
            time.sleep(SERVER_RETRY_BACKOFFS[sv_attempt])
            sv_attempt += 1
        except FetchError as exc:
            return {"seqid": seqid, "kind": kind, "ref": ref, "url": url,
                    "status": "fail", "error": str(exc)}
    try:
        tmp = jpeg_path.with_suffix(".part")
        tmp.write_bytes(data)
        digest = sha256_file(tmp)
        os.replace(tmp, jpeg_path)
    except Exception as exc:  # noqa: BLE001
        return {"seqid": seqid, "kind": kind, "ref": ref, "url": url,
                "status": "fail", "error": f"write: {type(exc).__name__}: {exc}"}
    tinfo: dict | None = None
    if convert and tiff_dir:
        try:
            tinfo = convert_jpeg_to_tiff(jpeg_path, tiff_dir)
        except Exception as exc:  # noqa: BLE001
            if is_undecodable_image_error(exc):
                # 源侧坏字节（HTTP 200 image/jpeg 但不可解码）⇒ 归 source_no_image 子因 bad_bytes（**非采集失败**）
                return {"seqid": seqid, "kind": kind, "ref": ref, "url": url,
                        "status": "bad_bytes",
                        "error": f"HTTP 200 {ctype} but undecodable ({len(data)}B)",
                        "jpeg_bytes": len(data), "jpeg_sha256": digest}
            return {"seqid": seqid, "kind": kind, "ref": ref, "url": url,
                    "status": "convert_fail", "error": f"tiff_convert: {exc}",
                    "jpeg_bytes": len(data), "jpeg_sha256": digest}
    if delay > 0:
        time.sleep(delay)
    return {"seqid": seqid, "kind": kind, "ref": ref, "url": url, "status": "ok",
            "jpeg_bytes": len(data), "jpeg_sha256": digest, "tinfo": tinfo}


def download_images_threaded(
    *,
    db_path: Path,
    images_root: Path,
    base: str,
    kinds: tuple[str, ...] = IMAGE_KINDS,
    resume: bool = True,
    delay: float = 0.3,
    workers: int = 4,
    limit: int | None = None,
    timeout: float = 30.0,
    progress: Callable[[dict], None] | None = None,
    batch_id: str | None = None,
    tiff_dir: Path | None = None,
    convert: bool = True,
) -> dict:
    """影像全量下载（**有界并发**；pilot 实测 w=4 ⇒ ~6.3 img/s、无 429）。

    **DB 写入一律回主线程**（worker 只做取图 ＋ 转换）；断点续跑口径与串行版一致。
    """
    import concurrent.futures as cf

    ensure_schema(db_path)
    Path(images_root).mkdir(parents=True, exist_ok=True)
    for k in kinds:
        (Path(images_root) / k).mkdir(parents=True, exist_ok=True)
    if convert and tiff_dir:
        Path(tiff_dir).mkdir(parents=True, exist_ok=True)

    refs = [(s, k, r) for (s, k, r) in collect_image_refs(db_path) if k in kinds]

    # 预读台账（快）
    ledger: dict[tuple, dict] = {}
    conn = _connect(db_path)
    try:
        for r in conn.execute("SELECT seqid, kind, sha256, tiff_sha256, status, local_path, "
                              "no_source_reason FROM seal_images"):
            ledger[(r["seqid"], r["kind"])] = dict(r)
    finally:
        conn.close()

    t0 = time.time()
    done = ok = failed = no_src = skipped = conv_failed = 0
    failures: list[dict] = []
    _missing: list[dict] = []   # 源侧坏图（持久 500）清单
    _bad_bytes: list[dict] = []  # 源侧坏字节（HTTP 200 但不可解码）清单
    queue: list[tuple] = []

    for (seqid, kind, ref) in refs:
        path = image_local_path(images_root, kind, seqid)
        if _is_source_no_image(ref):
            image_ledger_put(db_path, {
                "seqid": seqid, "kind": kind, "source_ref": ref,
                "source_url": image_url(base, ref), "local_path": None,
                "bytes": None, "sha256": None, "status": IMG_NO_SOURCE,
                "no_source_reason": NO_SOURCE_NAN_REF,
                "error": "源侧无图（ref 以 NaN_ 开头）",
            })
            no_src += 1
            done += 1
            continue
        prev = ledger.get((seqid, kind))
        # 源侧坏图（有界重试后仍 500）⇒ **终态**；resume 不重取（按 ref 恒定，非限流）
        if resume and prev and prev.get("status") == IMG_NO_SOURCE:
            no_src += 1
            skipped += 1
            done += 1
            continue
        if (resume and prev and prev.get("status") == IMG_OK and path.is_file()
                and prev.get("sha256") and sha256_file(path) == prev.get("sha256")
                and (not convert or _tiff_ready(prev, tiff_dir))):
            ok += 1
            skipped += 1
            done += 1
            continue
        queue.append((seqid, kind, ref, path))
        if limit is not None and len(queue) >= int(limit):
            break  # 分片：本片最多处理 N 个「待取」ref（resume 跳过的不计入）

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fetch_convert_one, s, k, rf, path, image_url(base, rf),
                          tiff_dir, convert, timeout, delay): (s, k, rf)
                for (s, k, rf, path) in queue}
        for fut in cf.as_completed(futs):
            res = fut.result()
            seqid, kind, ref = res["seqid"], res["kind"], res["ref"]
            url = res["url"]
            upscaled = int("!" in url)
            if res["status"] == "ok":
                image_ledger_put(db_path, {
                    "seqid": seqid, "kind": kind, "source_ref": ref, "source_url": url,
                    "local_path": str(image_local_path(images_root, kind, seqid)),
                    "bytes": res["jpeg_bytes"], "sha256": res["jpeg_sha256"],
                    "status": IMG_OK, "error": None, **(res.get("tinfo") or {}),
                    "upscaled": upscaled,
                })
                ok += 1
            elif res["status"] == "convert_fail":
                conv_failed += 1
                image_ledger_put(db_path, {
                    "seqid": seqid, "kind": kind, "source_ref": ref, "source_url": url,
                    "local_path": str(image_local_path(images_root, kind, seqid)),
                    "bytes": res.get("jpeg_bytes"), "sha256": res.get("jpeg_sha256"),
                    "status": IMG_FAIL, "error": res["error"], "upscaled": upscaled,
                })
                failures.append({"seqid": seqid, "kind": kind, "ref": ref, "error": res["error"]})
                failed += 1
            elif res["status"] == "no_source_500":
                # 有界重试后仍 500 ⇒ 「源侧坏图」：落 source_no_image（**不计入 failed**），子因 http_500
                image_ledger_put(db_path, {
                    "seqid": seqid, "kind": kind, "source_ref": ref, "source_url": url,
                    "local_path": None, "bytes": None, "sha256": None,
                    "status": IMG_NO_SOURCE, "no_source_reason": NO_SOURCE_HTTP_500,
                    "error": res["error"],
                })
                no_src += 1
                _missing.append({"seqid": seqid, "kind": kind, "ref": ref, "error": res["error"]})
            elif res["status"] == "bad_bytes":
                # 源侧坏字节（HTTP 200 image/jpeg 但不可解码）⇒ 落 source_no_image 子因 bad_bytes（**不计入 failed**）
                image_ledger_put(db_path, {
                    "seqid": seqid, "kind": kind, "source_ref": ref, "source_url": url,
                    "local_path": None, "bytes": None, "sha256": None,
                    "status": IMG_NO_SOURCE, "no_source_reason": NO_SOURCE_BAD_BYTES,
                    "error": res["error"],
                })
                no_src += 1
                _bad_bytes.append({"seqid": seqid, "kind": kind, "ref": ref, "error": res["error"]})
            else:
                image_ledger_put(db_path, {
                    "seqid": seqid, "kind": kind, "source_ref": ref, "source_url": url,
                    "local_path": None, "bytes": None, "sha256": None,
                    "status": IMG_FAIL, "error": res["error"],
                })
                failures.append({"seqid": seqid, "kind": kind, "ref": ref, "error": res["error"]})
                failed += 1
            done += 1
            if progress and done % 200 == 0:
                progress({"done": done, "total": len(refs), "ok": ok, "skipped": skipped,
                          "failed": failed, "no_source": no_src})

    elapsed = round(time.time() - t0, 3)
    status = image_status_counts(db_path)
    if batch_id:
        finish_batch(db_path, batch_id, images_ok=status["ok"], images_failed=status["failed"],
                     images_no_source=status["source_no_image"])
    return {
        "total_refs": len(refs), "done": done, "ok": ok, "skipped_resume": skipped,
        "no_source": no_src, "convert_failed": conv_failed,
        "no_source_500": len(_missing), "no_source_bad_bytes": len(_bad_bytes),
        "workers": workers, "elapsed_s": elapsed,
        "rate": round(done / elapsed, 2) if elapsed else None,
        "status_counts": status, "failures": failures,
        "source_missing": _missing, "bad_bytes": _bad_bytes,
        "images_root": str(images_root), "tiff_dir": str(tiff_dir) if tiff_dir else None,
    }


def download_images(
    *,
    db_path: Path,
    images_root: Path,
    base: str,
    kinds: tuple[str, ...] = IMAGE_KINDS,
    resume: bool = True,
    delay: float = 0.2,
    limit: int | None = None,
    timeout: float = 30.0,
    progress: Callable[[dict], None] | None = None,
    batch_id: str | None = None,
    tiff_dir: Path | None = None,
    convert: bool = True,
) -> dict:
    """影像全量下载（**可续跑 / 分片 / 失败清单 / 429 指数退避**）＋ JPEG→TIFF 无损容器转换。

    * 落 `images_root/<kind>/<seqid>.jpg` 作**源缓存**；再转 TIFF 落
      `tiff_dir/<sha256[:2]>/<sha256>.tiff`（内容寻址；供 xiai 影像库）；
    * 台账写 jpeg sha256/bytes ＋ tiff sha256/bytes/size/upscaled/status；
    * 跳过**已存在且 sha256 一致**者（resume）；
    * `NaN_` 开头 ref ⇒ 登记 `source_no_image`（**非失败**）；
    * 失败进 `seal_images`（status='failed'）**可重跑**，绝不静默跳过。

    **只用原生裁切**：取图 URL 不含 `!w,h` 放大参数（IIPImage 上采样会失真，禁用）。
    """
    ensure_schema(db_path)
    Path(images_root).mkdir(parents=True, exist_ok=True)
    for k in kinds:
        (Path(images_root) / k).mkdir(parents=True, exist_ok=True)
    if convert and tiff_dir:
        Path(tiff_dir).mkdir(parents=True, exist_ok=True)

    refs = [(s, k, r) for (s, k, r) in collect_image_refs(db_path) if k in kinds]

    t0 = time.time()
    done = ok = failed = no_src = skipped = conv_failed = 0
    failures: list[dict] = []
    _missing: list[dict] = []   # 源侧坏图（持久 500）清单
    _bad_bytes: list[dict] = []  # 源侧坏字节（HTTP 200 但不可解码）清单
    rl_events = 0
    cur_delay = float(delay)

    for (seqid, kind, ref) in refs:
        if limit is not None and done >= int(limit):
            break
        path = image_local_path(images_root, kind, seqid)
        prev = image_ledger_get(db_path, seqid, kind)

        if _is_source_no_image(ref):
            # 源侧无图（NaN_ 前缀）⇒ 登记，非失败
            image_ledger_put(db_path, {
                "seqid": seqid, "kind": kind, "source_ref": ref,
                "source_url": image_url(base, ref), "local_path": None,
                "bytes": None, "sha256": None, "status": IMG_NO_SOURCE,
                "no_source_reason": NO_SOURCE_NAN_REF,
                "error": "源侧无图（ref 以 NaN_ 开头）",
            })
            no_src += 1
            done += 1
            continue

        # 源侧坏图（有界重试后仍 500）⇒ 终态；resume 不重取
        if resume and prev and prev.get("status") == IMG_NO_SOURCE:
            no_src += 1
            skipped += 1
            done += 1
            continue

        # 断点续跑：JPEG 与 TIFF 都在（且一致）⇒ 跳过
        if (resume and prev and prev.get("status") == IMG_OK and path.is_file()
                and prev.get("sha256") and sha256_file(path) == prev.get("sha256")
                and (not convert or _tiff_ready(prev, tiff_dir))):
            ok += 1
            skipped += 1
            done += 1
            continue

        url = image_url(base, ref)
        data: bytes | None = None
        jpeg_ready = bool(resume and path.is_file() and prev and prev.get("sha256")
                          and sha256_file(path) == prev.get("sha256"))
        if not jpeg_ready:
            rl_attempt = 0
            sv_attempt = 0
            while True:
                try:
                    data, ctype = fetch_image_bytes(url, timeout=timeout)
                    break
                except RateLimited as exc:
                    rl_attempt += 1
                    rl_events += 1
                    if rl_attempt > RL_MAX_ATTEMPTS:
                        image_ledger_put(db_path, {
                            "seqid": seqid, "kind": kind, "source_ref": ref, "source_url": url,
                            "local_path": None, "bytes": None, "sha256": None,
                            "status": IMG_FAIL, "error": f"rate_limited: {exc}",
                        })
                        failures.append({"seqid": seqid, "kind": kind, "ref": ref, "error": str(exc)})
                        failed += 1
                        data = None
                        break
                    pause = min(RL_COOLDOWN_BASE * (2 ** (rl_attempt - 1)), RL_COOLDOWN_MAX)
                    cur_delay = min(cur_delay * RL_DELAY_GROWTH, RL_DELAY_MAX)
                    log.warning("影像限速（第 %d 次）：冷却 %.1fs 后重试 %s（稳态间隔→%.2fs）",
                                rl_attempt, pause, seqid, cur_delay)
                    time.sleep(pause)
                except ServerUnavailable as exc:
                    # 源侧 5xx（坏图）：3 轮 2/8/30s 退避后仍失败 ⇒ 判「源侧无图（坏图）」，**不计入 failed**
                    if sv_attempt >= len(SERVER_RETRY_BACKOFFS):
                        err = f"HTTP {exc.status or 500}"
                        image_ledger_put(db_path, {
                            "seqid": seqid, "kind": kind, "source_ref": ref, "source_url": url,
                            "local_path": None, "bytes": None, "sha256": None,
                            "status": IMG_NO_SOURCE, "no_source_reason": NO_SOURCE_HTTP_500,
                            "error": err,
                        })
                        _missing.append({"seqid": seqid, "kind": kind, "ref": ref, "error": err})
                        no_src += 1
                        data = None
                        break
                    time.sleep(SERVER_RETRY_BACKOFFS[sv_attempt])
                    sv_attempt += 1
                except FetchError as exc:
                    image_ledger_put(db_path, {
                        "seqid": seqid, "kind": kind, "source_ref": ref, "source_url": url,
                        "local_path": None, "bytes": None, "sha256": None,
                        "status": IMG_FAIL, "error": str(exc),
                    })
                    failures.append({"seqid": seqid, "kind": kind, "ref": ref, "error": str(exc)})
                    failed += 1
                    data = None
                    break
            if data is None:
                done += 1
                continue
            try:
                tmp = path.with_suffix(".part")
                tmp.write_bytes(data)
                digest = sha256_file(tmp)
                os.replace(tmp, path)
            except Exception as exc:  # noqa: BLE001
                image_ledger_put(db_path, {
                    "seqid": seqid, "kind": kind, "source_ref": ref, "source_url": url,
                    "local_path": None, "bytes": None, "sha256": None,
                    "status": IMG_FAIL, "error": f"write: {type(exc).__name__}: {exc}",
                })
                failures.append({"seqid": seqid, "kind": kind, "ref": ref, "error": f"write: {exc}"})
                failed += 1
                done += 1
                continue
        else:
            digest = sha256_file(path)
            data = b""  # 已有 JPEG，跳过下载

        # ── TIFF 无损容器转换（缺 Pillow / 转换失败 ⇒ 记 failed，不进 ok）；源侧坏字节单列 ──
        tinfo: dict | None = None
        if convert and tiff_dir:
            try:
                tinfo = convert_jpeg_to_tiff(path, tiff_dir)
            except Exception as exc:  # noqa: BLE001
                if is_undecodable_image_error(exc):
                    # 源侧坏字节（HTTP 200 image/jpeg 但不可解码）⇒ 落 source_no_image 子因 bad_bytes（**不计入 failed**）
                    try:
                        nb = path.stat().st_size
                    except OSError:
                        nb = len(data)
                    berr = f"HTTP 200 image/jpeg but undecodable ({nb}B)"
                    image_ledger_put(db_path, {
                        "seqid": seqid, "kind": kind, "source_ref": ref, "source_url": url,
                        "local_path": None, "bytes": None, "sha256": None,
                        "status": IMG_NO_SOURCE, "no_source_reason": NO_SOURCE_BAD_BYTES,
                        "error": berr,
                    })
                    _bad_bytes.append({"seqid": seqid, "kind": kind, "ref": ref, "error": berr})
                    no_src += 1
                    done += 1
                    continue
                conv_failed += 1
                image_ledger_put(db_path, {
                    "seqid": seqid, "kind": kind, "source_ref": ref, "source_url": url,
                    "local_path": str(path), "bytes": len(data), "sha256": digest,
                    "status": IMG_FAIL, "error": f"tiff_convert: {type(exc).__name__}: {exc}",
                    "upscaled": int("!" in url),
                })
                failures.append({"seqid": seqid, "kind": kind, "ref": ref, "error": f"tiff_convert: {exc}"})
                failed += 1
                done += 1
                continue

        upscaled = int("!" in url)
        image_ledger_put(db_path, {
            "seqid": seqid, "kind": kind, "source_ref": ref, "source_url": url,
            "local_path": str(path), "bytes": len(data), "sha256": digest,
            "status": IMG_OK, "error": None,
            **(tinfo or {}),
            "upscaled": upscaled,
        })
        ok += 1
        done += 1

        if not jpeg_ready and cur_delay > 0:
            time.sleep(max(0.0, cur_delay * (1.0 + random.uniform(-0.25, 0.25))))
        if progress and (done % 200 == 0 or done == len(refs)):
            progress({"done": done, "total": len(refs), "ok": ok, "skipped": skipped,
                      "failed": failed, "no_source": no_src})

    elapsed = round(time.time() - t0, 3)
    status = image_status_counts(db_path)
    if batch_id:
        finish_batch(db_path, batch_id, images_ok=status["ok"], images_failed=status["failed"],
                     images_no_source=status["source_no_image"])
    return {
        "total_refs": len(refs), "done": done, "ok": ok, "skipped_resume": skipped,
        "failed": failed, "no_source": no_src, "convert_failed": conv_failed,
        "rate_limit_events": rl_events, "no_source_500": len(_missing),
        "no_source_bad_bytes": len(_bad_bytes),
        "elapsed_s": elapsed, "rate": round(done / elapsed, 2) if elapsed else None,
        "status_counts": status, "failures": failures,
        "source_missing": _missing, "bad_bytes": _bad_bytes,
        "images_root": str(images_root), "tiff_dir": str(tiff_dir) if tiff_dir else None,
    }


# ═══════════════════════════════════════════════════════════════════════════ 就绪包
FIELD_DICT: list[dict] = [
    {"name": "source_seal_id", "source": "seqid", "type": "string", "role": "idempotency_key",
     "note": "内部键（detail/graph 路径参数）；幂等键，原样字符串"},
    {"name": "seal_uri", "source": "sealUri", "type": "string", "note": "GUID"},
    {"name": "category", "source": "sealFl", "type": "string", "note": "分类（恒「印章」）"},
    {"name": "seal_wen", "source": "sealYwSmwz", "type": "string", "note": "印文释文（繁体为正字段）"},
    {"name": "seal_wen_chs", "source": "sealYwSmwzChs", "type": "string", "note": "印文释文简体副字段"},
    {"name": "seal_wen_pinyin", "source": "sealYwSwpy", "type": "string|null", "note": "印文拼音"},
    {"name": "seal_wen_wzly", "source": "sealYwWzly", "type": "string|null", "note": "文字来源（繁）"},
    {"name": "seal_wen_wzly_chs", "source": "sealYwWzlyChs", "type": "string|null", "note": "文字来源（简）"},
    {"name": "seal_wen_yssw", "source": "sealYwYssw", "type": "string|null", "note": "印文·（繁）"},
    {"name": "seal_wen_yssw_chs", "source": "sealYwYsswChs", "type": "string|null", "note": "印文·（简）"},
    {"name": "seal_wen_wyz", "source": "sealYwWwyz", "type": "string|null", "note": "文字·"},
    {"name": "seal_wen_zjsw", "source": "sealYwZjsw", "type": "string|null", "note": "篆刻释文（繁）"},
    {"name": "seal_wen_zjsw_chs", "source": "sealYwZjswChs", "type": "string|null", "note": "篆刻释文（简）"},
    {"name": "seal_ys_xz", "source": "sealYsXz", "type": "integer|null",
     "note": "形製码 1..10；**null 合法（实测 644 行）**，不得当采集失败"},
    {"name": "seal_ys_label", "source": "派生 SEAL_YS_XZ_LOOKUP[sealYsXz]", "type": "string|null",
     "note": "形製可读值（纯函数派生，见 manifest.seal_ys_lookup）"},
    {"name": "seal_ys_kf", "source": "sealYsKf", "type": "string|null", "note": "—"},
    {"name": "seal_ys_st", "source": "sealYsSt", "type": "string|null", "note": "—"},
    {"name": "seal_zyz", "source": "sealZyz", "type": "string|null", "note": "主印主标志（3679）"},
    {"name": "seal_yz", "source": "sealYz", "type": "string|null",
     "note": "印主 person id（2379；与 persons.source_person_id 同域）"},
    {"name": "seal_yz_person_name", "source": "sealYzPersonName", "type": "string|null", "note": "印主姓名（繁）"},
    {"name": "seal_yz_person_name_chs", "source": "sealYzPersonNameChs", "type": "string|null", "note": "印主姓名（简）"},
    {"name": "seal_yz_name", "source": "sealYzName", "type": "string|null", "note": "实测全 null"},
    {"name": "seal_yz_ref_id", "source": "sealYzRefId", "type": "string|null",
     "note": "**detail 独有**；detail 默认关 ⇒ 默认 null"},
    {"name": "seal_yzzkz", "source": "sealYzzkz", "type": "string|null", "note": "篆者名（繁）"},
    {"name": "seal_yzzkz_chs", "source": "sealYzzkzChs", "type": "string|null", "note": "篆者名（简）"},
    {"name": "seal_yzzkz_id", "source": "sealYzzkzId", "type": "string|null",
     "note": "篆者 person id（2652）/ 10 个值"},
    {"name": "seal_bk", "source": "sealBk", "type": "string|null", "note": "边款（459，繁）"},
    {"name": "seal_bk_chs", "source": "sealBkChs", "type": "string|null", "note": "边款（简）"},
    {"name": "seal_bkzkz", "source": "sealBkzkz", "type": "string|null", "note": "边款篆者（繁）"},
    {"name": "seal_bkzkz_chs", "source": "sealBkzkzChs", "type": "string|null", "note": "边款篆者（简）"},
    {"name": "seal_bkzkz_id", "source": "sealBkzkzId", "type": "string|null",
     "note": "边款篆者 person id（254）/ 21 个值"},
    {"name": "as_book_id", "source": "asBookId", "type": "string",
     "note": "补零印谱业务号（3679）——桥接 items.as_book_id"},
    {"name": "related_book", "source": "relatedBook", "type": "string", "note": "所属印谱名（3679，繁）"},
    {"name": "seal_yt_url", "source": "sealYtUrl", "type": "string",
     "note": "印面图 ref（3679 全唯一；**2 行以 NaN_ 开头 ⇒ 源侧无图**）"},
    {"name": "seal_ytsw_url", "source": "sealYtswUrl", "type": "string|null", "note": "印体释文图 ref（2627）"},
    {"name": "seal_yzbk_url", "source": "sealYzbkUrl", "type": "string|null", "note": "边款图 ref（459）"},
    {"name": "seal_yzqt_url", "source": "sealYzqtUrl", "type": "string|null", "note": "其它图 ref（实测 3）"},
    {"name": "seal_threed_url", "source": "sealThreedUrl", "type": "string|null", "note": "实测全 null"},
    {"name": "seal_title", "source": "sealTitle", "type": "string|null", "note": "实测全 null"},
    {"name": "seal_title_chs", "source": "sealTitleChs", "type": "string|null", "note": "—"},
    {"name": "seal_org", "source": "sealOrg", "type": "string|null", "note": "实测全 null"},
    {"name": "seal_org_name", "source": "sealOrgName", "type": "string|null", "note": "实测全 null"},
    {"name": "seal_cz", "source": "sealCz", "type": "string|null", "note": "实测全 null"},
    {"name": "seal_cc", "source": "sealCc", "type": "string|null", "note": "实测全 null"},
    {"name": "seal_ly", "source": "sealLy", "type": "string|null", "note": "实测全 null"},
    {"name": "seal_yn", "source": "sealYn", "type": "string|null", "note": "—"},
    {"name": "seal_yksj_lsjn", "source": "sealYksjLsjn", "type": "string|null", "note": "印刻时间（繁）"},
    {"name": "seal_yksj_lsjn_chs", "source": "sealYksjLsjnChs", "type": "string|null", "note": "印刻时间（简）"},
    {"name": "seal_yksj_gyjn", "source": "sealYksjGyjn", "type": "string|null", "note": "印刻公元年"},
    {"name": "audit_status", "source": "auditStatus", "type": "string",
     "note": "审核状态（**保留字段**；分布见 manifest.audit_status_distribution）"},
    {"name": "misc", "source": "createdTime/updateTime/…/audit*", "type": "object",
     "note": "低频 / 审计元字段子对象（不散落顶层）"},
    {"name": "raw_json", "source": "列表行 ＋ 详情行 ＋ 关联图", "type": "object",
     "note": "源原文 {list, detail, graph}（不得丢源）；默认仅 list 非空"},
]

LINK_FIELD_DICT: list[dict] = [
    {"name": "source_seal_id", "source": "seqid", "type": "string", "note": "回指 seals.jsonl 的幂等键"},
    {"name": "link_kind", "source": "—", "type": "string",
     "note": "book（印谱）/ person_yz（印主）/ person_zzkz（篆者）/ person_bkzkz（边款篆者）/ person_graph（graph 独有）"},
    {"name": "ref_id", "source": "asBookId | sealYz | sealYzzkzId | sealBkzkzId | graph.id",
     "type": "string", "note": "被关联对象键（印谱 as_book_id / 印人 person id）"},
    {"name": "ref_name", "source": "relatedBook | sealYzPersonName | sealYzzkz | sealBkzkz | graph.name",
     "type": "string|null", "note": "被关联对象名（繁）"},
    {"name": "ref_name_chs", "source": "…Chs", "type": "string|null", "note": "简体副字段（graph 面无 ⇒ null）"},
    {"name": "creator_type", "source": "graph/seal creatorType", "type": "string|null",
     "note": "责任类型；**行内字段无此字段 ⇒ 默认 null**（仅 --with-graph 时有值）"},
    {"name": "bridge_item_id", "source": "items.source_item_id（经 as_book_id 桥接）", "type": "string|null",
     "note": "book 链：桥到印谱库的 source_item_id；person 链为 null"},
    {"name": "source_face", "source": "—", "type": "string",
     "note": f"关联来源面：{FACE_SEAL_ROW}（主源）| {FACE_SEAL_GRAPH}（--with-graph）"},
    {"name": "seq", "source": "graph 子项次序", "type": "integer", "note": "组内序号（行内构建恒 0）"},
]


def _read_seals(conn: sqlite3.Connection, batch_id: str | None = None) -> list[dict]:
    where = " WHERE batch_id=?" if batch_id else ""
    args: tuple = (batch_id,) if batch_id else ()
    rows = conn.execute(
        f"SELECT {', '.join(SEAL_FIELDS)} FROM seals{where} ORDER BY source_seal_id", args).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["misc"] = json.loads(d["misc"]) if d.get("misc") else None
            d["raw_json"] = json.loads(d["raw_json"]) if d.get("raw_json") else None
        except (ValueError, TypeError):
            pass
        out.append(d)
    return out


def _read_links(conn: sqlite3.Connection, batch_id: str | None = None) -> list[dict]:
    where = " WHERE batch_id=?" if batch_id else ""
    args: tuple = (batch_id,) if batch_id else ()
    rows = conn.execute(
        f"SELECT {', '.join(LINK_FIELDS)} FROM seal_links{where} "
        f"ORDER BY source_seal_id, link_kind, ref_id, source_face, seq", args).fetchall()
    return [dict(r) for r in rows]


def _audit_distribution(seals: list[dict]) -> dict:
    dist: dict[str, int] = {}
    for s in seals:
        k = str(s.get("audit_status"))
        dist[k] = dist.get(k, 0) + 1
    return dict(sorted(dist.items(), key=lambda kv: (kv[0] != "None", kv[0])))


def _ys_distribution(seals: list[dict]) -> dict:
    dist: dict[str, int] = {}
    for s in seals:
        k = s.get("seal_ys_xz")
        kk = "null" if k is None else str(k)
        dist[kk] = dist.get(kk, 0) + 1
    # 码序 + null 置首
    ordered: dict[str, int] = {}
    if "null" in dist:
        ordered["null"] = dist.pop("null")
    for code in sorted(int(x) for x in dist if x.isdigit()):
        ordered[str(code)] = dist[str(code)]
    for k, v in dist.items():
        if k not in ordered:
            ordered[k] = v
    return ordered


def _coverage(seals: list[dict]) -> dict:
    n = len(seals) or 1
    keys = {
        "seal_wen": lambda p: bool(p.get("seal_wen")),
        "seal_wen_chs": lambda p: bool(p.get("seal_wen_chs")),
        "seal_ys_xz": lambda p: p.get("seal_ys_xz") is not None,
        "seal_ys_label": lambda p: bool(p.get("seal_ys_label")),
        "seal_yz": lambda p: bool(p.get("seal_yz")),
        "seal_yzzkz_id": lambda p: bool(p.get("seal_yzzkz_id")),
        "seal_bk": lambda p: bool(p.get("seal_bk")),
        "seal_bkzkz_id": lambda p: bool(p.get("seal_bkzkz_id")),
        "as_book_id": lambda p: bool(p.get("as_book_id")),
        "related_book": lambda p: bool(p.get("related_book")),
        "seal_yt_url": lambda p: bool(p.get("seal_yt_url")),
        "seal_ytsw_url": lambda p: bool(p.get("seal_ytsw_url")),
        "seal_yzbk_url": lambda p: bool(p.get("seal_yzbk_url")),
    }
    return {k: f"{sum(1 for p in seals if fn(p))}/{len(seals)} ({(sum(1 for p in seals if fn(p)) / n):.1%})"
            for k, fn in keys.items()}


def _no_bom(path: Path) -> bool:
    with Path(path).open("rb") as fh:
        return fh.read(3) != b"\xef\xbb\xbf"


def write_package(*, db_path: Path, export_root: Path, batch_id: str, base: str, source_total: int,
                  params: dict, failures: list[dict], rows_seen: int,
                  item_db_path: Path | None = None,
                  with_detail: bool = False, with_graph: bool = False,
                  detail_unconfirmed: list[dict] | None = None,
                  graph_unconfirmed: list[dict] | None = None,
                  images_root: Path | None = None,
                  link_only_from_row: bool = False) -> dict:
    """产 xiai 就绪包 `exports/seal_import_<batch_id>/`。

    产物：`seals.jsonl` ＋ `seal_links.jsonl` ＋ `manifest.json` ＋ `report.json`
    ＋（若提供 `images_root`）`images/` ＋ `images_manifest.jsonl`。

    **重新出包不得删已有 `images/`**（重建口径同 item：仅时间戳变、JSONL 字节不变）。
    """
    detail_unconfirmed = list(detail_unconfirmed or [])
    graph_unconfirmed = list(graph_unconfirmed or [])
    conn = _connect(db_path)
    try:
        seals = _read_seals(conn, batch_id)
        links = _read_links(conn, batch_id)
        fp = content_fingerprint(conn)
    finally:
        conn.close()

    pkg_dir = Path(export_root) / f"seal_import_{batch_id}"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    seals_path = pkg_dir / "seals.jsonl"
    links_path = pkg_dir / "seal_links.jsonl"
    manifest_path = pkg_dir / "manifest.json"

    with seals_path.open("w", encoding="utf-8", newline="\n") as fh:
        for it in seals:
            fh.write(json.dumps({k: it.get(k) for k in SEAL_FIELDS}, ensure_ascii=False) + "\n")
    with links_path.open("w", encoding="utf-8", newline="\n") as fh:
        for c in links:
            fh.write(json.dumps({k: c.get(k) for k in LINK_FIELDS}, ensure_ascii=False) + "\n")

    # ── 幂等键唯一计数 ──
    ids = [it.get("source_seal_id") for it in seals]
    id_non_null = sum(1 for x in ids if x not in (None, ""))
    id_unique = len({x for x in ids if x not in (None, "")})
    yt_ids = [it.get("seal_yt_url") for it in seals if it.get("seal_yt_url")]
    yt_unique = len(set(yt_ids))

    # ── 形製码表标定证据（码 → 计数；每码应可派生；无冲突）──
    ys_counts = _ys_distribution(seals)
    ys_conflicts = []  # 码表为纯函数 ⇒ 逐行派生值必须与码一致；冲突应在 0
    for s in seals:
        code = s.get("seal_ys_xz")
        label = s.get("seal_ys_label")
        if code is None:
            if label is not None:
                ys_conflicts.append({"source_seal_id": s["source_seal_id"], "code": None, "label": label})
        else:
            expect = SEAL_YS_XZ_LOOKUP.get(int(code))
            if label != expect:
                ys_conflicts.append({"source_seal_id": s["source_seal_id"], "code": code,
                                     "label": label, "expect": expect})

    # ── sidecar 回指 seals ──
    seal_id_set = {x for x in ids if x not in (None, "")}
    orphan = sorted(str(x) for x in {c.get("source_seal_id") for c in links
                     if c.get("source_seal_id") is not None and c.get("source_seal_id") not in seal_id_set})
    link_kind_counts: dict[str, int] = {}
    for c in links:
        k = str(c.get("link_kind") or "unknown")
        link_kind_counts[k] = link_kind_counts.get(k, 0) + 1
    face_counts: dict[str, int] = {}
    for c in links:
        f = str(c.get("source_face") or "unknown")
        face_counts[f] = face_counts.get(f, 0) + 1
    bridged = sum(1 for c in links if c.get("link_kind") == "book" and c.get("bridge_item_id"))

    # ── 影像（若提供 images_root ⇒ hardlink/copy 入包 + images_manifest）──
    image_counts = image_status_counts(db_path)
    images_manifest = _materialize_images(db_path, pkg_dir, images_root) if images_root else None

    checks = {
        "rows": len(seals),
        "links_rows": len(links),
        "idempotency_non_null": id_non_null,
        "idempotency_unique": id_unique,
        "idempotency_total": len(ids),
        "idempotency_all_non_null_and_unique": (id_non_null == len(ids) == id_unique),
        "seal_yt_url_unique": yt_unique,
        "seal_yt_url_total_non_null": len(yt_ids),
        "seal_ys_lookup_conflicts": ys_conflicts,
        "seal_ys_lookup_conflict_free": len(ys_conflicts) == 0,
        "links_orphan_source_seal_id": orphan,
        "links_all_backref_seals": len(orphan) == 0,
        "seals_no_bom": _no_bom(seals_path),
        "links_no_bom": _no_bom(links_path),
    }

    detail_policy = {
        "enabled": bool(with_detail),
        "default": "off",
        "switch": "--with-detail（CLI sync）/ with_detail=true（POST /api/seals/sync 请求体）",
        "rationale": ("形製可读值已由本地码表纯函数派生（seal_ys_label）⇒ 无需逐枚 detail；"
                      "detail 降 best-effort（默认关），仅补 seal_ys_ref_id / audit_user / 真源标签校对。"),
        "detail_only_fields": ["sealYzRefId", "auditUser", "sealYsXzLabel（真源校对）"],
        "detail_unconfirmed": len(detail_unconfirmed),
        "detail_unconfirmed_list": detail_unconfirmed,
    }
    link_policy = {
        "primary_face": FACE_SEAL_ROW,
        "graph_face": FACE_SEAL_GRAPH,
        "with_graph": bool(with_graph),
        "chosen": "seal_row（行内字段直接构建）",
        "rationale": ("seal/list 行已含三类 person 链（sealYz/印主、sealYzzkzId/篆者、sealBkzkzId/边款篆者）"
                      "＋印谱链（asBookId＋relatedBook），覆盖 100%；graph/seal 只多给「印谱 canonical seqid」，"
                      "可由 asBookId 桥接本地派生 ⇒ 零额外联网即全量构建，且不与影像下载抢同站请求额度。"),
        "link_kind_counts": link_kind_counts,
        "by_source_face": face_counts,
        "book_links_bridged_to_item": bridged,
        "graph_unconfirmed": len(graph_unconfirmed),
    }
    source_missing = build_source_missing_summary(db_path)
    source_missing_compact = {k: v for k, v in source_missing.items() if k != "rows"}
    image_policy = {
        "mode": "iiif_char_proxy",
        "url_template": f"{iiif_host(base)}/iiif_proxy/api/char_proxy/<ref>",
        "follow_redirect": True,
        "native_crop_only": True,
        "native_crop_note": ("只用原生裁切（302 终点形如 `/full/0/default.jpg`，1:1 源像素）。"
                             "**禁用 `!w,h` 放大尺寸**——实测 `1200,` ⇒ 1200×2147 系**纯插值上采样**，"
                             "边缘强度 我双三次上采样 135.71 vs 服务器大图 137.69、MAD 4.32/255、"
                             "累方差 2858 vs 2824 ⇒ **不增真实信息**，属失真（见 ops/seal-ingest/09_upscale_probe.json）。"),
        "upscale_probe": {
            "probe_file": "ops/seal-ingest/09_upscale_probe.json",
            "native_vs_upsampled": {
                "edge_strength_my_bicubic": 135.71,
                "edge_strength_server_large": 137.69,
                "mad_255": 4.32,
                "cumulative_variance_upsampled": 2858,
                "cumulative_variance_native": 2824,
            },
            "verdict": "禁用放大尺寸（不增真实信息）；只取 /full/ 原生裁切",
        },
        "source_cache": "var/seal_images/<kind>/<seqid>.jpg（JPEG 源；**不入包**）",
        "container": "image/tiff",
        "conversion": CONVERSION_TAG,
        "conversion_note": ("IIIF 仅出 JPEG ⇒ 本包 TIFF 为 **无损容器转换**（解码 RAW JPEG 像素原样装进 TIFF，"
                            "不重采样、不二次有损编码），**质量受源 JPEG 限制**。"),
        "tiff_cache": "var/seal_images_tiff/<sha256[:2]>/<sha256>.tiff（内容寻址；**可续跑**）",
        "path_shape": "<sha256[:2]>/<sha256>.tiff",
        "content_addressed": True,
        "index_key": "sha256（TIFF 字节的 sha256；`images_manifest.jsonl` 是唯一索引）",
        "xiai_contract": {
            "endpoint": "POST /api/image/store",
            "read": "GET /api/image/original/{sha256}",
            "accepts": "只收 TIFF 容器（魔数 II*\\0 / MM\\0*；不回落、不冒充）",
            "stored_max_bytes": XIAI_STORED_MAX_BYTES,
            "max_input_bytes": XIAI_MAX_INPUT_BYTES,
        },
        "kinds": {k: IMAGE_KIND_NOTE[k] for k in IMAGE_KINDS},
        "status_counts": image_counts,
        "by_kind": image_kind_status(db_path),
        "no_image_rule": ("`source_no_image` 三条子因：① ref 以 `NaN_` 开头 ⇒ 源侧无图；"
                          "② 有界重试（3 轮 2/8/30s）后仍 HTTP 500 ⇒ 源侧坏图（站点同图页面 naturalWidth=0）；"
                          "③ HTTP 200 且 content-type=image/jpeg，但正文非可解码影像（Pillow 无法识别，如 iipsrv 把自身"
                          "响应头当正文吐出）⇒ 源侧坏字节（`bad_bytes`，持久复现）。"
                          "**三者均登记为「源侧无图」，非采集失败**；`failed` 只留给可重试的瞬态错误。"),
        "no_source_reasons": NO_SOURCE_REASON_NOTE,
        "source_missing": source_missing_compact,
        "packaged": images_manifest["counts"] if images_manifest else None,
        "packaged_checks": images_manifest["checks"] if images_manifest else None,
    }

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "key_face_status": "pending_xiai",
        "form": "F1（manifest + seals.jsonl + seal_links.jsonl + images/）",
        "batch_id": batch_id,
        "created_at": _now(),
        "source": "复旦印藏（yin.fudan.edu.cn）「印章」",
        "source_base": base,
        "source_endpoints": [
            "POST /service_yinpu/seal/list  {pageNum:1, pageRows:5000}（一次取全 3679；支持 auditStatus 过滤；"
            "**seal 本体全部取自此处**）",
            "GET /service_yinpu/graph/seal/<seqid>（**best-effort，默认关**；印谱/印人子项）",
            "GET /service_yinpu/seal/detail/<seqid>（**best-effort，默认关**；补 sealYzRefId/auditUser）",
            f"GET {iiif_host(base)}/iiif_proxy/api/char_proxy/<ref>（IIIF 裁切图；302 ⇒ 跟跳转得 image/jpeg）",
        ],
        "source_total": source_total,
        "idempotency_key": "source_seal_id（＝复旦 seqid）",
        "bridge_key": "as_book_id（＝补零 asBookId，桥接 items.as_book_id ↔ items.source_item_id）",
        "files": [
            {"name": "seals.jsonl", "rows": len(seals), "fields": SEAL_FIELDS,
             "format": "JSONL，一行一对象，UTF-8，无 BOM"},
            {"name": "seal_links.jsonl", "rows": len(links), "fields": LINK_FIELDS,
             "format": "JSONL，一行一对象，UTF-8，无 BOM",
             "note": "sidecar（印章↔印谱↔印人）：主源＝行内字段（source_face='seal_row'）；"
                     "book 链带 bridge_item_id（经 items.as_book_id 桥到印谱 source_item_id）"},
            {"name": "images_manifest.jsonl", "rows": (images_manifest or {}).get("rows"),
             "fields": ["seqid", "kind", "source_ref", "source_url", "sha256", "bytes",
                        "width", "height", "source_format", "container", "conversion", "upscaled"],
             "note": "**唯一索引**：内容寻址后文件名不含 seqid/kind ⇒ 靠它把 sha256 对应回哪枚印章"},
            {"name": "images/<sha256[:2]>/<sha256>.tiff", "rows": (images_manifest or {}).get("rows"),
             "fields": [], "note": "内容寻址 TIFF 树（镜像 xiai 影像库形态）；**JPEG 不入包**"},
            {"name": "manifest.json", "rows": None, "fields": []},
        ],
        "field_dict": FIELD_DICT,
        "field_dict_links": LINK_FIELD_DICT,
        "seal_ys_lookup": {
            "table": {str(k): v for k, v in SEAL_YS_XZ_LOOKUP.items()},
            "source": "sealYsXz（形製码）",
            "note": "**源侧原文写作「异性」（非「异形」）——逐字照登，不得代改为「异形」**",
            "calibration": {
                "method": "每码 2 枚 × 20 次调用 × 0 冲突 ⇒ 纯函数可派生",
                "samples_per_code": 2,
                "calls_per_sample": 20,
                "conflicts": 0,
                "conflicts_in_package": len(ys_conflicts),
            },
            "distribution": ys_counts,
        },
        "audit_status_distribution": _audit_distribution(seals),
        "audit_status_note": AUDIT_STATUS_NOTE,
        "idempotency": {
            "key": "source_seal_id", "non_null": id_non_null, "unique": id_unique, "total": len(ids),
            "all_non_null_and_unique": checks["idempotency_all_non_null_and_unique"],
        },
        "coverage": _coverage(seals),
        "links_summary": {
            "rows": len(links), "by_link_kind": link_kind_counts, "by_source_face": face_counts,
            "book_links_bridged_to_item": bridged,
        },
        "checks": checks,
        "source_missing": source_missing_compact,
        "image_policy": image_policy,
        "detail_policy": detail_policy,
        "link_policy": link_policy,
        "submission": ("提交与审核在玺爱侧；feicui **不写 xiai 任何文件、不调任何云函数**。"
                       "本包为 feicui 自有树内产物，键面待人（xiai）挑选。"),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "schema_version": SEAL_SCHEMA_VERSION,
        "batch_id": batch_id,
        "generated_at": _now(),
        "source": "复旦印藏（yin.fudan.edu.cn）「印章」",
        "source_base": base,
        "params": params,
        "rows_seen": rows_seen,
        "idempotency_key": "source_seal_id（＝seqid）",
        "counts": {
            "source_total": source_total, "seals": len(seals), "links": len(links),
            "failed_count": len(failures), "images": image_counts,
            "field_list_seals": SEAL_FIELDS, "field_list_links": LINK_FIELDS,
        },
        "content_fingerprint": fp,
        "failures": failures,
        "source_missing": source_missing,
        "image_policy": image_policy,
        "detail_policy": detail_policy,
        "link_policy": link_policy,
        "rate_limit": {
            "trap_form_sanitized": RATE_LIMIT_MARKER,
            "trap_form_note": "HTTP 200；信封 code 是字符串 \"429\"；status 仍可能为 true；只有 data 缺失能暴露失败",
            "handling": "指数退避 5s→10s→20s→40s→60s（上限 60s）后重试；退避耗尽才落失败清单",
        },
    }
    (pkg_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "batch_id": batch_id,
        "package_dir": str(pkg_dir),
        "rows": len(seals),
        "links_rows": len(links),
        "images_rows": (images_manifest or {}).get("rows"),
        "source_total": source_total,
        "key_face_status": manifest["key_face_status"],
        "idempotency_key": manifest["idempotency_key"],
        "bridge_key": manifest["bridge_key"],
        "idempotency": manifest["idempotency"],
        "coverage": manifest["coverage"],
        "audit_status_distribution": manifest["audit_status_distribution"],
        "seal_ys_lookup": manifest["seal_ys_lookup"],
        "links_summary": manifest["links_summary"],
        "checks": checks,
        "files": manifest["files"],
        "field_dict": FIELD_DICT,
        "field_dict_links": LINK_FIELD_DICT,
        "image_policy": image_policy,
        "detail_policy": detail_policy,
        "link_policy": link_policy,
        "content_fingerprint": fp,
        "generated_at": manifest["created_at"],
        "submission": manifest["submission"],
    }
    return {"package_dir": pkg_dir, "report_path": pkg_dir / "report.json",
            "seals_path": seals_path, "links_path": links_path,
            "manifest_path": manifest_path, "fingerprint": fp, "summary": summary}


def _materialize_images(db_path: Path, pkg_dir: Path, images_root: Path) -> dict:
    """把 TIFF 缓存 hardlink（失败则 copy）入包 `images/<sha256[:2]>/<sha256>.tiff`（**镜像 xiai 形态**）。

    写 `images_manifest.jsonl`（**唯一索引**：内容寻址后文件名不含 seqid/kind）：
    每行 `{seqid, kind, source_ref, source_url, sha256, bytes, width, height,
    source_format:'image/jpeg', container:'image/tiff', conversion:'jpeg->tiff(lossless container)', upscaled:false}`。

    **不删已有 `images/`**（仅补缺 / 覆盖同名）；**JPEG 不入包**（仅作 `var/` 源缓存）。

    出包同时做**双向自检**：① 每行 sha256 ＝ 包内该 TIFF 字节 sha256；② TIFF 魔数逐行成立；
    ③ 单张 ≤ 4 MiB（xiai 产物档）且 ≤ 1 MB（xiai 输入档）——超档单列；④ 行 ↔ 树文件一一对应（无孤儿 / 无缺失）。
    """
    import shutil

    dst_root = pkg_dir / "images"
    dst_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    linked = copied = missing = 0
    sha_mismatch: list[dict] = []
    magic_fail: list[dict] = []
    oversize_stored: list[dict] = []
    oversize_input: list[dict] = []
    conn = _connect(db_path)
    try:
        recs = conn.execute(
            "SELECT seqid, kind, source_ref, source_url, tiff_path, tiff_sha256, tiff_bytes, "
            "width, height, upscaled, status FROM seal_images WHERE status='ok' ORDER BY kind, seqid"
        ).fetchall()
    finally:
        conn.close()

    manifest_path = pkg_dir / "images_manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in recs:
            sha = r["tiff_sha256"]
            if not sha:
                missing += 1
                continue
            src = Path(r["tiff_path"]) if r["tiff_path"] else None
            if src is None or not src.is_file():
                missing += 1
                continue
            dst = dst_root / sha[:2] / f"{sha}.tiff"
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists():
                try:
                    os.link(src, dst)
                    linked += 1
                except OSError:
                    shutil.copy2(src, dst)
                    copied += 1
            # ── 逐行自检（内容寻址键＝该 TIFF 字节的 sha256）──
            real_sha = sha256_file(dst)
            if real_sha != sha:
                sha_mismatch.append({"seqid": r["seqid"], "kind": r["kind"],
                                     "row_sha256": sha, "file_sha256": real_sha})
            if not tiff_container_ok(dst):
                magic_fail.append({"seqid": r["seqid"], "kind": r["kind"], "sha256": sha})
            nbytes = dst.stat().st_size
            if nbytes > XIAI_STORED_MAX_BYTES:
                oversize_stored.append({"seqid": r["seqid"], "kind": r["kind"], "sha256": sha, "bytes": nbytes})
            if nbytes > XIAI_MAX_INPUT_BYTES:
                oversize_input.append({"seqid": r["seqid"], "kind": r["kind"], "sha256": sha, "bytes": nbytes})
            row = {
                "seqid": r["seqid"], "kind": r["kind"], "source_ref": r["source_ref"],
                "source_url": r["source_url"], "sha256": sha, "bytes": r["tiff_bytes"],
                "width": r["width"], "height": r["height"],
                "source_format": "image/jpeg", "container": "image/tiff",
                "conversion": CONVERSION_TAG, "upscaled": False,
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            rows.append(row)

    # ── 方向二：树上每个文件都有对应行（无孤儿）──
    row_shas = {row["sha256"] for row in rows}
    tree_files = {p.stem: p for p in dst_root.rglob("*.tiff") if p.is_file()}
    orphan_files = sorted(set(tree_files) - row_shas)
    rows_without_file = sorted(sha for sha in row_shas
                               if not (dst_root / sha[:2] / f"{sha}.tiff").is_file())

    counts = {
        "rows": len(rows), "hardlinked": linked, "copied": copied, "missing_cache": missing,
        "tree_files": len(tree_files), "orphan_files": len(orphan_files),
        "rows_without_file": len(rows_without_file),
        "by_kind": {},
    }
    for row in rows:
        k = row["kind"]
        counts["by_kind"][k] = counts["by_kind"].get(k, 0) + 1
    checks = {
        "row_count": len(rows),
        "tree_file_count": len(tree_files),
        "one_to_one": (len(rows) == len(tree_files) == len(row_shas)),
        "orphan_files": orphan_files[:50],
        "rows_without_file": rows_without_file[:50],
        "sha256_equals_tiff_bytes": len(sha_mismatch) == 0,
        "sha256_mismatch": sha_mismatch[:50],
        "tiff_magic_all_ok": len(magic_fail) == 0,
        "tiff_magic_fail": magic_fail[:50],
        "max_stored_bytes": XIAI_STORED_MAX_BYTES,
        "max_input_bytes": XIAI_MAX_INPUT_BYTES,
        "oversize_stored": oversize_stored,
        "oversize_input": oversize_input,
    }
    return {"rows": len(rows), "counts": counts, "checks": checks,
            "manifest_path": str(manifest_path)}


def write_package_from_db(db_path, export_root, batch_id=None, base=None, images_root=None,
                          item_db=None) -> dict:
    """从库内重建就绪包（**不联网采集**）——CLI `package` 与 `POST /api/seals/package` 共用。"""
    if base is None:
        from .config import get_settings
        base = get_settings().seals_source_base
    if images_root is None:
        from .config import get_settings
        images_root = get_settings().seal_images_dir
    ensure_schema(db_path)
    conn = _connect(db_path)
    try:
        if batch_id:
            if conn.execute("SELECT 1 FROM seal_import_batches WHERE batch_id=?", (batch_id,)).fetchone() is None:
                raise ImportPackageError("BATCH_NOT_FOUND", f"批次不存在：{batch_id}")
        else:
            r = conn.execute("SELECT batch_id FROM seal_import_batches ORDER BY batch_id DESC LIMIT 1").fetchone()
            if r is None:
                raise ImportPackageError("NO_BATCH", "本库尚无任何批次 ⇒ 无法生成就绪包（先跑 POST /api/seals/sync）")
            batch_id = r["batch_id"]
        total = conn.execute("SELECT source_total FROM seal_import_batches WHERE batch_id=?", (batch_id,)).fetchone()
        source_total = total["source_total"] if total else None
    finally:
        conn.close()
    return write_package(db_path=Path(db_path), export_root=Path(export_root), batch_id=str(batch_id),
                         base=base, source_total=int(source_total or 0), params={"rebuilt": True},
                         failures=[], rows_seen=0, item_db_path=Path(item_db) if item_db else None,
                         images_root=Path(images_root) if images_root else None)


# ═══════════════════════════════════════════════════════════════════════════ 查询
def list_seals(db_path: Path | str, *, page: int = 1, limit: int = 50, audit_status: str | None = None,
               has_image: bool | None = None, q: str | None = None) -> dict:
    """列表（**纯 offset 分页**）。`has_more == (page*limit < total)`；**不输出 `next_cursor`**。"""
    where: list[str] = []
    args: list[Any] = []
    if audit_status is not None:
        where.append("audit_status = ?")
        args.append(str(audit_status))
    if has_image is True:
        where.append("seal_yt_url IS NOT NULL")
    elif has_image is False:
        where.append("seal_yt_url IS NULL")
    if q:
        where.append("(seal_wen LIKE ? OR seal_wen_chs LIKE ? OR related_book LIKE ? OR source_seal_id = ?)")
        like = f"%{q}%"
        args += [like, like, like, q]
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    conn = _connect(db_path)
    try:
        total = conn.execute(f"SELECT COUNT(*) FROM seals{where_sql}", args).fetchone()[0]
        offset = max(0, (page - 1) * limit)
        rows = conn.execute(
            f"""SELECT source_seal_id, seal_wen, seal_wen_chs, seal_ys_xz, seal_ys_label,
                       related_book, as_book_id, seal_yz_person_name, seal_yzzkz, seal_yzzkz_id,
                       seal_yt_url, seal_ytsw_url, seal_yzbk_url, audit_status,
                       (SELECT COUNT(*) FROM seal_links l WHERE l.source_seal_id=seals.source_seal_id) AS link_count
                FROM seals{where_sql}
                ORDER BY as_book_id, source_seal_id
                LIMIT ? OFFSET ?""",
            args + [limit, offset],
        ).fetchall()
        items = [dict(r) for r in rows]
        has_more = (page * limit) < total
        return {"items": items, "page": page, "limit": limit, "total": total, "has_more": has_more}
    finally:
        conn.close()


def list_facets(db_path: Path | str) -> dict:
    conn = _connect(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM seals").fetchone()[0]
        with_img = conn.execute("SELECT COUNT(*) FROM seals WHERE seal_yt_url IS NOT NULL").fetchone()[0]
        dist = {r[0]: r[1] for r in conn.execute(
            "SELECT audit_status, COUNT(*) FROM seals GROUP BY audit_status ORDER BY audit_status")}
        return {"total": total, "with_image": with_img, "audit_status_distribution": dist}
    finally:
        conn.close()


def get_seal(db_path: Path | str, seqid: str) -> dict | None:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM seals WHERE source_seal_id=?", (seqid,)).fetchone()
        if row is None:
            return None
        rec = dict(row)
        try:
            rec["misc"] = json.loads(rec["misc"]) if rec.get("misc") else None
            rec["raw_json"] = json.loads(rec["raw_json"]) if rec.get("raw_json") else None
        except (ValueError, TypeError):
            pass
        links = conn.execute(
            "SELECT source_seal_id, link_kind, ref_id, ref_name, ref_name_chs, creator_type, "
            "bridge_item_id, source_face, seq FROM seal_links WHERE source_seal_id=? "
            "ORDER BY source_face, link_kind, seq", (seqid,)).fetchall()
        rec["links"] = [dict(r) for r in links]
        imgs = conn.execute(
            "SELECT seqid, kind, source_ref, source_url, local_path, bytes, sha256, status, error "
            "FROM seal_images WHERE seqid=? ORDER BY kind", (seqid,)).fetchall()
        rec["images"] = [dict(r) for r in imgs]
        return rec
    finally:
        conn.close()


def seal_image_path(db_path: Path | str, images_root: Path, seqid: str, kind: str) -> Path | None:
    """读本地影像路径：优先台账 `local_path`，退化到 `<images_root>/<kind>/<seqid>.jpg`。"""
    rec = image_ledger_get(db_path, seqid, kind)
    if rec and rec.get("local_path") and Path(rec["local_path"]).is_file():
        return Path(rec["local_path"])
    p = image_local_path(images_root, kind, seqid)
    return p if p.is_file() else None


# ═══════════════════════════════════════════════════════════════════════════ CLI
def _cli() -> int:
    import argparse

    from .config import get_settings

    st = get_settings()
    ap = argparse.ArgumentParser(description="feicui 印章采集线（批 1）")
    ap.add_argument("cmd", choices=[
        "sync", "counts", "fingerprint", "list-count", "package", "anchors",
        "sync-images", "convert-images", "image-counts",
    ], help="子命令")
    ap.add_argument("--db", default=str(st.seals_db_path))
    ap.add_argument("--export-root", default=str(st.seals_export_root))
    ap.add_argument("--item-db", default=str(st.items_db_path))
    ap.add_argument("--images-root", default=str(st.seal_images_dir))
    ap.add_argument("--tiff-root", default=str(st.seal_images_tiff_dir))
    ap.add_argument("--base", default=st.seals_source_base)
    ap.add_argument("--batch-id", default=None)
    ap.add_argument("--no-resume", action="store_true")
    ap.add_argument("--delay", type=float, default=st.seals_fetch_delay_s)
    ap.add_argument("--limit", type=int, default=None, help="本轮最多新增取数（分片续跑）")
    ap.add_argument("--with-detail", action="store_true", help="best-effort 逐枚 seal/detail（默认关）")
    ap.add_argument("--with-graph", action="store_true", help="best-effort 逐枚 graph/seal（默认关）")
    # 影像参数
    ap.add_argument("--kinds", default="yt,ytsw,yzbk")
    ap.add_argument("--img-delay", type=float, default=st.seals_image_delay_s)
    ap.add_argument("--img-limit", type=int, default=None)
    ap.add_argument("--img-workers", type=int, default=st.seals_image_concurrency,
                    help="影像下载并发（>1 走有界并发；pilot 实测 w=4 无 429）")
    args = ap.parse_args()

    if args.cmd == "counts":
        ensure_schema(args.db)
        print(json.dumps(db_counts(args.db), ensure_ascii=False))
        return 0
    if args.cmd == "image-counts":
        ensure_schema(args.db)
        print(json.dumps(image_status_counts(args.db), ensure_ascii=False))
        return 0
    if args.cmd == "fingerprint":
        ensure_schema(args.db)
        conn = _connect(args.db)
        try:
            print(content_fingerprint(conn))
        finally:
            conn.close()
        return 0
    if args.cmd == "list-count":
        rows, total = fetch_seals_list(args.base, timeout=st.seals_fetch_timeout_s)
        print(json.dumps({"total": total, "rows": len(rows)}, ensure_ascii=False))
        return 0
    if args.cmd == "anchors":
        ensure_schema(args.db)
        out = {}
        for sid in ("3922", "3894", "3921"):
            out[sid] = get_seal(args.db, sid)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "package":
        try:
            pkg = write_package_from_db(args.db, args.export_root, args.batch_id, args.base,
                                        args.images_root, args.item_db)
        except ImportPackageError as exc:
            print(json.dumps({"ok": False, "error": exc.code, "detail": str(exc)}, ensure_ascii=False))
            return 2
        out = {k: (str(v) if isinstance(v, Path) else v) for k, v in pkg.items() if k != "summary"}
        out["summary"] = pkg.get("summary")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "sync-images":
        def _img_progress(p: dict) -> None:
            print(f"[images] {p['done']}/{p['total']} ok={p['ok']} skipped={p['skipped']} "
                  f"failed={p['failed']} no_source={p['no_source']}", flush=True)
        kw = dict(
            db_path=Path(args.db), images_root=Path(args.images_root), base=args.base,
            kinds=tuple(k.strip() for k in args.kinds.split(",") if k.strip()),
            resume=not args.no_resume, delay=args.img_delay, limit=args.img_limit,
            timeout=st.seals_fetch_timeout_s, progress=_img_progress, batch_id=args.batch_id,
            tiff_dir=Path(args.tiff_root), convert=True,
        )
        if args.img_workers > 1:
            summary = download_images_threaded(workers=args.img_workers, **kw)
        else:
            summary = download_images(**kw)
        print(json.dumps({k: v for k, v in summary.items() if k != "failures"}, ensure_ascii=False, indent=2))
        print("FAILURES=" + json.dumps(summary["failures"], ensure_ascii=False))
        return 0
    if args.cmd == "convert-images":
        def _cv_progress(p: dict) -> None:
            print(f"[convert] {p['done']}/{p['total']} converted={p['converted']} failed={p['failed']}", flush=True)
        summary = convert_missing_tiffs(
            db_path=Path(args.db), images_root=Path(args.images_root), tiff_dir=Path(args.tiff_root),
            limit=args.img_limit, progress=_cv_progress,
        )
        print(json.dumps({k: v for k, v in summary.items() if k != "failures"}, ensure_ascii=False, indent=2))
        print("FAILURES=" + json.dumps(summary["failures"], ensure_ascii=False))
        return 0

    def _progress(p: dict) -> None:
        print(f"[sync] {p['done']}/{p['total']} ok={p['seals_ok']} fetched={p['fetched']} "
              f"failed={p['failed']}", flush=True)

    summary = run_sync(
        db_path=Path(args.db), export_root=Path(args.export_root), base=args.base,
        item_db_path=Path(args.item_db) if args.item_db else None,
        batch_id=args.batch_id, resume=not args.no_resume, delay=args.delay,
        limit=args.limit, timeout=st.seals_fetch_timeout_s,
        with_detail=args.with_detail, with_graph=args.with_graph, progress=_progress,
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "failures"}, ensure_ascii=False, indent=2))
    print("FAILURES=" + json.dumps(summary["failures"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
