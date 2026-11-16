"""单个模板的草稿、样例、输入诊断与保存用例"""

from __future__ import annotations

import os

from renamer.core.compile.template import reverse_fragment
from renamer.core.dsl import Call
from renamer.core.model import Issue, Level, Library, ParseTemplate, PlanError
from renamer.core.source import SourceTemplate

from .authoring import AuthoringService
from .session import AuthoringSession


class TemplateEditor:
    """持有一个模板编辑实例，未完成输入不进入已保存会话"""

    def __init__(
        self,
        authoring: AuthoringService,
        session: AuthoringSession,
        name: str,
    ) -> None:
        self._authoring = authoring
        self._session = session
        self.name = name
        self.source = SourceTemplate()
        self._enum_drafts: dict[int, tuple[str, str]] = {}

    def load(self, name: str, template: ParseTemplate) -> None:
        self.name = name
        self.source = SourceTemplate.from_template(template)
        self._enum_drafts.clear()

    def set_sample(self, filename: str) -> str | None:
        """新建草稿按样例重建，已载入草稿只更新匹配投影"""
        text = os.path.splitext(os.path.basename(filename))[0] if filename else ""
        if not self.source.is_loaded:
            self.source = SourceTemplate(chars=list(text))
            self._enum_drafts.clear()
            return None
        self.source.clear_sample()
        if not text:
            return None
        try:
            fragment = reverse_fragment(self.source.to_template(), text)
            if fragment is None:
                return "示例文件名与模板不匹配；模板内容已保留"
            self.source.attach_sample(text, fragment.spans)
        except (PlanError, ValueError) as exc:
            return str(exc)
        return None

    def mark(self, start: int, end: int) -> None:
        sample = "".join(self.source.chars[start : end + 1])
        self.source.mark(start, end, type=self._authoring.infer_type(sample))

    def unmark(self, token_id: int) -> None:
        self.source.unmark(token_id)
        self._enum_drafts.pop(token_id, None)

    def rename_token(self, token_id: int, name: str) -> None:
        self.source.rename(token_id, name)

    def set_token_type(self, token_id: int, type: str) -> None:
        token = self.source.tokens.get(token_id)
        if token is None:
            return
        self._enum_drafts.pop(token_id, None)
        values = () if type == "enum" and not token.values else (token.values or ())
        self.source.set_type(token_id, type)
        self.source.set_values(token_id, values)

    def set_candidate_text(self, token_id: int, text: str) -> None:
        """保留未完成参数原文，合法后提交同一份注解"""
        if token_id not in self.source.tokens:
            return
        try:
            calls = self._authoring.parse_format("enum(" + text + ")")
            if len(calls) != 1 or calls[0].name != "enum":
                raise ValueError("候选值须是一个 enum 调用的参数")
        except ValueError as exc:
            self._enum_drafts[token_id] = (text, str(exc))
        else:
            self._enum_drafts.pop(token_id, None)
            self.source.set_values(token_id, calls[0].args)

    def candidate_text(self, token_id: int) -> str:
        if token_id in self._enum_drafts:
            return self._enum_drafts[token_id][0]
        values = self.source.tokens[token_id].values or ()
        if not values:
            return ""
        expression = self._authoring.format_expression((Call("enum", values),))
        return expression[len("enum(") : -1]

    def token_conflicts(self) -> dict[int, str]:
        pairs = self.source.adjacent_conflict_pairs()
        bad = {tid for pair in pairs for tid in pair}
        numbers = {
            tid: index for index, (tid, _) in enumerate(self.source.ordered_tokens(), 1)
        }
        boundaries = ", ".join(
            f"{numbers[left]:02d}~{numbers[right]:02d}" for left, right in pairs
        )
        conflicts: dict[int, str] = {}
        for token_id, token in self.source.ordered_tokens():
            reasons: list[str] = []
            if token_id in self._enum_drafts:
                reasons.append("候选值：" + self._enum_drafts[token_id][1])
            if token_id in bad:
                reasons.append(f"相邻词段({boundaries})类型一致，无法区分边界")
            sample = self.source.sample_text(token_id)
            int_message = (
                self._authoring.int_content_conflict(
                    token.type, sample, token.name or str(token_id)
                )
                if sample is not None
                else None
            )
            if int_message:
                reasons.append(int_message)
            if reasons:
                conflicts[token_id] = "；".join(reasons)
        return conflicts

    def toml_text(self) -> str:
        return self._authoring.emit_library(
            Library(parse_templates={self.name: self.source.to_template()})
        )

    def save(self) -> Issue | None:
        """检查完整输入并提交会话，持久化异常继续交给调用方"""
        if self._enum_drafts:
            return Issue(
                level=Level.ERROR,
                code="incomplete_candidates",
                message="候选值尚未写完整："
                + "；".join(error for _, error in self._enum_drafts.values()),
            )
        name = (self.name or "").strip()
        if not name:
            return Issue(
                level=Level.ERROR,
                code="template_name_required",
                message="模板名不能为空",
            )
        if not self.source.render_text() and not self.source.is_loaded:
            return Issue(
                level=Level.ERROR, code="template_text_required", message="模板文本为空"
            )
        template = self.source.to_template()
        issues = self._authoring.validate_template(template)
        if issues:
            return Issue(
                level=Level.ERROR,
                code="template_validation_failed",
                message="模板校验未通过："
                + "；".join(issue.message for issue in issues),
            )
        self._session.add_template(name, template)
        return None
