"""规则编辑页的五张卡片：局部控件与显示，用户操作通过信号交给页面。"""

import os
from collections.abc import Callable, Iterable, Mapping
from difflib import SequenceMatcher

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from renamer.app.authoring import SourceRuleToken, Template
from renamer.core.model import Capability

from ..widgets.cap_block import CapBlock, capability_display_name
from ..widgets.compose_edit import ComposeEdit
from ..widgets.editor_card import EditorCard
from ..widgets.elide_label import ElideLabel
from ..widgets.flow_layout import FlowLayout
from ..widgets.format_chain import FormatChainEdit
from ..widgets.name_edit import NameEdit
from ..widgets.status_label import StatusLabel
from ..widgets.token_chip import TokenChip
from ..widgets.toml_edit import TomlEdit
from ..widgets.wrap_label import WrapLabel


def _note(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setProperty("role", "note")
    label.setWordWrap(True)
    return label


def _warning() -> StatusLabel:
    label = StatusLabel()
    label.setProperty("role", "note")
    label.set_status("warn")
    label.setWordWrap(True)
    label.hide()
    return label


class _SelectRow(QWidget):
    """标签、无滚轮下拉及可选操作；宽度按选中文本和当前行预算收放。"""

    class Combo(QComboBox):
        def wheelEvent(self, event) -> None:
            event.ignore()

    def __init__(self, label: str, action: QPushButton | None = None):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8 if action is not None else 6)
        caption = _note(label)
        caption.setWordWrap(False)
        layout.addWidget(caption)
        self.combo = self.Combo()
        self.combo.setProperty("role", "select-ghost")
        self.combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.combo.currentIndexChanged.connect(self.fit_width)
        layout.addWidget(self.combo)
        layout.addStretch(1)
        if action is not None:
            layout.addWidget(action)

    def fit_width(self) -> None:
        metrics = self.combo.fontMetrics()
        needed = (
            max(
                metrics.horizontalAdvance(
                    self.combo.currentText() or self.combo.placeholderText()
                ),
                metrics.horizontalAdvance("0") * 15,
            )
            + 26
        )
        layout = self.layout()
        margins = layout.contentsMargins()
        used = margins.left() + margins.right()
        for index in range(layout.count()):
            item = layout.itemAt(index)
            if item.widget() is not None and item.widget() is not self.combo:
                used += item.sizeHint().width()
        used += layout.spacing() * (layout.count() - 1)
        available = self.width() - used
        self.combo.setFixedWidth(min(needed, available) if available > 0 else needed)

    def minimumSizeHint(self):
        # 下拉宽度随行预算缩放，不能反过来作为父布局不可收窄的硬下限。
        hint = super().minimumSizeHint()
        hint.setWidth(max(0, hint.width() - self.combo.minimumWidth()))
        return hint

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fit_width()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.fit_width()


class _TokenLine(QWidget):
    """流式解析词段，宿主宽度改变时立即更新折行高度。"""

    def __init__(self):
        super().__init__()
        self.flow = FlowLayout(margin=0, spacing=4)
        self.setLayout(self.flow)

    def clear(self) -> None:
        while self.flow.count():
            widget = self.flow.takeAt(0).widget()
            widget.setParent(None)
            widget.deleteLater()

    def fit_height(self) -> None:
        if self.width() > 0:
            height = self.flow.heightForWidth(self.width())
            if height >= 0:
                self.setMinimumHeight(height + 2)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fit_height()


class ParseCard(EditorCard):
    template_changed = Signal()
    token_activated = Signal(int)
    token_deactivated = Signal(int)

    def __init__(self):
        super().__init__()
        self.tokens = _TokenLine()
        self.tokens.hide()
        self.body.addWidget(self.tokens)
        self.empty = _note("从文件树拖入文件，按解析模板分片标注")
        self.empty.setMinimumHeight(self.HINT_ROW_HEIGHT)
        self.empty.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.body.addWidget(self.empty)
        self._selection = _SelectRow("解析模板：")
        self._selection.hide()
        self.combo = self._selection.combo
        self.combo.currentIndexChanged.connect(self.template_changed)
        self.body.addWidget(self._selection)
        self.message = _warning()
        self.body.addWidget(self.message)

    def set_templates(self, templates: Mapping[str, Template], current: str) -> None:
        with QSignalBlocker(self.combo):
            self.combo.clear()
            for name, template in templates.items():
                self.combo.addItem(name, template)
            self.combo.setCurrentIndex(self.combo.findText(current))
        self._selection.fit_width()

    def show_message(self, text: str) -> None:
        self.message.setText(text)
        self.message.setVisible(bool(text) and self.empty.isHidden())

    def show_sample(
        self,
        filename: str,
        tokens: Mapping[int, SourceRuleToken],
        spans: list[tuple[str, int, int]],
        chip_for: Callable[[SourceRuleToken], TokenChip],
    ) -> None:
        self.tokens.clear()
        parse_tokens = [token for token in tokens.values() if token.kind == "parse"]
        self.empty.setVisible(not filename)
        self.tokens.setVisible(bool(filename))
        self._selection.setVisible(bool(filename))
        self.message.setVisible(bool(filename) and bool(self.message.text()))
        if not filename:
            return
        if not spans:
            self._add_literal(filename, "未解析：尚未选择模板或模板不适用")
        else:
            stem_length = len(os.path.splitext(filename)[0])
            by_name = {token.binding.parse_token: token.id for token in parse_tokens}
            owners: list[int | None] = [None] * len(filename)
            for name, start, end in spans:
                token_id = by_name.get(name)
                if token_id is not None:
                    for index in range(start, min(end, stem_length - 1) + 1):
                        owners[index] = token_id
            start = 0
            while start < len(filename):
                end = start + 1
                while end < len(filename) and owners[end] == owners[start]:
                    end += 1
                token_id = owners[start]
                if token_id is None:
                    self._add_literal(
                        filename[start:end],
                        "扩展名（解析只处理主名）"
                        if start >= stem_length
                        else "固定分隔文本",
                    )
                else:
                    self._add_chip(chip_for(tokens[token_id]))
                start = end
        self.tokens.fit_height()

    def _add_chip(self, chip: TokenChip) -> None:
        chip.clicked.connect(self.token_activated)
        chip.right_clicked.connect(self.token_deactivated)
        self.tokens.flow.addWidget(chip)

    def _add_literal(self, text: str, tooltip: str) -> None:
        label = WrapLabel(text)
        label.setProperty("role", "parse-lit")
        label.setToolTip(tooltip)
        self.tokens.flow.addWidget(label)


class CapabilityCard(EditorCard):
    add_requested = Signal(object)
    remove_requested = Signal(str)
    input_dropped = Signal(str, int)
    input_unbound = Signal(str)
    run_requested = Signal(object)
    output_activated = Signal(str, str)
    output_deactivated = Signal(str, str)

    def __init__(self, capabilities: Iterable[Capability]):
        super().__init__()
        self._capabilities = tuple(capabilities)
        self.blocks: dict[str, CapBlock] = {}
        self.add_button = QPushButton("添加")
        self.add_button.setProperty("role", "d-btn-primary")
        self.add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_button.clicked.connect(self._request_add)
        self._selection = _SelectRow("补充能力：", self.add_button)
        self.combo = self._selection.combo
        self.combo.currentIndexChanged.connect(self._sync_selection)
        self.body.addWidget(self._selection)
        host = QWidget()
        self._blocks_layout = QVBoxLayout(host)
        self._blocks_layout.setContentsMargins(0, 0, 0, 0)
        self._blocks_layout.setSpacing(0)
        self.body.addWidget(host)
        self._refresh_choices()

    def reset_blocks(self, capabilities: Iterable[Capability]) -> None:
        for block in self.blocks.values():
            block.setParent(None)
            block.deleteLater()
        self.blocks.clear()
        for capability in capabilities:
            self.add_block(capability)
        self._refresh_choices()

    def add_block(self, capability: Capability) -> None:
        if capability.id in self.blocks:
            return
        block = CapBlock(capability)
        block.token_dropped.connect(self.input_dropped)
        block.unbind_requested.connect(self.input_unbound)
        block.run_requested.connect(self.run_requested)
        block.remove_requested.connect(
            lambda item: self.remove_requested.emit(item.cap.id)
        )
        block.output_activate.connect(
            lambda key, cap_id=capability.id: self.output_activated.emit(cap_id, key)
        )
        block.output_deactivate.connect(
            lambda key, cap_id=capability.id: self.output_deactivated.emit(cap_id, key)
        )
        self.blocks[capability.id] = block
        self._blocks_layout.insertWidget(0, block)
        self._refresh_choices()

    def remove_block(self, cap_id: str) -> None:
        block = self.blocks.pop(cap_id)
        block.setParent(None)
        block.deleteLater()
        self._refresh_choices()

    def _refresh_choices(self) -> None:
        with QSignalBlocker(self.combo):
            self.combo.clear()
            for capability in self._capabilities:
                if capability.id not in self.blocks:
                    self.combo.addItem(capability_display_name(capability), capability)
                    inputs = "、".join(str(field) for field in capability.inputs)
                    outputs = "、".join(str(field) for field in capability.outputs)
                    self.combo.setItemData(
                        self.combo.count() - 1,
                        "\n".join(
                            part
                            for part in (
                                capability.description,
                                f"输入：{inputs or '无'}",
                                f"产出：{outputs or '无'}",
                            )
                            if part
                        ),
                        Qt.ItemDataRole.ToolTipRole,
                    )
            self.combo.setPlaceholderText(
                "已添加全部可用能力" if self.blocks and not self.combo.count() else ""
            )
            self.combo.setCurrentIndex(-1)
        self._sync_selection()

    def _sync_selection(self) -> None:
        self.add_button.setEnabled(self.combo.currentData() is not None)
        self._selection.fit_width()

    def _request_add(self) -> None:
        capability = self.combo.currentData()
        if capability is not None:
            self.add_requested.emit(capability)


class ComposeCard(EditorCard):
    def __init__(self):
        super().__init__()
        self.preview = QLabel()
        self.preview.setProperty("role", "preview")
        self.preview.setWordWrap(True)
        self.preview_holder = QWidget()
        self.body.addWidget(self.preview_holder)
        self.edit = ComposeEdit()
        self.body.addWidget(self.edit)
        self.pool_holder = QWidget()
        self.body.addWidget(self.pool_holder)
        self.show_preview("", visible=False)

    def show_preview(self, text: str, *, visible: bool) -> None:
        self.preview.setText(text)
        self.preview.setVisible(visible)
        self.preview_holder.setVisible(visible)


class _TokenFormatRow(QWidget):
    def __init__(self, index: int, name: str, spec: str, formats: list[dict]):
        super().__init__()
        self.setProperty("role", "tok-row")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        prefix = QWidget()
        row = QHBoxLayout(prefix)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.sequence = QLabel()
        self.sequence.setProperty("role", "tok-seq")
        self.sequence.setFixedWidth(22)
        self.set_index(index)
        row.addWidget(self.sequence)
        self.preview = ElideLabel("")
        self.preview.setProperty("role", "tok-raw")
        self.preview.setTextFormat(Qt.TextFormat.PlainText)
        row.addWidget(self.preview, 1)
        self.name_edit = NameEdit(name)
        self.name_edit.setProperty("role", "tok-token")
        self.name_edit.setToolTip("渲染词段名称；同名引用同步修改")
        self.name_edit.setAcceptDrops(False)
        self.name_edit.settle_display()
        row.addWidget(self.name_edit)
        self.chain = FormatChainEdit(formats, spec)
        self.chain.set_prefix(prefix)
        self.chain.set_preview_offset(self.sequence.width() + row.spacing())
        layout.addWidget(self.chain)
        self.name_error = StatusLabel()
        self.name_error.setProperty("role", "note")
        self.name_error.set_status("err")
        self.name_error.setWordWrap(True)
        self.name_error.hide()
        layout.addWidget(self.name_error)
        self.name = name
        self._applied_spec = spec

    def set_index(self, index: int) -> None:
        self.index = index
        self.sequence.setText(f"{index + 1:02d}")

    def set_name(self, name: str) -> None:
        self.name = name
        if self.name_edit.text() != name:
            with QSignalBlocker(self.name_edit):
                self.name_edit.setText(name)
            self.name_edit.updateGeometry()
        self.set_name_error("")

    def set_name_error(self, message: str) -> None:
        self.name_error.setText(message)
        self.name_error.setVisible(bool(message))

    def set_value(self, spec: str, sample: str | None) -> None:
        # 样例/能力回调只更新示例，保留当前格式槽及其焦点。
        if spec != self._applied_spec:
            self.chain.set_spec(spec)
            self._applied_spec = spec
        self.chain.set_sample(sample)
        text = sample if sample is not None else "未提供示例"
        self.preview.setText(text)
        self.preview.setToolTip(text)


class FormatCard(EditorCard):
    format_changed = Signal(int, str)
    name_changed = Signal(int, str)

    def __init__(self, formats: list[dict]):
        super().__init__()
        self._formats = formats
        self.rows: list[_TokenFormatRow] = []
        self.empty = _note("先在组合区添加词段，再为每个词段选择格式函数")
        self.empty.setMinimumHeight(self.HINT_ROW_HEIGHT)
        self.empty.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.body.addWidget(self.empty)
        self.legacy_format = _note()
        self.body.addWidget(self.legacy_format)
        self.legacy_format.hide()

    @property
    def has_errors(self) -> bool:
        return any(row.chain.errors or row.name_error.text() for row in self.rows)

    def rename_token(self, old_name: str, new_name: str) -> None:
        for row in self.rows:
            if row.name == old_name:
                row.set_name(new_name)

    def focus_token(self, index: int) -> NameEdit | None:
        """按组合引用顺序定位名称编辑，同名引用仍对应各自的行。"""
        if 0 <= index < len(self.rows):
            edit = self.rows[index].name_edit
            edit.setFocus(Qt.FocusReason.MouseFocusReason)
            edit.selectAll()
            return edit
        return None

    def set_tokens(
        self, tokens: list[tuple[str, str]], values: Mapping[str, str]
    ) -> None:
        if [name for name, _ in tokens] != [row.name for row in self.rows]:
            # 组合中增删其它引用时保留仍存在的行，避免丢失未完成的名称输入。
            matched = {}
            for old, new, size in SequenceMatcher(
                a=[row.name for row in self.rows],
                b=[name for name, _ in tokens],
                autojunk=False,
            ).get_matching_blocks():
                for offset in range(size):
                    matched[new + offset] = self.rows[old + offset]
            for row in self.rows:
                self.body.removeWidget(row)
                if row not in matched.values():
                    row.hide()
                    row.deleteLater()
            self.rows.clear()
            for index, (name, spec) in enumerate(tokens):
                row = matched.get(index)
                if row is None:
                    row = _TokenFormatRow(index, name, spec, self._formats)
                    row.chain.changed.connect(
                        lambda spec, row=row: self.format_changed.emit(row.index, spec)
                    )
                    row.name_edit.textChanged.connect(
                        lambda name, row=row: self.name_changed.emit(row.index, name)
                    )
                row.set_index(index)
                self.body.insertWidget(index + 1, row)
                self.rows.append(row)
        self.empty.setVisible(not tokens)
        for row, (name, spec) in zip(self.rows, tokens):
            row.set_value(spec, values.get(name))

    def show_legacy_format(self, spec: str) -> None:
        self.legacy_format.setText(f"已保留原规则的整串格式：{spec}" if spec else "")
        self.legacy_format.setVisible(bool(spec))


class RuleOutputCard(EditorCard):
    def __init__(self):
        super().__init__()
        self.toml = TomlEdit.readonly()
        self.body.addWidget(self.toml)
