"""共享模板语法：调用、原文位置与规范输出，不解释操作含义。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = [
    "Call",
    "Literal",
    "Placeholder",
    "SourceSpan",
    "TemplateSyntax",
    "escape_literal",
    "fmt_draft_placeholder",
    "fmt_expr",
    "fmt_placeholder",
    "fmt_template",
    "parse_expr",
    "parse_template",
]

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", "'": "'", '"': '"'}


@dataclass(frozen=True)
class Call:
    """操作名及字符串参数；名称与参数是否合法由语义层判定。"""

    name: str
    args: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "args", tuple(self.args))


@dataclass(frozen=True)
class SourceSpan:
    """原文半开区间 [start, end)。"""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise ValueError("原文区间非法")


@dataclass(frozen=True)
class Literal:
    """解码后的字面量；原文通过 span 读取。"""

    text: str
    span: SourceSpan | None = field(default=None, compare=False)


@dataclass(frozen=True)
class Placeholder:
    """占位名及中立注解，None 表示没有显式注解。"""

    name: str
    annotation: tuple[Call, ...] | None = None
    span: SourceSpan | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if self.annotation is not None:
            object.__setattr__(self, "annotation", tuple(self.annotation))


@dataclass(frozen=True)
class TemplateSyntax:
    """模板原文及共享语法树。"""

    source: str
    parts: tuple[Literal | Placeholder, ...]
    open: str = "{"
    close: str = "}"

    def __post_init__(self) -> None:
        object.__setattr__(self, "parts", tuple(self.parts))

    @property
    def tokens(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(p.name for p in self.parts if isinstance(p, Placeholder))
        )


def _skip_space(text: str, pos: int) -> int:
    while pos < len(text) and text[pos].isspace():
        pos += 1
    return pos


def _read_argument(text: str, pos: int) -> tuple[str, int]:
    """读取一个参数；引号外的空白保留为参数内容。"""
    chars: list[str] = []
    quote: str | None = None
    while pos < len(text):
        ch = text[pos]
        if quote is not None:
            if ch == "\\":
                pos += 1
                if pos >= len(text) or text[pos] not in _ESCAPES:
                    raise ValueError("参数含未知或未完成的转义")
                chars.append(_ESCAPES[text[pos]])
            elif ch == quote:
                quote = None
            else:
                chars.append(ch)
        elif ch in "'\"":
            quote = ch
        elif ch in ",)":
            break
        elif ch == "(":
            raise ValueError("参数中的括号须放在引号内")
        else:
            chars.append(ch)
        pos += 1
    if quote is not None:
        raise ValueError("参数引号未闭合")
    return "".join(chars), pos


def _read_call(text: str, pos: int) -> tuple[Call, int]:
    match = _IDENT.match(text, pos)
    if match is None:
        raise ValueError(f"操作名非法，位置 {pos}")
    name = match.group()
    pos = _skip_space(text, match.end())
    if pos == len(text) or text[pos] != "(":
        return Call(name), pos
    pos += 1
    if pos < len(text) and text[pos] == ")":
        return Call(name), pos + 1
    args: list[str] = []
    while True:
        arg, pos = _read_argument(text, pos)
        args.append(arg)
        if pos == len(text):
            raise ValueError("调用参数括号未闭合")
        if text[pos] == ")":
            return Call(name, tuple(args)), pos + 1
        pos += 1  # 逗号；空参数保留，交由操作定义校验。


def parse_expr(spec: str) -> tuple[Call, ...]:
    """解析调用链；空串为空链，string 与其他操作一视同仁。"""
    pos = _skip_space(spec, 0)
    if pos == len(spec):
        return ()
    calls: list[Call] = []
    while True:
        call, pos = _read_call(spec, pos)
        calls.append(call)
        pos = _skip_space(spec, pos)
        if pos == len(spec):
            return tuple(calls)
        if spec[pos] != "|":
            raise ValueError(f"调用链分隔非法，位置 {pos}")
        pos = _skip_space(spec, pos + 1)
        if pos == len(spec):
            raise ValueError("调用链末尾缺少操作")


def _fmt_argument(value: str, delimiters: tuple[str, ...] = ()) -> str:
    reserved = "'\"\\,()|{}[]<>"
    if (
        value
        and not any(ch.isspace() or ch in reserved for ch in value)
        and not any(delim in value for delim in delimiters)
    ):
        return value
    quote = '"' if any(d.startswith("'") for d in delimiters) else "'"
    escaped = (
        value.replace("\\", "\\\\")
        .replace(quote, "\\" + quote)
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return quote + escaped + quote


def _fmt_expr(calls: tuple[Call, ...], delimiters: tuple[str, ...]) -> str:
    parts: list[str] = []
    for call in calls:
        if _IDENT.fullmatch(call.name) is None:
            raise ValueError(f"操作名非法：{call.name!r}")
        if not call.args:
            parts.append(call.name)
        else:
            args = ",".join(_fmt_argument(arg, delimiters) for arg in call.args)
            parts.append(f"{call.name}({args})")
    return "|".join(parts)


def fmt_expr(calls: tuple[Call, ...]) -> str:
    """调用链规范输出，不改变空调用的语义。"""
    return _fmt_expr(calls, ())


def _check_delimiters(open: str, close: str) -> None:
    if not open or not close or open == close:
        raise ValueError("占位分隔符须非空且互不相同")


def _placeholder_end(text: str, pos: int, close: str) -> int | None:
    quote: str | None = None
    annotated = False
    depth = 0
    while pos < len(text):
        ch = text[pos]
        if quote is not None:
            if ch == "\\":
                pos += 2
                continue
            if ch == quote:
                quote = None
        elif annotated and ch == ")" and depth:
            depth -= 1
        elif text.startswith(close, pos):
            return pos
        elif ch == ":":
            annotated = True
        elif annotated and ch in "'\"":
            quote = ch
        elif annotated and ch == "(":
            depth += 1
        pos += 1
    if quote is not None:
        raise ValueError("占位注解的参数引号未闭合")
    return None


def parse_template(text: str, open: str = "{", close: str = "}") -> TemplateSyntax:
    """扫描模板并保留原文区间；未闭合普通占位按字面量处理。"""
    _check_delimiters(open, close)
    parts: list[Literal | Placeholder] = []
    chars: list[str] = []
    start = pos = 0
    while pos < len(text):
        if text.startswith(open * 2, pos):
            chars.append(open)
            pos += len(open) * 2
            continue
        if text.startswith(open, pos):
            end = _placeholder_end(text, pos + len(open), close)
            if end is not None:
                if chars:
                    parts.append(Literal("".join(chars), SourceSpan(start, pos)))
                    chars = []
                content = text[pos + len(open) : end]
                name, colon, spec = content.partition(":")
                if not name:
                    raise ValueError("占位名不能为空")
                after = end + len(close)
                parts.append(
                    Placeholder(
                        name,
                        parse_expr(spec) if colon else None,
                        SourceSpan(pos, after),
                    )
                )
                pos = start = after
                continue
        if text.startswith(close * 2, pos):
            chars.append(close)
            pos += len(close) * 2
            continue
        chars.append(text[pos])
        pos += 1
    if chars:
        parts.append(Literal("".join(chars), SourceSpan(start, pos)))
    return TemplateSyntax(text, tuple(parts), open, close)


def escape_literal(text: str, open: str = "{", close: str = "}") -> str:
    """把字面量编码为模板文本，转义当前分隔符。"""
    _check_delimiters(open, close)
    parts: list[str] = []
    pos = 0
    while pos < len(text):
        if text.startswith(open, pos):
            parts.append(open * 2)
            pos += len(open)
        elif text.startswith(close, pos):
            parts.append(close * 2)
            pos += len(close)
        else:
            parts.append(text[pos])
            pos += 1
    return "".join(parts)


def fmt_placeholder(
    name: str,
    annotation: tuple[Call, ...] | None = None,
    open: str = "{",
    close: str = "}",
) -> str:
    """占位规范输出；参数编码遵循同一调用语法。"""
    _check_delimiters(open, close)
    if not name or ":" in name or open in name or close in name:
        raise ValueError(f"占位名非法：{name!r}")
    return _placeholder_text(name, annotation, open, close)


def fmt_draft_placeholder(
    name: str,
    annotation: tuple[Call, ...] | None = None,
    open: str = "{",
    close: str = "}",
) -> str:
    """打印未完成编辑，名字原样保留；结果不保证可执行。"""
    _check_delimiters(open, close)
    return _placeholder_text(name, annotation, open, close)


def _placeholder_text(
    name: str, annotation: tuple[Call, ...] | None, open: str, close: str
) -> str:
    spec = "" if annotation is None else ":" + _fmt_expr(annotation, (open, close))
    return open + name + spec + close


def fmt_template(syntax: TemplateSyntax) -> str:
    """规范化整份模板；原样读取使用 source 与节点 span。"""
    return "".join(
        escape_literal(part.text, syntax.open, syntax.close)
        if isinstance(part, Literal)
        else fmt_placeholder(part.name, part.annotation, syntax.open, syntax.close)
        for part in syntax.parts
    )
