"""sanitize stage：机制性 sanitize 目标名（非法字符/保留名/末尾点空格）并拼回后缀"""

from __future__ import annotations

from ..context import Context
from ..stage import parse_mismatched

_ILLEGAL = frozenset('<>:"/\\|?*') | frozenset(chr(i) for i in range(32))
_RESERVED = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{i}" for i in range(1, 10)]
    + [f"LPT{i}" for i in range(1, 10)]
)


def sanitize_stem(stem: str) -> str:
    """Windows 非法字符替换为下划线，去末尾点/空格，保留名加前缀 _ 规避"""
    text = "".join("_" if ch in _ILLEGAL else ch for ch in stem)
    text = text.rstrip(". ")
    if text.split(".", 1)[0].upper() in _RESERVED:
        text = "_" + text
    return text


class SanitizeStage:
    """对渲染出的 stem 做机制性 sanitize，拼回原 suffix 得完整目标名"""

    name = "sanitize"

    def process(self, ctx: Context) -> None:
        if parse_mismatched(ctx):
            return
        ctx.target = sanitize_stem(ctx.target or "") + ctx.suffix
