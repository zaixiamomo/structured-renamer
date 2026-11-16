"""可编辑草稿及声明转换，示例与界面状态不决定规则声明"""

from __future__ import annotations

from .binding import Binding
from .primitives import strip_dead_refs
from .rule import SourceRule, SourceRuleToken, render_template_name
from .segment import Literal, Segment, SegmentedText, Span, segment, tokenize
from .template import SourceTemplate

__all__ = [
    "Binding",
    "Literal",
    "Segment",
    "SegmentedText",
    "SourceRule",
    "SourceRuleToken",
    "SourceTemplate",
    "Span",
    "render_template_name",
    "segment",
    "strip_dead_refs",
    "tokenize",
]
