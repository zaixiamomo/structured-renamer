"""共享文法、捕获约束、输出变换与映射简写"""

from __future__ import annotations

from .capture import (
    BoundCapture,
    CaptureError,
    adjacent_capture_conflicts,
    bind_capture,
    infer_type,
)
from .format import (
    BoundTransform,
    apply_bound,
    apply_chain,
    compile_chain,
    compile_expr,
    list_formats,
    validate_call,
    validate_expr,
)
from .mapping import fmt_mapping, parse_mapping
from .syntax import (
    Call,
    Literal,
    Placeholder,
    SourceSpan,
    TemplateSyntax,
    escape_literal,
    fmt_draft_placeholder,
    fmt_expr,
    fmt_placeholder,
    fmt_template,
    parse_expr,
    parse_template,
)

__all__ = [
    "BoundCapture",
    "BoundTransform",
    "Call",
    "CaptureError",
    "Literal",
    "Placeholder",
    "SourceSpan",
    "TemplateSyntax",
    "adjacent_capture_conflicts",
    "apply_bound",
    "apply_chain",
    "bind_capture",
    "compile_chain",
    "compile_expr",
    "escape_literal",
    "fmt_draft_placeholder",
    "fmt_expr",
    "fmt_mapping",
    "fmt_placeholder",
    "fmt_template",
    "infer_type",
    "list_formats",
    "parse_expr",
    "parse_mapping",
    "parse_template",
    "validate_call",
    "validate_expr",
]
