"""PDF 拖曳上传落盘（**additive** 端点 `POST /api/jobs/upload` 的核心逻辑）——Kong。

用途：浏览器 `<input type=file>` / 拖放拿到的 `File` **不带本地路径**（浏览器事实），
而 E1 必须吃「服务器侧 `pdf_path`」⇒ 必须先上传落盘、再把落盘路径交给 E1。

红线（与 `routers/tools.py` 的工具端点同风格）：
  * **零 DB 写、不建 job**：本模块**不 import** `repository` / `db`，不产生任何 SQL；
  * **不动 E1〜E7**：本模块只管「字节 → inbox 里的一个文件」，E1 契约一字未改（纯 additive）；
  * 错误一律由调用方（路由层）落成**结构化 JSON**，**绝不 HTML 错误页**。

为什么走**裸字节流**而不是 multipart：仓内 `app/multipart.py` 是 stdlib 实现，调用侧是
`content = await request.body()` ⇒ **把整个请求体读进内存**。源 PDF 实测 38 MB、历史 372 MB，
372 MB 会打爆接口层内存。故本端点用 `Request.stream()` **分块写盘**（默认 1 MiB/块、内存恒定），
**超限时在写盘过程中即中断**（不会先把盘写满再判负），同目录临时文件 + 原子 `os.replace`。

落点（Kevin 2026-10-10 口径）：`<inbox>/<yyyymmdd>/<safe-name>.pdf`。
幂等：
  * **同名同内容** ⇒ 不重写（`idempotent=true`，目标文件 mtime 不变）；
  * **同名异内容** ⇒ **绝不覆盖**（既有 job 的输入可能正靠它）⇒ 落 `<stem>-<sha256[:8]>.pdf`
    并标 `dedup_suffix=true`。
  * 成本如实登记：幂等重传仍会**先写一次同目录临时文件再删除**——这是「先拿内容 sha 才能判幂等」
    的固有代价；目标文件本身不重写、不重复占盘。
"""
from __future__ import annotations

import hashlib
import os
import re
import urllib.parse
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

PDF_MAGIC = b"%PDF-"
DEFAULT_FILENAME = "upload.pdf"
#: 文件名清毒后的**字节**上限（§3.19.3 例：200 字节；按 UTF-8 字节计，超长截断并保留 `.pdf`）
MAX_STEM_BYTES = 200
TMP_SUFFIX = ".part"
#: §3.19.2：`Content-Type` **必须** ∈ 此二值，否则 `400 BAD_CONTENT_TYPE`
ALLOWED_CONTENT_TYPES = frozenset({"application/pdf", "application/octet-stream"})
#: 同名异内容时依次尝试的后缀长度（sha256 前缀）；8 位碰撞概率可忽略，仍留 16/64 兜底。
DEDUP_PREFIX_LENGTHS = (8, 16, 64)

_FILENAME_STAR = re.compile(r"filename\*\s*=\s*([^;]+)", re.I)
_FILENAME_QUOTED = re.compile(r'filename\s*=\s*"([^"]*)"', re.I)
_FILENAME_BARE = re.compile(r"filename\s*=\s*([^;]+)", re.I)


class UploadRejected(Exception):
    """可预期拒收（路由层据此落结构化 JSON，**不得落 500、不得 HTML 错误页**）。"""

    def __init__(self, status_code: int, error: str, detail: str, **extra: Any) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.error = error
        self.detail = detail
        self.extra = extra


# --------------------------------------------------------------------------- 文件名
def _decode_text(raw: str) -> str:
    """把请求头里的文件名还原成真 Unicode（不臆造、不硬改）。

    * `X-Filename` 按契约是 **URL-encoded UTF-8** ⇒ 先 `unquote`；
    * HTTP 头值只允许 latin-1，Starlette 按 latin-1 解码 ⇒ 浏览器若直送 UTF-8 字节，
      拿到的是 mojibake；此处尝试 `latin-1 → utf-8` 还原（**能还原才还**，还原不了就原样）。
    """
    value = (raw or "").strip()
    if not value:
        return ""
    if "%" in value:
        try:
            value = urllib.parse.unquote(value, encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, UnicodeError):
            value = urllib.parse.unquote(value, encoding="utf-8", errors="replace")
    if any(ord(ch) > 0x7F for ch in value):
        try:
            value = value.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return value


def filename_from_headers(headers: Mapping[str, str]) -> str | None:
    """文件名来源优先级：`X-Filename` → `Content-Disposition` 的 `filename*` / `filename`。"""
    raw = headers.get("x-filename")
    if raw:
        name = _decode_text(str(raw))
        if name:
            return name

    disposition = headers.get("content-disposition")
    if disposition:
        match = _FILENAME_STAR.search(str(disposition))
        if match:
            value = match.group(1).strip().strip('"')
            if "''" in value:  # RFC 5987：UTF-8''%E4%B8%AD…
                value = value.split("''", 1)[1]
            name = _decode_text(value)
            if name:
                return name
        match = _FILENAME_QUOTED.search(str(disposition)) or _FILENAME_BARE.search(str(disposition))
        if match:
            name = _decode_text(match.group(1).strip().strip('"'))
            if name:
                return name
    return None


def check_content_type(raw: str | None) -> str:
    """§3.19.2：`Content-Type` **必须** ∈ {`application/pdf`, `application/octet-stream`}，否则 400。

    容 `; charset=…` 一类参数（只看分号前的基础类型、大小写不敏感）；**缺失 / 其他值一律 400**。
    """
    base = (raw or "").split(";", 1)[0].strip().lower()
    if base not in ALLOWED_CONTENT_TYPES:
        raise UploadRejected(
            400,
            "BAD_CONTENT_TYPE",
            "Content-Type 必须为 application/pdf 或 application/octet-stream"
            f"（收到：{raw or '（缺失）'}）",
            allowed=sorted(ALLOWED_CONTENT_TYPES),
        )
    return base


def _truncate_utf8(text: str, limit_bytes: int) -> str:
    """按 **UTF-8 字节**截断（不切碎多字节字符）。"""
    out: list[str] = []
    used = 0
    for ch in text:
        size = len(ch.encode("utf-8", "ignore"))
        if used + size > limit_bytes:
            break
        out.append(ch)
        used += size
    return "".join(out)


def sanitize_filename(raw: str | None, *, default: str = DEFAULT_FILENAME) -> str:
    """**清毒**：只留 basename；去控制字符 / 路径分隔符 / `..`；后缀一律规范成 `.pdf`；限长。

    限长口径＝ **UTF-8 字节 ≤ `MAX_STEM_BYTES`（200）**，截断后仍保留单个 `.pdf` 后缀。
    """
    name = (raw or "").replace("\\", "/").split("/")[-1]
    name = "".join(ch for ch in name if ord(ch) >= 32 and ord(ch) != 127)
    name = name.strip().strip(".")
    if not name or name in {".", ".."}:
        name = default
    stem, _ext = os.path.splitext(name)
    stem = stem.strip().strip(".")
    if not stem:
        stem = Path(default).stem
    stem = _truncate_utf8(stem, MAX_STEM_BYTES) or Path(default).stem
    return f"{stem}.pdf"


def assert_inside_inbox(day_dir: Path, filename: str, inbox_root: Path) -> Path:
    """**清毒后越界 ⇒ 400**（§3.19.3）。

    basename 化之后本不该越界，此处仍显式兜底：① `filename` 必须是纯 basename（无分隔符 /
    非 `.` / `..`）；② `<inbox_root>/<day>/<filename>` 解析后必须落在 `<inbox_root>` 之内。
    """
    if filename != Path(filename).name or filename in {".", "..", ""} or "/" in filename or "\\" in filename:
        raise UploadRejected(400, "BAD_FILENAME", f"清毒后的文件名不是合法 basename：{filename!r}")
    try:
        (day_dir / filename).resolve().relative_to(Path(inbox_root).resolve())
    except ValueError:
        raise UploadRejected(
            400,
            "BAD_FILENAME",
            f"清毒后的落点越出 inbox 根（{inbox_root}）：{day_dir / filename}",
        )
    return day_dir / filename


# --------------------------------------------------------------------------- 落盘
def day_stamp(now: datetime | None = None) -> str:
    """落点日期目录名 `yyyymmdd`（本机本地时区）。"""
    return (now or datetime.now()).strftime("%Y%m%d")


def sha256_file(path: Path, *, chunk: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _resolve_destination(day_dir: Path, filename: str, sha: str) -> tuple[Path, bool, bool]:
    """决定终名：返回 `(终名, dedup_suffix, idempotent)`。

    * 同名文件不存在 ⇒ 直接用原名（新写入）；
    * 同名存在且 sha 相同 ⇒ **原名 + 幂等**（不重写）；
    * 同名存在但 sha 不同 ⇒ **绝不覆盖**：`<stem>-<sha 前缀>.pdf`（不存在 ⇒ 新写；
      已存在且 sha 相同 ⇒ 幂等复用）。
    """
    base = day_dir / filename
    if not base.exists():
        return base, False, False
    if sha256_file(base) == sha:
        return base, False, True

    stem = Path(filename).stem
    for length in DEDUP_PREFIX_LENGTHS:
        candidate = day_dir / f"{stem}-{sha[:length]}.pdf"
        if not candidate.exists():
            return candidate, True, False
        if sha256_file(candidate) == sha:
            return candidate, True, True

    index = 2  # 理论上不可达（sha256 全量相同却不同名）；兜底加序号，绝不覆盖
    while True:
        candidate = day_dir / f"{stem}-{sha[:8]}-{index}.pdf"
        if not candidate.exists():
            return candidate, True, False
        index += 1


async def store_pdf(
    request: Any,
    *,
    inbox_root: Path,
    max_bytes: int,
    chunk_bytes: int,
    day: str | None = None,
) -> dict[str, Any]:
    """把请求体当**裸字节流**分块写进 `inbox_root/<day>/<safe>.pdf`。

    `request` 只需是 Starlette 的 `Request`（用其 `.headers` 与 `.stream()`）。
    正常返回 `dict`（含 `status_code`：`201` 新写入 / `200` 幂等复用）；
    可预期拒收一律抛 `UploadRejected`（`400 EMPTY_BODY` / `400 NOT_A_PDF` / `413 PAYLOAD_TOO_LARGE`）。
    """
    # —— 校验顺序（§3.19.4 **冻结**）：① Content-Type → ② 空体 → ③ 首字节 `%PDF-` → ④ 累计超限 ——
    check_content_type(request.headers.get("content-type"))  # ①
    if request.query_params:  # §3.19.2：本端点**无查询参数**（未白名单 ⇒ 400，同 Q5 / §3.18.6 型）
        raise UploadRejected(
            400,
            "UNSUPPORTED_PARAM",
            f"本端点无查询参数（收到：{dict(request.query_params)}）",
            unsupported=sorted(request.query_params.keys()),
        )

    filename = sanitize_filename(filename_from_headers(request.headers))
    day = day or day_stamp()
    inbox_root = Path(inbox_root)
    day_dir = inbox_root / day
    assert_inside_inbox(day_dir, filename, inbox_root)  # 清毒后越界 ⇒ 400（防御式兜底）
    declared = str(request.headers.get("content-length") or "").strip()

    tmp_path: Path | None = None
    created_day_dir = False
    handle = None
    total = 0
    head = bytearray()
    magic_ok = False
    digest = hashlib.sha256()

    def _cleanup() -> None:
        nonlocal handle
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
            handle = None
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        if created_day_dir:
            try:
                day_dir.rmdir()  # 只在目录已空时成功（best effort，不留空目录）
            except OSError:
                pass

    try:
        async for block in request.stream():
            if not block:
                continue
            total += len(block)
            if total > max_bytes:
                raise UploadRejected(
                    413,
                    "PAYLOAD_TOO_LARGE",
                    f"上传字节数超过上限 {max_bytes} B（**已在落盘过程中中断**，未写满盘）",
                    limit_bytes=max_bytes,
                    received_bytes=total,
                )
            if not magic_ok:
                head += block
                if len(head) < len(PDF_MAGIC):
                    continue  # 罕见：单块 < 5 字节 ⇒ 继续攒够魔数再判
                if bytes(head[: len(PDF_MAGIC)]) != PDF_MAGIC:
                    raise UploadRejected(
                        400,
                        "NOT_A_PDF",
                        "首字节不是 %PDF-：上传内容不是 PDF",
                        magic=bytes(head[:8]).decode("latin-1", "replace"),
                    )
                # ④ 声明总量超限（`Content-Length`）：魔数已过 ⇒ 立刻 413，**一个字节都不落盘**
                if declared.isdigit() and int(declared) > max_bytes:
                    raise UploadRejected(
                        413,
                        "PAYLOAD_TOO_LARGE",
                        f"请求体声明 {int(declared)} B 超过上限 {max_bytes} B（**未落盘即拒**）",
                        limit_bytes=max_bytes,
                        declared_bytes=int(declared),
                    )
                # 魔数通过 ⇒ **这时才**建目录 / 开临时文件（空体 / 非 PDF 不落任何字节）
                if not day_dir.is_dir():
                    day_dir.mkdir(parents=True, exist_ok=True)
                    created_day_dir = True
                tmp_path = day_dir / f".{filename}-{os.getpid()}-{uuid.uuid4().hex}{TMP_SUFFIX}"
                handle = tmp_path.open("wb")
                handle.write(bytes(head))
                digest.update(bytes(head))
                head.clear()
                magic_ok = True
                continue
            assert handle is not None  # magic 通过时必然已开临时文件
            handle.write(block)
            digest.update(block)

        if total == 0:
            raise UploadRejected(400, "EMPTY_BODY", "请求体为空（0 字节）")
        if not magic_ok:  # 有字节但不足 5 字节
            raise UploadRejected(
                400,
                "NOT_A_PDF",
                f"请求体仅 {total} 字节，短于 %PDF- 魔数（5 字节）",
                received_bytes=total,
            )
        if handle is not None:
            handle.close()
            handle = None
    except BaseException:
        _cleanup()
        raise

    sha = digest.hexdigest()
    assert tmp_path is not None  # magic_ok 为真时必然已建临时文件
    final, dedup_suffix, idempotent = _resolve_destination(day_dir, filename, sha)
    if idempotent:
        tmp_path.unlink(missing_ok=True)
        status_code = 200
    else:
        os.replace(tmp_path, final)  # 同目录 ⇒ 原子 rename
        status_code = 201

    return {
        "status_code": status_code,
        "path": final,
        "filename": final.name,
        "bytes": total,
        "sha256": sha,
        "idempotent": idempotent,
        "dedup_suffix": dedup_suffix,
    }


def iter_pdf_chunks(path: Path, *, chunk: int = 1024 * 1024) -> Iterable[bytes]:
    """（自测用）按块读回已落盘文件，便于逐字节对账。"""
    with Path(path).open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                return
            yield block
