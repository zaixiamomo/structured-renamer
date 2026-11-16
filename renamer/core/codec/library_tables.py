"""Library 文件结构的双向转换，负责表字段、默认值与声明校验"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NoReturn

from pydantic import ValidationError

from renamer.core.dsl import fmt_mapping, parse_mapping
from renamer.core.model import (
    CapabilityCall,
    Issue,
    Level,
    Library,
    ParseTemplate,
    PlanError,
    RenderTemplate,
    Rule,
    TokenMapping,
)
from renamer.core.model.template import (
    DEFAULT_DELIM_CLOSE,
    DEFAULT_DELIM_OPEN,
)


def library_from_tables(data: Mapping[str, Any]) -> Library:
    """把已解析的表数据转换为声明，结构非法时抛 rule_load_failed"""
    parse_templates: dict[str, ParseTemplate] = {}
    render_templates: dict[str, RenderTemplate] = {}
    rules: dict[str, Rule] = {}
    for spec in _section_list(data, "parse_template"):
        name, template = _template_from_table(spec, ParseTemplate)
        parse_templates[name] = template
    for spec in _section_list(data, "render_template"):
        name, template = _template_from_table(spec, RenderTemplate)
        render_templates[name] = template
    for spec in _section_list(data, "rule"):
        name, rule = _rule_from_table(spec)
        rules[name] = rule
    return Library(
        parse_templates=parse_templates,
        render_templates=render_templates,
        rules=rules,
    )


def library_to_tables(library: Library) -> dict[str, list[dict[str, Any]]]:
    """按固定段落与字段顺序生成表数据，省略默认值和空的可选项"""
    return {
        "parse_template": [
            _template_to_table(name, template)
            for name, template in library.parse_templates.items()
        ],
        "render_template": [
            _template_to_table(name, template)
            for name, template in library.render_templates.items()
        ],
        "rule": [_rule_to_table(name, rule) for name, rule in library.rules.items()],
    }


def _template_to_table(
    name: str, template: ParseTemplate | RenderTemplate
) -> dict[str, Any]:
    table: dict[str, Any] = {"name": name, "text": template.text}
    if template.open != DEFAULT_DELIM_OPEN:
        table["open"] = template.open
    if template.close != DEFAULT_DELIM_CLOSE:
        table["close"] = template.close
    return table


def _rule_to_table(name: str, rule: Rule) -> dict[str, Any]:
    table: dict[str, Any] = {
        "name": name,
        "parse_template": rule.parse_template,
        "render_template": rule.render_template,
    }
    if rule.mappings:
        table["mapping"] = [fmt_mapping(item) for item in rule.mappings]
    if rule.capabilities:
        table["capabilities"] = [_capcall_to_dict(call) for call in rule.capabilities]
    if rule.format:
        table["format"] = rule.format
    return table


def _section_list(data: Mapping[str, Any], key: str) -> list[Any]:
    value = data.get(key, [])
    if not isinstance(value, list):
        _raise_load(f"顶层 {key!r} 必须是数组（请用 [[{key}]] 表）")
    return value


def _template_from_table(
    spec: Any, model: type[ParseTemplate | RenderTemplate]
) -> tuple[str, ParseTemplate | RenderTemplate]:
    if not isinstance(spec, Mapping):
        _raise_load("template 表项必须为 table")
    name = spec.get("name")
    if not isinstance(name, str) or not name:
        _raise_load(f"template 缺少合法 name：{name!r}")
    text = spec.get("text")
    if not isinstance(text, str):
        _raise_load(f"template {name!r} 缺少 text 或类型错误")
    open_ = spec.get("open", DEFAULT_DELIM_OPEN)
    close_ = spec.get("close", DEFAULT_DELIM_CLOSE)
    if not isinstance(open_, str) or not isinstance(close_, str):
        _raise_load(f"template {name!r} 的 open/close 必须为字符串")
    try:
        template = model(text=text, open=open_, close=close_)
    except ValidationError as exc:
        _raise_load(f"template {name!r} 非法：{exc}")
    return name, template


def _rule_from_table(spec: Any) -> tuple[str, Rule]:
    if not isinstance(spec, Mapping):
        _raise_load("rule 表项必须为 table")
    name = spec.get("name")
    if not isinstance(name, str) or not name:
        _raise_load(f"rule 缺少合法 name：{name!r}")
    parse_template = spec.get("parse_template")
    render_template = spec.get("render_template")
    if not isinstance(parse_template, str) or not parse_template:
        _raise_load(f"rule {name!r} 缺少 parse_template 或类型错误")
    if not isinstance(render_template, str) or not render_template:
        _raise_load(f"rule {name!r} 缺少 render_template 或类型错误")

    mapping_spec = spec.get("mapping", [])
    if not isinstance(mapping_spec, list):
        _raise_load(f"rule {name!r} 的 mapping 必须为字符串数组")
    mappings: list[TokenMapping] = []
    for item in mapping_spec:
        if not isinstance(item, str):
            _raise_load(f"rule {name!r} 的 mapping 项必须为字符串：{item!r}")
        try:
            mappings.append(parse_mapping(item))
        except (ValueError, ValidationError) as exc:
            _raise_load(f"rule {name!r} 的 mapping {item!r} 非法：{exc}")

    capabilities_spec = spec.get("capabilities", [])
    if not isinstance(capabilities_spec, list):
        _raise_load(f"rule {name!r} 的 capabilities 必须为 inline table 数组")
    capabilities = tuple(_capcall_from_table(c, name) for c in capabilities_spec)

    format_spec = spec.get("format", "")
    if not isinstance(format_spec, str):
        _raise_load(f"rule {name!r} 的 format 必须为字符串")

    return name, Rule(
        name=name,
        parse_template=parse_template,
        render_template=render_template,
        mappings=tuple(mappings),
        capabilities=capabilities,
        format=format_spec,
    )


def _capcall_from_table(spec: Any, rule_name: str) -> CapabilityCall:
    if not isinstance(spec, Mapping):
        _raise_load(f"rule {rule_name!r} 的 capability 必须为 inline table")
    func = spec.get("func")
    if not isinstance(func, str) or not func:
        _raise_load(f"rule {rule_name!r} 的 capability 缺少 func")
    out_spec = spec.get("out", [])
    if not isinstance(out_spec, list):
        _raise_load(f"rule {rule_name!r} 的 capability out 必须为字符串数组")
    out: list[str] = []
    for item in out_spec:
        if not isinstance(item, str):
            _raise_load(
                f"rule {rule_name!r} 的 capability out 项必须为字符串：{item!r}"
            )
        out.append(item)
    return CapabilityCall(func=func, out=tuple(out))


def _capcall_to_dict(call: CapabilityCall) -> dict[str, Any]:
    result: dict[str, Any] = {"func": call.func}
    if call.out:
        result["out"] = list(call.out)
    return result


def _raise_load(message: str) -> NoReturn:
    raise PlanError(
        [Issue(level=Level.ERROR, code="rule_load_failed", message=message)]
    )
