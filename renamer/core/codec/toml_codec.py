"""TOML 文本语法与输出排版，Library 结构转换由 library_tables 负责"""

from __future__ import annotations

import re
from typing import Any

try:  # Python 3.11+
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib

from renamer.core.model import Issue, Level, Library, PlanError

from .library_tables import library_from_tables, library_to_tables

__all__ = ["emit", "parse"]

_BARE_KEY_RE = re.compile(r"[A-Za-z0-9_-]+")


def parse(text: str) -> Library:
    """解析 TOML 并转换为 Library，语法或声明结构错误抛 rule_load_failed"""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise PlanError(
            [
                Issue(
                    level=Level.ERROR,
                    code="rule_load_failed",
                    message=f"TOML 解析失败：{exc}",
                )
            ]
        ) from exc

    return library_from_tables(data)


def emit(library: Library) -> str:
    """重新生成规范 TOML 文本，不保留输入文本的注释和排版"""
    lines: list[str] = []
    for section, tables in library_to_tables(library).items():
        for table in tables:
            lines.append(f"[[{_bare_key(section)}]]")
            lines.extend(
                f"{_bare_key(key)} = {_emit_value(value)}"
                for key, value in table.items()
            )
            lines.append("")
    return "\n".join(lines)


def _emit_value(value: Any) -> str:
    if isinstance(value, dict):
        pairs = [f"{_bare_key(k)} = {_emit_value(v)}" for k, v in value.items()]
        return "{ " + ", ".join(pairs) + " }"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_emit_value(v) for v in value) + "]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return _escape_str(value)
    raise TypeError(f"不支持序列化为 TOML 的类型：{type(value)!r}")


def _bare_key(name: str) -> str:
    if _BARE_KEY_RE.fullmatch(name):
        return name
    return _escape_str(name)


def _escape_str(text: str) -> str:
    out: list[str] = ['"']
    for ch in text:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)
