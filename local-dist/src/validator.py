# src/validator.py
"""文件名模板解析与字段校验"""
import re

PREFIX = "P???-C?-R?-"
SUFFIX = ".tiff"

# 模板：P{3位页码}-C{1位列码}-R{1位行码}-{释文}-{朝代}-{作者}.tiff
PATTERN = re.compile(r"^P(\d{3})-C(\d)-R(\d)-(.+?)-(.+?)-(.+?)\.tiff$")

# Windows 非法文件名字符
INVALID_CHARS = r'\/:*?"<>|'

# 字段长度上限（汉字计数）
SHIWEN_MAX = 10
AUTHOR_MAX = 4


def count_chinese(s: str) -> int:
    """统计中文字符个数"""
    return len(re.findall(r"[\u4e00-\u9fff]", s))


def parse_filename(file_name: str):
    """
    从标准模板文件名反向解析三个字段。
    返回 (shiwen, dynasty, author)；不匹配返回 None。
    """
    m = PATTERN.match(file_name.strip())
    if not m:
        return None
    return m.groups()


# ── 新命名（tab2 切图台「有编号」）：`<编号>_P<页>_C<列>_R<行>_<释文>_<朝代>_<作者>.tiff` ──────
#   ⚠ 与旧模板**不是**同一套分隔符（旧的是 `P370-C1-R1-释文-朝代-作者.tiff`）。tab3 若只认旧模板，
#   切图台产出的新文件会**解析不出 P/C/R**（显示「命名不合模板」、三字段空白）——所以这里加**兼容解析**：
#   旧模板优先，认不出再按新命名解；两套都认不出 ⇒ None（tab3 仍走「手工填写」老路，语义未变）。
CROP_PATTERN = re.compile(
    r"^(?P<code>.+?)_P(?P<page>\d+)_C(?P<col>\d+)_R(?P<row>\d+)_(?P<rest>.+)\.tiff$",
    re.IGNORECASE)
#: 无编号回落名 `P<页>-C<列>-R<行>.tiff`（切图台「无编号」产物）：只有 P/C/R，没有三字段。
BARE_PATTERN = re.compile(r"^P(?P<page>\d+)-C(?P<col>\d+)-R(?P<row>\d+)\.tiff$", re.IGNORECASE)


def parse_crop_filename(file_name: str):
    """新命名反解 ⇒ `{code, page, col, row, shiwen, dynasty, author}`；不匹配 ⇒ None。

    尾部三段按 `_` **从右**切（释文里本来就可能有 `_`）：`rest.rsplit('_', 2)` ⇒ 释文/朝代/作者。
    """
    m = CROP_PATTERN.match(str(file_name).strip())
    if not m:
        return None
    parts = m.group("rest").rsplit("_", 2)
    if len(parts) != 3:
        return None
    return {
        "code": m.group("code"),
        "page": int(m.group("page")), "col": int(m.group("col")), "row": int(m.group("row")),
        "page_raw": m.group("page"), "col_raw": m.group("col"), "row_raw": m.group("row"),
        "shiwen": parts[0], "dynasty": parts[1], "author": parts[2],
    }


def parse_tiff_name(file_name: str):
    """**单一入口**：旧模板 → 新命名 → 无编号回落名 → None。⇒ `{naming, page, col, row, code, …}`。

    `naming ∈ {'legacy', 'with_code'}`；旧模板的 `code` 为空串（旧名里没有编号位）。
    **同时给 `page_raw/col_raw/row_raw`**：旧模板页号是零填充三位（`P001`），改名回写必须保原样，
    不能借 `int()` 再拼（那会把 `P001` 变成 `P1`，与旧版 `webui.py` 的前缀不一致）。
    """
    parsed = parse_filename(file_name)
    if parsed:
        page, col, row, shiwen, dynasty, author = parsed
        return {"naming": "legacy", "page": int(page), "col": int(col), "row": int(row),
                "page_raw": page, "col_raw": col, "row_raw": row,
                "code": "", "shiwen": shiwen, "dynasty": dynasty, "author": author}
    crop = parse_crop_filename(file_name)
    if crop:
        crop["naming"] = "with_code"
        return crop
    m = BARE_PATTERN.match(str(file_name).strip())
    if m:
        return {"naming": "legacy", "page": int(m.group("page")), "col": int(m.group("col")),
                "row": int(m.group("row")),
                "page_raw": m.group("page"), "col_raw": m.group("col"), "row_raw": m.group("row"),
                "code": "", "shiwen": "", "dynasty": "", "author": ""}
    return None


def build_crop_filename(page, col, row, shiwen: str, dynasty: str,
                        author: str, code: str = "") -> str:
    """反向构造（tab3 改名预览用）：`code` 非空 ⇒ 新命名，否则旧模板。

    与 `src/seal_crop.build_crop_name` **同构**（段顺序 释文_朝代_作者、`P/C/R` 保留字母前缀）；
    清洗/截断不在这里做 —— tab3 走 `validate_fields`（长度/非法字符先拒），不静默改名。
    `page/col/row` **原样取用**（字符串 "001" 不会被 `int()` 吃掉零填充；int 也照常接受）。
    """
    if str(code or "").strip():
        return (f"{str(code).strip()}_P{page}_C{col}_R{row}"
                f"_{shiwen}_{dynasty}_{author}{SUFFIX}")
    return f"P{page}-C{col}-R{row}-{shiwen}-{dynasty}-{author}{SUFFIX}"


def build_filename(shiwen: str, dynasty: str, author: str) -> str:
    """根据三个字段拼接标准文件名"""
    return f"{PREFIX}{shiwen}-{dynasty}-{author}{SUFFIX}"


def validate_fields(shiwen: str, dynasty: str, author: str):
    """
    校验三个字段。
    返回 (ok: bool, msg: str)
    """
    if not shiwen.strip():
        return False, "印面释文不能为空"
    if not dynasty.strip():
        return False, "朝代不能为空"
    if not author.strip():
        return False, "作者不能为空"

    for c in INVALID_CHARS:
        if c in shiwen or c in dynasty or c in author:
            return False, f"字段包含非法字符：{INVALID_CHARS}"

    sw_n = count_chinese(shiwen)
    if sw_n > SHIWEN_MAX:
        return False, f"印面释文最多 {SHIWEN_MAX} 个汉字，当前 {sw_n}"

    au_n = count_chinese(author)
    if au_n > AUTHOR_MAX:
        return False, f"作者最多 {AUTHOR_MAX} 个汉字，当前 {au_n}"

    return True, ""


def is_standard_tiff(name: str) -> bool:
    """是否符合标准模板（**旧模板或切图台新命名都算合规**，见 `parse_tiff_name`）。"""
    return parse_tiff_name(name) is not None

