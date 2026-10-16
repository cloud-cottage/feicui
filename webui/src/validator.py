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
    """是否符合标准模板"""
    return parse_filename(name) is not None
