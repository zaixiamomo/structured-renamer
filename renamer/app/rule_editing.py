"""单个规则编辑工作集：声明修改、样例投影、试跑和保存"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from renamer.core.dsl import (
    Placeholder,
    fmt_mapping,
    fmt_placeholder,
    parse_mapping,
    parse_template,
)
from renamer.core.model import (
    SOURCE_PATH_KEY,
    Capability,
    FieldKey,
    ParseTemplate,
    Rule,
    TokenMapping,
)
from renamer.core.source import Binding, SourceRule, SourceRuleToken

from .authoring import AuthoringService
from .rule_preview import PreviewTicket, RulePreview

if TYPE_CHECKING:
    from .session import AuthoringSession


@dataclass(frozen=True)
class CapabilityValues:
    """能力输入与各生产者输出的样例投影"""

    inputs: dict[str, tuple[str, bool]]
    outputs: dict[str, tuple[int, str, str | None]]  # 词段 ID、名称、可选预览值
    ready: bool


class RuleEditing:
    """一个打开的规则草稿及其样例；不持有窗口和词池选择"""

    def __init__(self, authoring: AuthoringService, session: AuthoringSession):
        self.authoring = authoring
        self.session = session
        self.source = SourceRule()
        self.preview = RulePreview()
        self.source_path = ""
        self.capabilities = {cap.id: cap for cap in authoring.list_capabilities()}
        self.field_types = authoring.field_types()

    @property
    def filename(self) -> str:
        return os.path.basename(self.source_path)

    def load(self, name: str, rule: Rule) -> str:
        source = self.authoring.restore_rule(rule, self.session.library)
        source.name = name
        self.source = source
        return self.reset_preview()

    def save(self) -> str:
        """校验并保存，返回已有的失败提示；其它异常仍交调用方处理"""
        source = self.source
        if not source.name.strip():
            return "规则名不能为空"
        if not source.parse_name:
            return "请选择解析模板"
        if not source.render_text.strip() and source.render_name is None:
            return "请填写组合文本"
        library = source.to_library()
        rule = library.rules[source.name]
        issues = self.authoring.validate_rule(rule, library, self.capabilities)
        if issues:
            return "；".join(issue.message for issue in issues)
        try:
            self.session.update_library(library)
        except OSError as exc:
            return f"保存失败：{exc}"
        return ""

    def set_name(self, name: str) -> None:
        self.source.name = name

    def set_render_text(self, text: str) -> None:
        self.source.render_text = text

    def token_formats(self) -> list[tuple[str, str]]:
        """按组合中的出现顺序返回引用及格式，同名引用各自独立。"""
        source = self.source
        return [
            (span.name, self.authoring.format_expression(span.annotation or ()))
            for span in self.authoring.tokenize(
                source.render_text, open=source.render_open, close=source.render_close
            ).spans
            if span.is_token()
        ]

    def set_token_format(self, index: int, spec: str) -> None:
        """只替换指定次引用的注解，保留其它引用、分隔文本和自定义定界符。"""
        errors = self.authoring.validate_format(spec)
        if errors:
            raise ValueError("；".join(errors))
        source = self.source
        spans = [
            span
            for span in self.authoring.tokenize(
                source.render_text, open=source.render_open, close=source.render_close
            ).spans
            if span.is_token()
        ]
        span = spans[index]
        reference = self.authoring.format_reference(
            span.name, spec, open=source.render_open, close=source.render_close
        )
        source.render_text = (
            source.render_text[: span.s] + reference + source.render_text[span.e + 1 :]
        )

    def rename_render_token(self, old_name: str, new_name: str) -> None:
        """修改渲染别名及全部引用，不改捕获、字段身份或能力试跑有效性。"""
        if old_name == new_name:
            return
        source = self.source
        if not new_name.strip():
            raise ValueError("词段名称不能为空")
        if any(char.isspace() for char in new_name):
            raise ValueError("词段名称不能包含空白")
        reference = fmt_placeholder(
            new_name, open=source.render_open, close=source.render_close
        )
        mapping = TokenMapping(parse_token=new_name)
        if parse_mapping(fmt_mapping(mapping)) != mapping:
            raise ValueError(f"词段名称不能用于映射：{new_name!r}")
        syntax = parse_template(
            source.render_text, source.render_open, source.render_close
        )
        references = [part for part in syntax.parts if isinstance(part, Placeholder)]
        tokens = [
            token for token in source.tokens.values() if token.render_name == old_name
        ]
        if not tokens and not any(part.name == old_name for part in references):
            raise ValueError(f"词段 {old_name!r} 不存在")
        restores_capture = bool(tokens) and all(
            token.binding.parse_token == new_name for token in tokens
        )
        if any(part.name == new_name for part in references) or any(
            token.render_name != old_name
            and (
                new_name == token.render_name
                or (new_name == token.binding.parse_token and not restores_capture)
            )
            for token in source.tokens.values()
        ):
            raise ValueError(f"词段名称 {new_name!r} 已被使用")

        text = source.render_text
        # 只替换名字，原注解的引号、空白及每次引用的独立格式均原样保留。
        prefix = reference[: -len(source.render_close)]
        for part in reversed(references):
            if part.name != old_name:
                continue
            assert part.span is not None
            name_end = part.span.start + len(source.render_open) + len(old_name)
            text = text[: part.span.start] + prefix + text[name_end:]
        calls = [
            call.model_copy(
                update={
                    "out": tuple(
                        new_name if output.strip() == old_name else output
                        for output in call.out
                    )
                }
            )
            for call in source.capability_calls
        ]
        if not tokens and source.parse_template is not None:
            # core 允许原捕获名在已有别名映射之外同名透传；改名时补出独立绑定。
            template = source.parse_template
            for span in self.authoring.tokenize(
                template.text, open=template.open, close=template.close
            ).spans:
                if span.is_token() and span.name == old_name:
                    token = SourceRuleToken(
                        id=source.new_token_id(),
                        kind="parse",
                        type=span.type or "string",
                        binding=Binding(parse_token=old_name),
                    )
                    source.tokens[token.id] = token
                    tokens.append(token)
                    break
        for token in tokens:
            token.binding.render_token = new_name
        source.render_text = text
        source.capability_calls = calls
        self.preview.refresh_values(source, self.capabilities)

    def reset_preview(self) -> str:
        return self.preview.reset(self.source, self.source_path, self.capabilities)

    def set_sample(self, path: str) -> str:
        self.source_path = path or ""
        return self.reset_preview()

    def select_parse_template(
        self, name: str | None, template: ParseTemplate | None
    ) -> str:
        self.source.set_parse_template(name, template)
        return self.reset_preview()

    def add_capability(self, cap: Capability) -> str:
        self.source.add_capability(cap, self.field_types)
        return self.reset_preview()

    def remove_capability(self, cap_id: str) -> str:
        if not any(call.func == cap_id for call in self.source.capability_calls):
            return ""
        fields = self.source.capability_output_fields(cap_id)
        cap = self.capabilities.get(cap_id)
        if cap is not None:
            # 输入绑定属于共享字段；只释放不再被其它能力使用的解析种子。
            shared_inputs = {
                key
                for call in self.source.capability_calls
                if call.func != cap_id and call.func in self.capabilities
                for key in self.capabilities[call.func].inputs
            }
            released = set(cap.inputs) - shared_inputs
            for key in released:
                self.source.unbind_input(key)
            fields.update(released)
        self.source.remove_capability(cap_id)
        self._clear_dependent_outputs(fields)
        return self.reset_preview()

    def bind_input(self, key: str, token_id: int) -> str:
        before = self._reachable_capabilities()
        self.source.bind_input(FieldKey.parse(key), token_id)
        restored = self._reachable_capabilities() - before
        for call in self.source.capability_calls:
            if call.func in restored:
                self.source.add_capability(
                    self.capabilities[call.func], self.field_types
                )
        return self.reset_preview()

    def unbind_input(self, key: str) -> str:
        field = FieldKey.parse(key)
        self.source.unbind_input(field)
        self._clear_dependent_outputs({field})
        return self.reset_preview()

    def _clear_dependent_outputs(self, fields: set[FieldKey]) -> None:
        """解绑或删除能力后，沿受影响字段清理失去来源的下游产出。"""
        pending = {
            call.func
            for call in self.source.capability_calls
            if call.func in self.capabilities
        } - self._reachable_capabilities()
        affected = set()
        while pending:
            consumers = {
                cid
                for cid in pending
                if fields.intersection(self.capabilities[cid].inputs)
            }
            if not consumers:
                break
            for cid in consumers:
                fields.update(self.source.capability_output_fields(cid))
            affected.update(consumers)
            pending.difference_update(consumers)
        self.source.clear_capability_outputs(affected)

    def _reachable_capabilities(self) -> set[str]:
        """按声明判断输入来源，不以样例值或是否试跑决定词段是否存在。"""
        template = self.source.parse_template
        captures = (
            {
                span.name
                for span in self.authoring.tokenize(
                    template.text, open=template.open, close=template.close
                ).spans
                if span.is_token()
            }
            if template is not None
            else set()
        )
        fields = {SOURCE_PATH_KEY}
        fields.update(
            token.binding.field_key
            for token in self.source.tokens.values()
            if token.binding.parse_token in captures
            and token.binding.field_key is not None
        )
        pending = {
            call.func
            for call in self.source.capability_calls
            if call.func in self.capabilities
        }
        reachable = set()
        while pending:
            ready = {
                cid
                for cid in pending
                if fields.issuperset(self.capabilities[cid].inputs)
            }
            if not ready:
                break
            for cid in ready:
                fields.update(self.source.capability_output_fields(cid))
            reachable.update(ready)
            pending.difference_update(ready)
        return reachable

    def output_tokens(self, cap_id: str) -> dict[str, int]:
        return {
            str(token.binding.field_key): tid
            for tid, token in self.source.tokens.items()
            if token.cap_id == cap_id and token.binding.field_key is not None
        }

    def capability_values(self, cap_ids: Iterable[str]) -> dict[str, CapabilityValues]:
        """一次刷新共享输入投影，各能力的运行就绪仍由预览服务判断"""
        bindings = self.source.input_bindings()
        available = self.preview.available_fields(self.source, self.capabilities)
        result = {}
        for cap_id in cap_ids:
            cap = self.capabilities[cap_id]
            inputs: dict[str, tuple[str, bool]] = {}
            for field in cap.inputs:
                tid = bindings.get(field)
                token = self.source.tokens.get(tid)
                unbind = token is not None and token.kind == "parse"
                if field in available:
                    inputs[str(field)] = (available[field], unbind)
                elif token is not None:
                    inputs[str(field)] = (
                        self.preview.values.get(tid, token.render_name),
                        unbind,
                    )
            outputs = {
                key: (
                    tid,
                    self.source.tokens[tid].render_name,
                    self.preview.values.get(tid),
                )
                for key, tid in self.output_tokens(cap_id).items()
            }
            ready = (
                self.preview.inputs_for(cap, self.source, self.capabilities) is not None
            )
            result[cap_id] = CapabilityValues(inputs, outputs, ready)
        return result

    def begin_preview(
        self, cap: Capability
    ) -> tuple[PreviewTicket, dict[str, str]] | None:
        return self.preview.begin(cap, self.source, self.capabilities)

    def accept_preview(
        self, cap: Capability, ticket: PreviewTicket, outputs: dict
    ) -> bool:
        return self.preview.accept(cap, ticket, outputs, self.source, self.capabilities)

    def cancel_preview(self, cap_id: str) -> None:
        self.preview.cancel(cap_id)

    def invalidate_preview(self) -> None:
        self.preview.invalidate()

    def render_preview(self) -> str:
        return self.preview.render(self.source, self.capabilities)

    def toml_text(self) -> str:
        return self.authoring.emit_library(self.source.to_library())
