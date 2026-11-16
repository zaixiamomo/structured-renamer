"""规则草稿的示例运行状态；声明始终由 SourceRule 持有。"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from renamer.core.compile.template import reverse_fragment
from renamer.core.dsl import apply_bound
from renamer.core.model import (
    SOURCE_PATH_KEY,
    Capability,
    FieldKey,
    ParseTemplate,
    PlanError,
)
from renamer.core.runtime.scheduler import run_capabilities
from renamer.core.source import SourceRule

from .authoring import compile_source_plan


@dataclass(frozen=True)
class PreviewTicket:
    revision: int
    sequence: int
    inputs: tuple[tuple[str, str], ...]


@dataclass
class RulePreview:
    """一次编辑会话的样例和调用缓存，不参与 TOML 持久化。"""

    filename: str = ""
    parsed: dict[str, str] = field(default_factory=dict)
    values: dict[int, str] = field(default_factory=dict)
    render_values: dict[str, str] = field(default_factory=dict)
    spans: tuple[tuple[str, int, int], ...] = ()
    outputs: dict[str, dict[FieldKey, str]] = field(default_factory=dict)
    revision: int = 0
    _sequence: int = 0
    _pending: dict[str, PreviewTicket] = field(default_factory=dict)

    def reset(
        self, source: SourceRule, filename: str, capabilities: Mapping[str, Capability]
    ) -> str:
        """样例或输入声明变化使旧结果失效，保留草稿中的身份和绑定。"""
        self.invalidate()
        self.filename = filename
        self.parsed.clear()
        self.outputs.clear()
        self.values.clear()
        self.render_values.clear()
        self.spans = ()
        if not filename or source.parse_template is None:
            return ""
        try:
            fragment = reverse_fragment(
                source.parse_template, os.path.splitext(os.path.basename(filename))[0]
            )
        except PlanError as exc:
            return "；".join(issue.message for issue in exc.issues)
        if fragment is None:
            return "文件名与解析模板不匹配"
        self.parsed.update(fragment.values)
        self.spans = fragment.spans
        self.refresh_values(source, capabilities)
        return ""

    def _evaluate(self, source, capabilities, *, render=False):
        # 输入试跑不要求组合文本已写完；接线、优先级和取值仍由同一编译器负责。
        draft = source if render else replace(source, render_text="", format="")
        if not render and draft.parse_template is None:
            # 独立能力试跑可以先于解析模板选择；只给本次求值补空捕获环境。
            draft = replace(
                draft, parse_name="__preview", parse_template=ParseTemplate(text="")
            )
        plan = compile_source_plan(draft, capabilities)
        seeds = plan.mapping.seed_values(self.parsed)
        if self.filename:
            seeds.setdefault(SOURCE_PATH_KEY, self.filename)
        calls = {
            cid: (lambda _inputs, cid=cid: self.outputs.get(cid, {}))
            for cid in plan.wire.capabilities
        }
        fields, _issues = run_capabilities(plan.wire, seeds, calls)
        return plan, fields

    def available_fields(self, source, capabilities) -> dict[FieldKey, str]:
        try:
            return self._evaluate(source, capabilities)[1]
        except PlanError:
            # 草稿尚不能编译时仍展示已捕获的输入；不伪造能力运行结果。
            seeds = {
                tok.binding.field_key: self.parsed[tok.binding.parse_token]
                for tok in source.tokens.values()
                if tok.binding.field_key is not None
                and tok.binding.parse_token in self.parsed
            }
            if self.filename:
                seeds.setdefault(SOURCE_PATH_KEY, self.filename)
            return seeds

    def refresh_values(self, source, capabilities) -> None:
        fields = self.available_fields(source, capabilities)
        self.values.clear()
        self.render_values = dict(self.parsed)
        for tid, tok in source.tokens.items():
            binding = tok.binding
            if binding.parse_token in self.parsed:
                self.values[tid] = self.parsed[binding.parse_token]
                self.render_values[tok.render_name] = self.parsed[binding.parse_token]
            elif binding.field_key in fields:
                self.render_values[tok.render_name] = fields[binding.field_key]
            if binding.parse_token in self.parsed:
                continue
            if tok.cap_id:
                result = self.outputs.get(tok.cap_id, {})
                if binding.field_key in result:
                    self.values[tid] = result[binding.field_key]
            elif binding.field_key in fields:
                self.values[tid] = fields[binding.field_key]

    def inputs_for(self, cap, source, capabilities) -> dict[str, str] | None:
        fields = self.available_fields(source, capabilities)
        if any(key not in fields for key in cap.inputs):
            return None
        return {str(key): fields[key] for key in cap.inputs}

    def forget(self, cap_id: str, capabilities: Mapping[str, Capability]) -> None:
        """重新试跑生产者时，清除它和依赖其输出的旧预览。"""
        affected = {cap_id}
        while True:
            fields = {
                key
                for cid in affected
                if cid in capabilities
                for key in capabilities[cid].outputs
            }
            consumers = {
                cid
                for cid, cap in capabilities.items()
                if fields.intersection(cap.inputs)
            }
            if consumers <= affected:
                break
            affected.update(consumers)
        for cid in affected:
            self.outputs.pop(cid, None)
            self._pending.pop(cid, None)

    def begin(
        self, cap, source, capabilities
    ) -> tuple[PreviewTicket, dict[str, str]] | None:
        self.forget(cap.id, capabilities)
        self.refresh_values(source, capabilities)
        inputs = self.inputs_for(cap, source, capabilities)
        if inputs is None:
            return None
        self._sequence += 1
        ticket = PreviewTicket(self.revision, self._sequence, tuple(inputs.items()))
        self._pending[cap.id] = ticket
        return ticket, inputs

    def cancel(self, cap_id: str) -> None:
        self._pending.pop(cap_id, None)

    def invalidate(self) -> None:
        """样例、绑定或窗口生命周期变化后拒绝所有旧回调。"""
        self.revision += 1
        self._pending.clear()

    def is_running(self, cap_id: str) -> bool:
        return cap_id in self._pending

    def accept(self, cap, ticket, outputs, source, capabilities) -> bool:
        if self._pending.get(cap.id) != ticket or ticket.revision != self.revision:
            return False
        self._pending.pop(cap.id, None)
        inputs = self.inputs_for(cap, source, capabilities)
        if inputs is None or tuple(inputs.items()) != ticket.inputs:
            return False
        # 等待期间消费者可能已经使用备用来源完成；新值到达时再次作废下游。
        self.forget(cap.id, capabilities)
        allowed = {str(key): key for key in cap.outputs}
        self.outputs[cap.id] = {
            allowed[str(key)]: str(value)
            for key, value in outputs.items()
            if str(key) in allowed and value is not None
        }
        self.refresh_values(source, capabilities)
        return True

    def render(self, source, capabilities) -> str:
        """使用编译后的取值和格式步骤预览，绝不触发实际能力调用。"""
        plan, fields = self._evaluate(source, capabilities, render=True)
        text = plan.render.render(
            lambda name: plan.mapping.render_value(name, self.parsed, fields)
        )
        return apply_bound(text, plan.output_steps) + os.path.splitext(self.filename)[1]
