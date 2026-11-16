"""结合模板解释 mapping 简写，分别编译字段种子和渲染绑定"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict

from renamer.core.model import FieldKey, Issue, Level, PlanError, TokenMapping

__all__ = ["CompiledMapping", "Slot", "compile_mappings"]


class Slot(BaseModel):
    """渲染引用的取值来源，捕获原值优先于补全字段"""

    model_config = ConfigDict(frozen=True)

    parse_token: str | None = None
    field_key: FieldKey | None = None


@dataclass(frozen=True)
class CompiledMapping:
    """只读绑定结果，渲染绑定保留未引用的显式别名供能力 out 查找"""

    seed_bindings: Mapping[FieldKey, str]
    render_bindings: Mapping[str, Slot]
    required: tuple[FieldKey, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "seed_bindings", MappingProxyType(dict(self.seed_bindings))
        )
        object.__setattr__(
            self, "render_bindings", MappingProxyType(dict(self.render_bindings))
        )
        object.__setattr__(self, "required", tuple(self.required))

    @property
    def seed_fields(self) -> frozenset[FieldKey]:
        return frozenset(self.seed_bindings)

    @property
    def field_aliases(self) -> Mapping[str, FieldKey]:
        """字段别名包括未渲染的显式声明，供能力输出引用"""
        return MappingProxyType(
            {
                name: slot.field_key
                for name, slot in self.render_bindings.items()
                if slot.field_key is not None
            }
        )

    def seed_values(self, parsed: Mapping[str, str]) -> dict[FieldKey, str]:
        """按字段绑定读取捕获值，空串合法"""
        return {
            field: parsed[token]
            for field, token in self.seed_bindings.items()
            if token in parsed
        }

    def render_value(
        self,
        token: str,
        parsed: Mapping[str, str],
        fields: Mapping[FieldKey, str],
    ) -> str | None:
        """捕获原值优先于补全字段，双缺返回 None"""
        slot = self.render_bindings.get(token)
        if slot is None:
            return None
        if slot.parse_token is not None and slot.parse_token in parsed:
            return parsed[slot.parse_token]
        if slot.field_key is not None and slot.field_key in fields:
            return fields[slot.field_key]
        return None


def compile_mappings(
    mappings: Iterable[TokenMapping],
    *,
    parse_tokens: Iterable[str],
    render_tokens: Iterable[str],
) -> CompiledMapping:
    """按模板上下文解释简写，校验冲突并编译两类绑定

    Args:
        mappings: 手写或程序生成的 mapping 声明
        parse_tokens: 解析模板捕获名
        render_tokens: 渲染模板引用名，顺序用于确定 required

    Returns:
        字段种子、渲染绑定及必需字段的只读编译结果

    Raises:
        PlanError: 显式绑定冲突或渲染引用没有值来源
    """
    captured = set(parse_tokens)
    referenced = tuple(dict.fromkeys(render_tokens))
    seeds: dict[FieldKey, str] = {}
    explicit: dict[str, Slot] = {}
    issues: list[Issue] = []

    for mapping in mappings:
        # 简写左侧被模板捕获时才形成解析来源
        parse_token = mapping.parse_token if mapping.parse_token in captured else None
        render_token = mapping.render_token
        slot = Slot(parse_token=parse_token, field_key=mapping.field_key)
        previous = explicit.get(render_token)
        if previous is not None and previous != slot:
            issues.append(
                Issue(
                    level=Level.ERROR,
                    code="conflicting_render_binding",
                    message=(
                        f"渲染 token {render_token!r} 的显式绑定冲突："
                        f"{_describe_slot(previous)} 与 {_describe_slot(slot)}"
                    ),
                )
            )
        else:
            explicit[render_token] = slot

        field_key = mapping.field_key
        if parse_token is not None and field_key is not None:
            previous_token = seeds.get(field_key)
            if previous_token is not None and previous_token != parse_token:
                issues.append(
                    Issue(
                        level=Level.ERROR,
                        code="conflicting_seed_binding",
                        message=(
                            f"字段 {field_key} 同时绑定解析 token "
                            f"{previous_token!r} 和 {parse_token!r}"
                        ),
                    )
                )
            else:
                seeds[field_key] = parse_token

    # 显式声明优先，缺省同名透传只补充未声明的渲染引用
    render_bindings: dict[str, Slot] = {}
    required: dict[FieldKey, None] = {}
    for token in referenced:
        slot = explicit.get(token)
        if slot is None:
            if token in captured:
                slot = Slot(parse_token=token)
            else:
                issues.append(
                    Issue(
                        level=Level.ERROR,
                        code="no_value_source",
                        message=f"渲染 token {token!r} 无值来源（既未被解析捕获，也无 mapping）",
                    )
                )
                continue
        elif slot.parse_token is None and slot.field_key is None:
            issues.append(
                Issue(
                    level=Level.ERROR,
                    code="unresolved_mapping",
                    message=(
                        f"mapping 对渲染 token {token!r} 未能解析出任何值来源"
                        f"（parse_token 未捕获且无 field_key）"
                    ),
                )
            )
        render_bindings[token] = slot
        if slot.field_key is not None:
            required[slot.field_key] = None

    if issues:
        raise PlanError(issues)

    # 未渲染的显式别名仍可能用于手动能力的 out
    render_bindings.update(explicit)
    return CompiledMapping(
        seed_bindings=seeds,
        render_bindings=render_bindings,
        required=tuple(required),
    )


def _describe_slot(slot: Slot) -> str:
    """描述冲突绑定中的解析来源和规范字段"""
    return f"解析来源 {slot.parse_token!r}、字段 {slot.field_key}"
