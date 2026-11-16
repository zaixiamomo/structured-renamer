"""规则草稿、编辑操作及声明转换，示例值不决定绑定或能力是否存在"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from renamer.core.model import (
    Capability,
    CapabilityCall,
    FieldKey,
    Issue,
    Level,
    Library,
    PlanError,
    RenderTemplate,
    Rule,
    TokenMapping,
)
from renamer.core.model.template import ParseTemplate

from .binding import Binding
from .segment import segment

__all__ = ["SourceRule", "SourceRuleToken", "render_template_name"]


def render_template_name(rule_name: str) -> str:
    """渲染模板名派生：``{name}__render``（与规则名一一对应）"""
    return f"{rule_name or 'rule'}__render"


@dataclass
class SourceRuleToken:
    """规则编辑期的单个词段（parse / enrich 统一），绑定收口进 Binding"""

    id: int
    kind: str  # "parse" | "enrich"
    type: str  # 类型串（对齐 FieldType.value）
    binding: Binding  # parse_token / render_token / field_key
    cap_id: str | None = None  # 产出本词的能力 id（enrich 词）
    # 显式映射始终导出，派生词段按绑定和渲染引用决定是否导出
    explicit_mapping: bool = False

    @property
    def render_name(self) -> str:
        """渲染引用名（进组合框的 {name}）"""
        return self.binding.effective_render_token() or ""


@dataclass
class SourceRule:
    """持有可编辑的规则声明，能力调用按列表保存，空列表表示自动接线"""

    name: str = ""
    parse_name: str | None = None
    parse_template: ParseTemplate | None = None
    tokens: dict[int, SourceRuleToken] = field(default_factory=dict)
    render_text: str = ""
    format: str = ""
    render_name: str | None = None
    render_open: str = "{"
    render_close: str = "}"
    capability_calls: list[CapabilityCall] = field(default_factory=list)
    _next_id: int = field(default=0, init=False, repr=False)

    def new_token_id(self) -> int:
        self._next_id = max(self._next_id, max(self.tokens, default=0)) + 1
        return self._next_id

    def unique_render_name(self, base: str) -> str:
        used = {token.render_name for token in self.tokens.values()}
        name, suffix = base, 1
        while name in used:
            suffix += 1
            name = f"{base}{suffix}"
        return name

    def set_parse_template(
        self, name: str | None, template: ParseTemplate | None
    ) -> None:
        """按捕获名协调声明；同名词段保留 id、别名和字段绑定"""
        self.parse_name = name
        self.parse_template = template
        spans = (
            segment(template.text, template.open, template.close).spans
            if template is not None
            else ()
        )
        captures = {span.name: span for span in spans if span.is_token()}
        # 只删除模板自动派生且没有任何额外语义的旧词段，显式声明仍可诊断
        for tid, token in list(self.tokens.items()):
            if (
                token.kind == "parse"
                and token.binding.parse_token not in captures
                and not token.explicit_mapping
                and token.binding.field_key is None
                and token.binding.is_identity()
            ):
                del self.tokens[tid]
        known = {
            token.binding.parse_token
            for token in self.tokens.values()
            if token.kind == "parse"
        }
        for token in self.tokens.values():
            if token.binding.parse_token in captures:
                token.kind = "parse"
                token.type = captures[token.binding.parse_token].type or "string"
                known.add(token.binding.parse_token)
        for capture, span in captures.items():
            if capture in known:
                continue
            tid = self.new_token_id()
            self.tokens[tid] = SourceRuleToken(
                id=tid,
                kind="parse",
                type=span.type or "string",
                binding=Binding(parse_token=capture),
                explicit_mapping=False,
            )

    def bind_input(self, field_key: FieldKey | str, tid: int) -> None:
        """替换字段的解析种子；能力输出只能接入自身声明的同名字段"""
        key = FieldKey.parse(field_key) if isinstance(field_key, str) else field_key
        token = self.tokens[tid]
        if token.kind != "parse":
            if token.binding.field_key != key:
                raise ValueError("能力输出只能接入其声明的同名字段")
            self.unbind_input(key)
            return
        self.unbind_input(key)
        token.binding.field_key = key
        token.explicit_mapping = True

    def unbind_input(self, field_key: FieldKey | str) -> None:
        """清除该字段的解析种子，不修改能力输出的字段身份"""
        key = FieldKey.parse(field_key) if isinstance(field_key, str) else field_key
        for token in self.tokens.values():
            if token.kind == "parse" and token.binding.field_key == key:
                token.binding.field_key = None

    def input_bindings(self) -> dict[FieldKey, int]:
        """供视图展示的字段索引，真实解析种子优先于能力输出引用"""
        captured = set()
        if self.parse_template is not None:
            template = self.parse_template
            captured = {
                span.name
                for span in segment(template.text, template.open, template.close).spans
                if span.is_token()
            }
        result: dict[FieldKey, int] = {}
        for tid, token in self.tokens.items():
            key = token.binding.field_key
            if key is not None and token.kind != "parse":
                result.setdefault(key, tid)
        for tid, token in self.tokens.items():
            key = token.binding.field_key
            if key is not None and token.binding.parse_token in captured:
                result[key] = tid
        return result

    def add_capability(
        self, cap: Capability, field_types: Mapping[str, str] | None = None
    ) -> dict[FieldKey, int]:
        """声明能力及其全部输出，返回本能力的字段到词段 id 索引"""
        existing = next(
            (call for call in self.capability_calls if call.func == cap.id), None
        )
        if existing is None:
            self.capability_calls.append(
                CapabilityCall(func=cap.id, out=tuple(str(key) for key in cap.outputs))
            )
        declared = self.capability_output_fields(cap.id)
        outputs = {
            token.binding.field_key: tid
            for tid, token in self.tokens.items()
            if token.cap_id == cap.id and token.binding.field_key is not None
        }
        for key in cap.outputs:
            if key not in declared or key in outputs:
                continue
            tid = self.new_token_id()
            name = self.unique_render_name(key.field.lower())
            self.tokens[tid] = SourceRuleToken(
                id=tid,
                kind="enrich",
                type=(field_types or {}).get(str(key), "string"),
                binding=Binding(render_token=name, field_key=key),
                cap_id=cap.id,
                explicit_mapping=False,
            )
            outputs[key] = tid
        return outputs

    def capability_output_fields(self, cap_id: str) -> set[FieldKey]:
        """解析调用实际声明的输出字段，保留部分输出及别名的含义。"""
        aliases = {
            token.render_name: token.binding.field_key for token in self.tokens.values()
        }
        fields = set()
        for call in self.capability_calls:
            if call.func != cap_id:
                continue
            for output in call.out:
                text = output.strip()
                try:
                    key = FieldKey.parse(text) if ":" in text else aliases.get(text)
                except ValueError:
                    continue
                if key is not None:
                    fields.add(key)
        return fields

    def clear_capability_outputs(self, cap_ids: set[str]) -> None:
        """清理指定能力的产出词段及专属引用，保留调用及输出字段。"""
        removed = {
            tid: token
            for tid, token in self.tokens.items()
            if token.kind == "enrich" and token.cap_id in cap_ids
        }
        if not removed:
            return
        aliases = {
            token.render_name: str(token.binding.field_key)
            for token in removed.values()
            if token.binding.field_key is not None
        }
        # out 可引用即将删除的别名；先转回字段，避免留下悬空声明。
        self.capability_calls = [
            call.model_copy(
                update={"out": tuple(aliases.get(out.strip(), out) for out in call.out)}
            )
            for call in self.capability_calls
        ]
        for tid in removed:
            del self.tokens[tid]
        names = {token.render_name for token in removed.values()}
        names.difference_update(token.render_name for token in self.tokens.values())
        if self.parse_template is not None:
            template = self.parse_template
            names.difference_update(
                span.name
                for span in segment(template.text, template.open, template.close).spans
                if span.is_token()
            )
        for span in reversed(
            segment(self.render_text, self.render_open, self.render_close).spans
        ):
            if span.is_token() and span.name in names:
                self.render_text = (
                    self.render_text[: span.s] + self.render_text[span.e + 1 :]
                )

    def remove_capability(self, cap_id: str) -> None:
        """删除能力调用及其产出词段，清除专属渲染引用。"""
        self.clear_capability_outputs({cap_id})
        self.capability_calls[:] = [
            call for call in self.capability_calls if call.func != cap_id
        ]

    def to_rule(self) -> Rule:
        """将编辑绑定转为 mapping，按原序保留能力调用声明"""
        mappings: list[TokenMapping] = []
        used = {
            span.name
            for span in segment(
                self.render_text, self.render_open, self.render_close
            ).spans
            if span.is_token()
        }
        for tok in self.tokens.values():
            binding = tok.binding
            if tok.explicit_mapping:
                mappings.append(binding.to_mapping())
                continue
            if tok.kind == "parse":
                # 恒等且未绑定字段的解析词段由 mapping 编译补充同名透传
                if binding.field_key is None and binding.is_identity():
                    continue
            elif binding.field_key is None:
                # enrich 词段未绑定字段不产出映射
                continue
            elif tok.render_name not in used:
                # 输出声明可独立于渲染别名存在，能力 out 使用规范字段名
                continue
            mappings.append(binding.to_mapping())

        return Rule(
            name=self.name,
            parse_template=self.parse_name or "",
            render_template=self.render_name or render_template_name(self.name),
            mappings=tuple(mappings),
            capabilities=tuple(self.capability_calls),
            format=self.format,
        )

    def to_library(self) -> Library:
        """将草稿中的模板与规则声明组装为 Library"""
        parse_templates: dict[str, ParseTemplate] = {}
        if self.parse_name and isinstance(self.parse_template, ParseTemplate):
            parse_templates[self.parse_name] = self.parse_template
        render_templates: dict[str, RenderTemplate] = {
            self.render_name or render_template_name(self.name): RenderTemplate(
                text=self.render_text,
                open=self.render_open,
                close=self.render_close,
            )
        }
        return Library(
            parse_templates=parse_templates,
            render_templates=render_templates,
            rules={self.name: self.to_rule()},
        )

    @classmethod
    def from_rule(cls, rule: Rule, library: Library) -> SourceRule:
        """恢复草稿并保留映射顺序、能力输出原文和模板角色

        未知或未使用的声明仍可编辑和导出，执行合法性由 Plan 编译检查

        Args:
            rule: 已保存的规则声明
            library: 提供解析和渲染模板的库

        Returns:
            不依赖示例或能力实现的独立草稿

        Raises:
            PlanError: 缺少规则引用的模板
        """
        parse_template = library.parse_templates.get(rule.parse_template)
        render_template = library.render_templates.get(rule.render_template)
        if parse_template is None or render_template is None:
            missing = []
            if parse_template is None:
                missing.append(f"解析模板 {rule.parse_template!r}")
            if render_template is None:
                missing.append(f"渲染模板 {rule.render_template!r}")
            raise PlanError(
                [
                    Issue(
                        level=Level.ERROR,
                        code="template_not_found",
                        message="无法恢复规则，缺少" + "、".join(missing),
                    )
                ]
            )
        source = cls(
            name=rule.name,
            parse_name=rule.parse_template,
            parse_template=parse_template,
            render_name=rule.render_template,
            render_text=render_template.text,
            render_open=render_template.open,
            render_close=render_template.close,
            format=rule.format,
            capability_calls=list(rule.capabilities),
        )
        captures = {
            span.name
            for span in segment(
                parse_template.text, parse_template.open, parse_template.close
            ).spans
            if span.is_token()
        }
        for mapping in rule.mappings:
            tid = source.new_token_id()
            source.tokens[tid] = SourceRuleToken(
                id=tid,
                kind="parse" if mapping.parse_token in captures else "enrich",
                type="string",
                binding=Binding(
                    parse_token=mapping.parse_token,
                    render_token=mapping.render_token,
                    field_key=mapping.field_key,
                ),
                explicit_mapping=True,
            )
        source.set_parse_template(rule.parse_template, parse_template)

        aliases = {
            token.render_name: token.binding.field_key
            for token in source.tokens.values()
        }
        # 同字段不同能力是不同输出声明；额外编辑词段不增加原 Rule 的 mapping
        outputs: set[tuple[str, FieldKey]] = set()
        for call in rule.capabilities:
            for output in call.out:
                text = output.strip()
                try:
                    key = FieldKey.parse(text) if ":" in text else aliases.get(text)
                except ValueError:
                    continue
                if key is None or (call.func, key) in outputs:
                    continue
                outputs.add((call.func, key))
                token = next(
                    (
                        token
                        for token in source.tokens.values()
                        if token.kind != "parse"
                        and token.cap_id is None
                        and token.binding.field_key == key
                        and (":" in text or token.render_name == text)
                    ),
                    None,
                )
                if token is not None:
                    token.cap_id = call.func
                    continue
                tid = source.new_token_id()
                source.tokens[tid] = SourceRuleToken(
                    id=tid,
                    kind="enrich",
                    type="string",
                    binding=Binding(
                        render_token=source.unique_render_name(key.field.lower()),
                        field_key=key,
                    ),
                    cap_id=call.func,
                    explicit_mapping=False,
                )
        return source
