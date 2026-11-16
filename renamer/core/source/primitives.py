"""编辑态原语：死引用剔除（纯函数，唯一来源）

以规则面板 ``_strip_dead_refs`` 现有逻辑为需求规格抽入，供组合渲染文本剔除
失效引用时共用（经 app.authoring 再导出到 GUI），不各手写一份。
"""

from __future__ import annotations

from .segment import segment

__all__ = ["strip_dead_refs"]


def strip_dead_refs(
    text: str, live_names: set[str], open: str = "{", close: str = "}"
) -> str:
    """按原文区间删除死引用；有语法诊断的草稿原样保留。"""
    view = segment(text, open, close)
    if view.issues:
        return text
    parts: list[str] = []
    cursor = 0
    for part in view.spans:
        if part.is_token() and part.name not in live_names:
            parts.append(text[cursor : part.s])
            cursor = part.e + 1
    parts.append(text[cursor:])
    return "".join(parts)
