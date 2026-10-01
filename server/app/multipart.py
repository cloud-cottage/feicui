"""`multipart/form-data` 解析（**纯 stdlib**，零新增依赖）——Kong。

## 为什么不用 FastAPI 的 `File()/Form()`

FastAPI/Starlette 解析表单要 `python-multipart`，而接口层 `server/.venv` 现在**没有**这个包，且本单
**可改范围**只有 `server/app/**`（`server/requirements.txt` 不在范围内）。若在路由签名里写 `File(...)`，
一旦该包缺失，**FastAPI 在注册路由时就会抛异常 ⇒ 整个 5196 起不来**（现有 jobs 体系一起挂）。
为避免把一个「新端点」变成「服务启动依赖」，这里用 stdlib `email` 解析 multipart ——
行为在「装没装 python-multipart」两种环境下**完全一致**，且不动任何现存依赖。

口径（只做契约用得上的部分，保持小而可测）：
  * 只接受 `multipart/form-data`（含 boundary）；
  * 文本字段 → `dict[str, str]`（UTF-8，首个同名值生效）；
  * 文件字段 → `dict[str, bytes]`（**原始字节，不做任何解码**；首个同名值生效）；
  * 解析不出 boundary / 不是 multipart / 结构损坏 ⇒ 抛 `MultipartError`（调用侧落 400）。
"""
from __future__ import annotations

import email
import email.policy
from email.message import Message

__all__ = ["MultipartError", "parse_multipart", "is_multipart"]


class MultipartError(ValueError):
    """multipart 结构不可解析（⇒ 400，可读 reason）。"""


def is_multipart(content_type: str) -> bool:
    return content_type.split(";")[0].strip().lower() == "multipart/form-data"


def _boundary_of(content_type: str) -> str:
    msg = Message()
    msg["content-type"] = content_type
    boundary = msg.get_param("boundary", header="content-type")
    if not boundary:
        raise MultipartError("Content-Type 里没有 boundary 参数")
    if isinstance(boundary, tuple):  # RFC 2231 形态（边界值实际不会用到）
        boundary = boundary[2]
    return str(boundary)


def parse_multipart(content_type: str, body: bytes) -> tuple[dict[str, str], dict[str, bytes]]:
    """解析 multipart body，返回 `(fields, files)`。"""
    if not is_multipart(content_type):
        raise MultipartError(f"Content-Type 不是 multipart/form-data：{content_type!r}")
    boundary = _boundary_of(content_type)
    if not body:
        raise MultipartError("请求体为空")

    # 造一个最小 MIME 文档交给 stdlib 解析器（它按行扫描边界，二进制载荷按原样保留）
    raw = (
        b"Content-Type: "
        + content_type.encode("utf-8", "replace")
        + b"\r\nMIME-Version: 1.0\r\n\r\n"
        + body
    )
    try:
        msg = email.message_from_bytes(raw, policy=email.policy.default)
    except Exception as exc:  # noqa: BLE001
        raise MultipartError(f"multipart 解析失败：{exc!r}") from exc
    if not msg.is_multipart():
        raise MultipartError(f"解析器未识别为 multipart（boundary={boundary!r}）")

    fields: dict[str, str] = {}
    files: dict[str, bytes] = {}
    try:
        parts = list(msg.iter_parts())
    except Exception as exc:  # noqa: BLE001
        raise MultipartError(f"multipart 分段失败：{exc!r}") from exc

    for part in parts:
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        name = str(name)
        payload = part.get_payload(decode=True)
        if payload is None:  # 非 base64/quoted-printable 的纯文本段
            raw_payload = part.get_payload()
            payload = (raw_payload or "").encode("utf-8") if isinstance(raw_payload, str) else b""
        filename = part.get_filename()
        if filename is None:
            if name not in fields:
                fields[name] = payload.decode("utf-8", "replace")
        elif name not in files:
            files[name] = payload
    return fields, files
