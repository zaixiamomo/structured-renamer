"""规则编辑页：连接五张卡片、应用编辑工作集和能力试跑任务。"""

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QScrollArea

from renamer.app.authoring import (
    AuthoringService,
    PlanError,
    Rule,
    SourceRuleToken,
    render_template_name,
)
from renamer.app.rule_editing import RuleEditing
from renamer.core.model import Capability

from ..state.window import Window
from ..toml_projection import toml_lines, toml_string
from ..widgets.frozen_section import FrozenSection
from ..widgets.token_chip import TokenChip
from .panel_base import EditorPanel
from .rule_cards import (
    CapabilityCard,
    ComposeCard,
    FormatCard,
    ParseCard,
    RuleOutputCard,
)
from .rule_pool import FloatingTokenPool
from .rule_tasks import RulePreviewTasks

__all__ = ["RulePanel"]


class RulePanel(EditorPanel):
    """草稿和预览由 RuleEditing 持有；页面只保留词池选择和卡片间接线。"""

    def __init__(
        self,
        win: Window,
        *,
        manager,
        session,
        runner,
        authoring: AuthoringService,
        parent=None,
    ):
        super().__init__(parent)
        self._win = win
        self._manager = manager
        self._authoring = authoring
        self._session = session
        self._editing = RuleEditing(authoring, session.authoring_session)
        self._tasks = RulePreviewTasks(self._editing, runner, self)
        self.destroyed.connect(self._tasks.close)
        self._active_token_ids: set[int] = set()
        self._scroll_area: QScrollArea | None = None
        self._build()
        self._tasks.preview_changed.connect(self._sync_all)
        self._tasks.state_changed.connect(self._refresh_run_display)
        self._editing.set_name(
            manager.available_name("user_rule", session.rules, win.id)
        )
        self._register_open_rule_name()
        self._populate_parse_templates()
        session.changed.connect(self._populate_parse_templates)
        self.set_filename(win.filename)
        self.setAcceptDrops(True)

    def _build(self) -> None:
        layout = self._make_layout()
        self._parse = ParseCard()
        self._capabilities = CapabilityCard(
            self._authoring.list_capabilities(implemented_only=True)
        )
        self._compose = ComposeCard()
        self._formats = FormatCard(self._authoring.list_formats())
        self._output = RuleOutputCard()
        cards = [
            self._parse,
            self._capabilities,
            self._compose,
            self._formats,
            self._output,
        ]
        for title, card in zip(
            ("1. 解析", "2. 补全", "3. 组合", "4. 格式", "5. 规则"), cards
        ):
            layout.addWidget(self._pane_cap(title))
            layout.addWidget(card)
        layout.addStretch(1)
        self._pool = FloatingTokenPool(self, self._compose.pool_holder, cards)
        self._preview = FrozenSection(
            self, self._compose.preview_holder, cards, edge="top"
        )
        self._preview.body.addWidget(self._compose.preview)

        self._parse.template_changed.connect(self._on_parse_tpl_changed)
        self._parse.token_activated.connect(self._on_chip_activate)
        self._parse.token_deactivated.connect(self._on_chip_deactivate)
        self._capabilities.add_requested.connect(self._add_cap)
        self._capabilities.remove_requested.connect(self._remove_block)
        self._capabilities.input_dropped.connect(self._on_input_dropped)
        self._capabilities.input_unbound.connect(self._on_input_unbind)
        self._capabilities.run_requested.connect(self._tasks.toggle)
        self._capabilities.output_activated.connect(self._on_output_activate)
        self._capabilities.output_deactivated.connect(self._on_output_deactivate)
        self._compose.edit.token_dropped.connect(self._append_token)
        self._compose.edit.textChanged.connect(self._on_compose_edited)
        self._pool.token_deactivated.connect(self._on_chip_deactivate)
        self._formats.format_changed.connect(self._on_token_format_changed)
        self._formats.name_changed.connect(self._on_render_name_changed)
        self._output.toml.name_clicked.connect(self.name_edit_requested)
        self._output.toml.token_clicked.connect(self._on_toml_token_clicked)

    @property
    def name(self) -> str:
        return self._editing.source.name

    def set_name(self, text: str) -> None:
        if text != self.name:
            self._editing.set_name(text)
            self._register_open_rule_name()
            self._sync_toml()
            self.name_changed.emit()

    def _register_open_rule_name(self) -> None:
        self._manager.register_name(self._win.id, self.name)

    def set_filename(self, text: str) -> None:
        if text == "（新建规则）":
            text = ""
        self._after_parse(self._editing.set_sample(text))

    def save(self) -> bool:
        if self._formats.has_errors:
            self._parse.show_message("请先修正「4. 格式」中的词段名称或格式参数")
            return False
        message = self._editing.save()
        if message:
            self._parse.show_message(message)
            return False
        return True

    def load_rule(self, name: str, rule: Rule) -> None:
        """恢复声明，再投影到卡片；恢复过程不运行能力。"""
        try:
            message = self._editing.load(name, rule)
        except PlanError as exc:
            self._parse.show_message("；".join(issue.message for issue in exc.issues))
            return
        self._active_token_ids.clear()
        self._register_open_rule_name()
        self._populate_parse_templates()
        self._formats.set_tokens([], {})
        with QSignalBlocker(self._compose.edit):
            self._compose.edit.set_delimiters(
                self._editing.source.render_open, self._editing.source.render_close
            )
            self._compose.edit.set_markup(self._editing.source.render_text)
        self._tasks.clear()
        self._capabilities.reset_blocks(
            self._editing.capabilities[call.func]
            for call in self._editing.source.capability_calls
            if call.func in self._editing.capabilities
        )
        self._after_parse(message)

    def attach_scroll_area(self, scroll_area: QScrollArea) -> None:
        self._scroll_area = scroll_area
        self._pool.attach_scroll_area(scroll_area)
        self._preview.attach_scroll_area(scroll_area)

    # 解析模板与能力操作
    def _populate_parse_templates(self) -> None:
        self._parse.set_templates(
            self._session.parse_templates, self._editing.source.parse_name
        )

    def _on_parse_tpl_changed(self) -> None:
        combo = self._parse.combo
        template = combo.currentData()
        name = combo.currentText() if template is not None else None
        self._after_parse(self._editing.select_parse_template(name, template))

    def _after_parse(self, message: str) -> None:
        self._sync_all()
        self._parse.show_message(message)

    def _add_cap(self, capability: Capability) -> None:
        if capability.id in self._capabilities.blocks:
            return
        message = self._editing.add_capability(capability)
        self._capabilities.add_block(capability)
        self._after_parse(message)

    def _remove_block(self, cap_id: str) -> None:
        message = self._editing.remove_capability(cap_id)
        self._capabilities.remove_block(cap_id)
        self._tasks.remove(cap_id)
        self._after_parse(message)

    def _refresh_run_display(self, cap_id: str) -> None:
        block = self._capabilities.blocks.get(cap_id)
        if block is not None:
            display = self._tasks.status(cap_id)
            block.set_run_display(display.state, display.seconds, display.completed)

    def _refresh_blocks(self) -> None:
        self._tasks.reconcile()
        values = self._editing.capability_values(self._capabilities.blocks)
        for cap_id, block in self._capabilities.blocks.items():
            self._refresh_run_display(cap_id)
            block.refresh(values[cap_id], self._active_token_ids)

    def _on_output_activate(self, cap_id: str, key: str) -> None:
        token_id = self._editing.output_tokens(cap_id).get(key)
        if token_id is not None:
            self._on_chip_activate(token_id)

    def _on_output_deactivate(self, cap_id: str, key: str) -> None:
        token_id = self._editing.output_tokens(cap_id).get(key)
        if token_id is not None:
            self._on_chip_deactivate(token_id)

    def _on_input_dropped(self, key: str, token_id: int) -> None:
        try:
            message = self._editing.bind_input(key, token_id)
        except (KeyError, ValueError) as exc:
            self._parse.show_message(str(exc))
            return
        self._after_parse(message)

    def _on_input_unbind(self, key: str) -> None:
        self._after_parse(self._editing.unbind_input(key))

    # 组合编辑与输出格式
    def _append_token(self, token_id: int) -> None:
        token = self._editing.source.tokens.get(token_id)
        if token is not None:
            self._compose.edit.insert_token(token.render_name)

    def _on_compose_edited(self) -> None:
        self._editing.set_render_text(self._compose.edit.markup_text())
        self._sync_formats()
        self._update_preview()
        self._sync_toml()

    def _on_token_format_changed(self, index: int, spec: str) -> None:
        if not self._formats.rows[index].chain.errors:
            self._editing.set_token_format(index, spec)
            with QSignalBlocker(self._compose.edit):
                self._compose.edit.set_markup(self._editing.source.render_text)
            self._sync_formats()
        self._update_preview()
        self._sync_toml()

    def _on_render_name_changed(self, index: int, name: str) -> None:
        row = self._formats.rows[index]
        old_name = row.name
        try:
            self._editing.rename_render_token(old_name, name)
        except ValueError as exc:
            row.set_name_error(str(exc))
            self._update_preview()
            self.content_changed.emit()
            return
        self._formats.rename_token(old_name, name)
        self._sync_all()

    def _sync_formats(self) -> None:
        self._formats.set_tokens(
            self._editing.token_formats(), self._editing.preview.render_values
        )
        self._formats.show_legacy_format(self._editing.source.format)

    def _update_preview(self) -> None:
        visible = bool(self._editing.source.render_text.strip())
        text = ""
        if visible:
            if self._formats.has_errors:
                text = "请先修正「4. 格式」中的词段名称或格式参数"
            elif not self._editing.filename:
                text = "先拖入示例文件"
            else:
                try:
                    text = self._editing.render_preview()
                except PlanError as exc:
                    text = "；".join(issue.message for issue in exc.issues)
        self._compose.show_preview(text, visible=visible)
        self._preview.set_enabled(visible)

    def _sync_toml(self) -> None:
        text = self._editing.toml_text()
        self._output.toml.set_content(text, self._click_regions(text))
        self.content_changed.emit()

    def _on_toml_token_clicked(self, index: int) -> None:
        edit = self._formats.focus_token(index)
        if edit is not None and self._scroll_area is not None:
            preview = self._preview.card
            margin = (
                preview.height() + self.layout().spacing() if preview.isVisible() else 0
            )
            self._scroll_area.ensureWidgetVisible(edit, ymargin=max(50, margin))

    def _click_regions(self, text: str) -> list[dict]:
        """标注规则名及渲染引用，引用序号对应格式卡片中的编辑行。"""
        rule_name = self._editing.source.name.strip()
        render_key = self._editing.source.render_name or render_template_name(rule_name)
        regions: list[dict] = []
        section = ""
        cur_name: str | None = None
        for line, offset in toml_lines(text):
            if line.startswith("[[render_template]]"):
                section, cur_name = "template", None
                continue
            if line.startswith("[[rule]]"):
                section, cur_name = "rule", None
                continue
            if line.startswith('name = "'):
                name = toml_string(line, offset, "name")
                if name is None:
                    continue
                if section == "rule":
                    regions.append(name.name_region())
                cur_name = name.decoded
                continue
            if (
                line.startswith('text = "')
                and section == "template"
                and cur_name == render_key
            ):
                value = toml_string(line, offset, "text")
                if value is None:
                    continue
                spans = self._authoring.tokenize(
                    value.decoded,
                    open=self._editing.source.render_open,
                    close=self._editing.source.render_close,
                ).spans
                for index, sp in enumerate(sp for sp in spans if sp.is_token()):
                    regions.append(value.token_region(index, sp.s, sp.e))
        return regions

    # 词段选择只影响视图，不改写声明。
    def _on_chip_activate(self, token_id: int) -> None:
        if (
            token_id in self._editing.source.tokens
            and token_id not in self._active_token_ids
        ):
            self._active_token_ids.add(token_id)
            self._sync_token_views()
            self.content_changed.emit()

    def _on_chip_deactivate(self, token_id: int) -> None:
        if token_id in self._active_token_ids:
            self._active_token_ids.remove(token_id)
            self._sync_token_views()
            self.content_changed.emit()

    def _chip(self, tok: SourceRuleToken) -> TokenChip:
        """词组件统一构造：沿用 token 种类与激活态，悬停提示带完整信息"""
        return TokenChip(
            tok.id,
            tok.render_name,
            self._editing.preview.render_values.get(tok.render_name, ""),
            tok.type,
            source=tok.kind,
            active=tok.id in self._active_token_ids,
            tooltip=self._token_info(tok),
        )

    def _token_info(self, tok: SourceRuleToken) -> str:
        """词组件的悬停完整信息（词组件只显示词，信息在悬停时展开）"""
        parts = [f"名 = {tok.render_name}"]
        if tok.render_name in self._editing.preview.render_values:
            parts.append(f"值 = {self._editing.preview.render_values[tok.render_name]}")
        parts.append(f"类型 = {tok.type}")
        parts.append("来源 = " + ("解析" if tok.kind == "parse" else "enrich"))
        active = tok.id in self._active_token_ids
        parts.append("状态 = " + ("已激活" if active else "未激活（左键激活）"))
        if tok.binding.field_key is not None:
            parts.append(f"绑定字段 = {tok.binding.field_key}")
        return "、".join(parts)

    def _sync_token_views(self) -> None:
        self._parse.show_sample(
            self._editing.filename,
            self._editing.source.tokens,
            self._editing.preview.spans,
            self._chip,
        )
        self._pool.set_chips(
            self._chip(token)
            for token in self._editing.source.tokens.values()
            if token.id in self._active_token_ids
        )
        self._compose.edit.set_hint(
            "输入文本或拖入词段"
            if self._pool.has_tokens
            else "在解析和补全中，激活所需词段"
        )
        self._refresh_blocks()

    def _sync_all(self) -> None:
        self._active_token_ids.intersection_update(self._editing.source.tokens)
        with QSignalBlocker(self._compose.edit):
            self._compose.edit.refresh_tokens(
                {
                    token.render_name: (
                        self._editing.preview.render_values.get(
                            token.render_name, token.render_name
                        ),
                        token.type,
                    )
                    for token in self._editing.source.tokens.values()
                    if token.render_name
                }
            )
            if self._compose.edit.markup_text() != self._editing.source.render_text:
                self._compose.edit.set_markup(self._editing.source.render_text)
        self._sync_token_views()
        self._sync_formats()
        self._update_preview()
        self._sync_toml()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._pool.update()
        self._preview.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._pool.update()
        self._preview.update()
