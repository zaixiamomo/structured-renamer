"""组合模板、mapping 和 wire 的不可变编译结果"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict

from renamer.core.dsl.format import BoundTransform, compile_expr
from renamer.core.model import (
    Capability,
    Issue,
    Level,
    Library,
    PlanError,
    Rule,
)

from .mapping import CompiledMapping, compile_mappings
from .template import CompiledParseTemplate, CompiledRenderTemplate, TemplateCompiler
from .wire import CompiledWire, compile_wire

__all__ = ["Plan", "compile_rule"]


class Plan(BaseModel):
    """可跨文件复用的编译快照，文件值和能力调用结果保存在运行态"""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    parse: CompiledParseTemplate
    render: CompiledRenderTemplate
    mapping: CompiledMapping
    wire: CompiledWire
    output_steps: tuple[BoundTransform, ...] = ()


def compile_rule(
    rule: Rule, library: Library, capabilities: Mapping[str, Capability]
) -> Plan:
    """组合规则的模板、绑定、能力候选与整串格式步骤

    Args:
        rule: 目标规则，模板名按解析和渲染角色分别引用
        library: 命名模板库
        capabilities: 能力注册表，映射插入顺序为注册顺序

    Returns:
        可跨文件复用的不可变 Plan

    Raises:
        PlanError: 模板、格式、mapping 或接线校验失败
    """
    issues: list[Issue] = []
    parse_template = library.parse_templates.get(rule.parse_template)
    if parse_template is None:
        issues.append(
            Issue(
                level=Level.ERROR,
                code="template_not_found",
                message=f"解析模板 {rule.parse_template!r} 未注册（或误引用了渲染模板名）",
            )
        )
    render_template = library.render_templates.get(rule.render_template)
    if render_template is None:
        issues.append(
            Issue(
                level=Level.ERROR,
                code="template_not_found",
                message=f"渲染模板 {rule.render_template!r} 未注册（或误引用了解析模板名）",
            )
        )

    output_steps: tuple[BoundTransform, ...] = ()
    try:
        output_steps = compile_expr(rule.format)
    except ValueError as exc:
        issues.append(
            Issue(
                level=Level.ERROR,
                code="rule_format_error",
                message=f"规则 {rule.name!r} 的输出格式非法：{exc}",
            )
        )
    if issues:
        raise PlanError(issues)

    parse = TemplateCompiler.compile_parse(parse_template)
    render = TemplateCompiler.compile_render(render_template)
    mapping = compile_mappings(
        rule.mappings,
        parse_tokens=parse.tokens,
        render_tokens=render.tokens,
    )
    wire = compile_wire(
        required=mapping.required,
        seed_fields=mapping.seed_fields,
        aliases=mapping.field_aliases,
        calls=rule.capabilities,
        registry=capabilities,
    )
    return Plan(
        parse=parse,
        render=render,
        mapping=mapping,
        wire=wire,
        output_steps=output_steps,
    )
