"""共享模板语法，分别编译捕获约束与逐引用渲染程序。"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import lru_cache

from renamer.core.dsl.capture import (
    BoundCapture,
    CaptureError,
    adjacent_capture_conflicts,
    bind_capture,
)
from renamer.core.dsl.format import BoundTransform, apply_bound, compile_chain
from renamer.core.dsl.syntax import (
    Call,
    Literal,
    Placeholder,
    TemplateSyntax,
    parse_template,
)
from renamer.core.model import Issue, Level, PlanError, Template

__all__ = [
    "CompiledParseTemplate",
    "CompiledRenderTemplate",
    "ParseFragment",
    "TemplateCompiler",
    "reverse_fragment",
]


@dataclass(frozen=True)
class ParseFragment:
    """原始捕获值、输入中的闭区间，以及捕获定义的元数据。"""

    values: dict[str, str]
    spans: tuple[tuple[str, int, int], ...]
    spec_types: dict[str, str]
    annotations: dict[str, tuple[Call, ...] | None]


@dataclass(frozen=True)
class CompiledParseTemplate:
    syntax: TemplateSyntax
    captures: tuple[BoundCapture, ...]
    pattern: re.Pattern[str]

    @property
    def tokens(self) -> tuple[str, ...]:
        return self.syntax.tokens

    def parse(self, text: str) -> dict[str, str] | None:
        """全串匹配，始终返回原始字符串，不转换数字或日期。"""
        match = self.pattern.fullmatch(text)
        return None if match is None else dict(zip(self.tokens, match.groups()))

    def fragment(self, text: str) -> ParseFragment | None:
        match = self.pattern.fullmatch(text)
        if match is None:
            return None
        placeholders = tuple(
            part for part in self.syntax.parts if isinstance(part, Placeholder)
        )
        return ParseFragment(
            values=dict(zip(self.tokens, match.groups())),
            spans=tuple(
                (name, match.start(index), match.end(index) - 1)
                for index, name in enumerate(self.tokens, 1)
            ),
            spec_types={
                name: capture.field_type
                for name, capture in zip(self.tokens, self.captures)
            },
            annotations={part.name: part.annotation for part in placeholders},
        )


@dataclass(frozen=True)
class RenderField:
    name: str
    steps: tuple[BoundTransform, ...]


@dataclass(frozen=True)
class CompiledRenderTemplate:
    syntax: TemplateSyntax
    parts: tuple[Literal | RenderField, ...]

    @property
    def tokens(self) -> tuple[str, ...]:
        return self.syntax.tokens

    def render(self, values: Mapping[str, str] | Callable[[str], str | None]) -> str:
        """唯一渲染入口：按每次引用执行绑定步骤，缺值留空。"""
        resolve = values.get if isinstance(values, Mapping) else values
        result: list[str] = []
        for part in self.parts:
            if isinstance(part, Literal):
                result.append(part.text)
            else:
                raw = resolve(part.name)
                result.append("" if raw is None else apply_bound(raw, part.steps))
        return "".join(result)


def _issue(code: str, message: str) -> Issue:
    return Issue(level=Level.ERROR, code=code, message=message)


@lru_cache(maxsize=256)
def _read_syntax(template: Template) -> TemplateSyntax:
    return parse_template(template.text, template.open, template.close)


def _syntax_for(template: Template, code: str) -> TemplateSyntax:
    try:
        return _read_syntax(template)
    except ValueError as exc:
        raise PlanError([_issue(code, str(exc))]) from exc


class TemplateCompiler:
    """编译入口按角色分开；成功产物不再包含未解释的格式字符串。"""

    @staticmethod
    @lru_cache(maxsize=256)
    def compile_parse(template: Template) -> CompiledParseTemplate:
        syntax = _syntax_for(template, "template_syntax_error")
        issues: list[Issue] = []
        seen: set[str] = set()
        captures: list[BoundCapture] = []
        constraints: list[tuple[bool, bool]] = []
        adjacent_pairs: list[tuple[int, int]] = []
        names: list[str] = []
        pattern: list[str] = []
        for part in syntax.parts:
            if isinstance(part, Literal):
                constraints.append((False, False))
                pattern.append(re.escape(part.text))
                continue
            if constraints and constraints[-1][0]:
                adjacent_pairs.append((len(names) - 1, len(names)))
            names.append(part.name)
            try:
                capture = bind_capture(part.annotation)
            except CaptureError as exc:
                issues.append(_issue(exc.code, f"模板 token {part.name!r}：{exc}"))
                constraints.append((True, False))
            else:
                captures.append(capture)
                constraints.append((True, capture.discriminable))
                pattern.append("(" + capture.pattern + ")")
            if part.name in seen:
                issues.append(
                    _issue(
                        "template_duplicate_token",
                        f"模板含重复 token 名 {part.name!r}，同名 token 会丢失解析结果",
                    )
                )
            seen.add(part.name)

        conflicts = adjacent_capture_conflicts(constraints)
        for previous, index in adjacent_pairs:
            if previous in conflicts and index in conflicts:
                issues.append(
                    _issue(
                        "template_adjacent_token",
                        f"相邻 token {names[previous]!r} 与 {names[index]!r} 之间缺少字面量分隔",
                    )
                )
        if issues:
            raise PlanError(issues)
        return CompiledParseTemplate(
            syntax, tuple(captures), re.compile("".join(pattern))
        )

    @staticmethod
    @lru_cache(maxsize=256)
    def compile_render(template: Template) -> CompiledRenderTemplate:
        syntax = _syntax_for(template, "render_format_error")
        issues: list[Issue] = []
        parts: list[Literal | RenderField] = []
        for part in syntax.parts:
            if isinstance(part, Literal):
                parts.append(part)
                continue
            try:
                steps = compile_chain(part.annotation or ())
            except ValueError as exc:
                issues.append(
                    _issue(
                        "render_format_error", f"渲染模板 token {part.name!r}：{exc}"
                    )
                )
            else:
                parts.append(RenderField(part.name, steps))
        if issues:
            raise PlanError(issues)
        return CompiledRenderTemplate(syntax, tuple(parts))

    @classmethod
    def validate_parse(cls, template: Template) -> list[Issue]:
        """供编辑端收集诊断；执行与诊断共用编译规则。"""
        try:
            cls.compile_parse(template)
        except PlanError as exc:
            return exc.issues
        return []


def reverse_fragment(template: Template, stem: str) -> ParseFragment | None:
    """输入中的捕获位置直接来自匹配结果，不从规范模板推算。"""
    return TemplateCompiler.compile_parse(template).fragment(stem)
