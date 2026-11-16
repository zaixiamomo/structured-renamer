"""统一模板语法的编辑视图：保留原始位置与解码文本。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from renamer.core.dsl.syntax import Call, Literal, Placeholder, fmt_expr, parse_template
from renamer.core.model.issue import Issue, Level

__all__ = [
    "Literal",
    "Segment",
    "SegmentedText",
    "Span",
    "segment",
    "tokenize",
]


Segment: TypeAlias = Literal | Placeholder


def tokenize(text: str, open: str = "{", close: str = "}") -> list[Segment]:
    """模板分词直接使用统一 AST，不再持有另一套 token 文法。"""
    return list(parse_template(text, open, close).parts)


@dataclass(frozen=True)
class Span:
    """作者视图；s/e 为原文闭区间，注解只存 AST。

    字面量的 text 是解码值，raw 是原始文本；token 的 text 保留占位原文。
    SourceTemplate 标注示例文件时，text/raw 则为被标注的示例字符。
    """

    kind: str
    s: int
    e: int
    text: str
    name: str | None = None
    annotation: tuple[Call, ...] | None = None
    raw: str = ""

    def is_token(self) -> bool:
        return self.kind == "tok"

    @property
    def type(self) -> str | None:
        """旧 GUI 的只读适配；渲染注解返回完整表达式。"""
        if not self.is_token():
            return None
        if not self.annotation:
            return "string"
        if len(self.annotation) == 1 and self.annotation[0].name == "enum":
            return "enum"
        return fmt_expr(self.annotation)

    @property
    def values(self) -> tuple[str, ...] | None:
        """旧 GUI 的 enum 参数视图；不另存候选值副本。"""
        if not self.is_token():
            return None
        if self.annotation and len(self.annotation) == 1:
            call = self.annotation[0]
            if call.name == "enum":
                return call.args
        return ()


@dataclass(frozen=True)
class SegmentedText:
    """原文及其编辑视图；语法不完整时保留整份草稿并附诊断。"""

    chars: tuple[str, ...]
    spans: tuple[Span, ...] = ()
    issues: tuple[Issue, ...] = ()

    def token_of(self) -> list[int | None]:
        """每个原文字符所属的 span 序号（字面量为 None）。"""
        out: list[int | None] = [None] * len(self.chars)
        for idx, sp in enumerate(self.spans):
            if sp.is_token():
                for i in range(max(0, sp.s), min(sp.e, len(self.chars) - 1) + 1):
                    out[i] = idx
        return out


def segment(text: str, open: str = "{", close: str = "}") -> SegmentedText:
    """从原始范围构造编辑视图；错误草稿保留原文，严格编译使用 tokenize。"""
    try:
        syntax = parse_template(text, open, close)
    except ValueError as exc:
        return SegmentedText(
            chars=tuple(text),
            spans=(Span("lit", 0, len(text) - 1, text, raw=text),),
            issues=(
                Issue(
                    level=Level.ERROR, code="template_syntax_error", message=str(exc)
                ),
            ),
        )
    spans: list[Span] = []
    for part in syntax.parts:
        assert part.span is not None  # parser 产物总有原文区间
        start, end = part.span.start, part.span.end
        raw = text[start:end]
        if isinstance(part, Literal):
            spans.append(Span("lit", start, end - 1, part.text, raw=raw))
        else:
            spans.append(
                Span(
                    "tok",
                    start,
                    end - 1,
                    raw,
                    name=part.name,
                    annotation=part.annotation,
                    raw=raw,
                )
            )
    return SegmentedText(tuple(text), tuple(spans))
