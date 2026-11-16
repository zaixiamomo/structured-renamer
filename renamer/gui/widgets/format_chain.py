"""词段格式链：固定原始行，在缩进子行编辑并预览每一步结果。"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from renamer.app.authoring import AuthoringService

from .elide_label import ElideLabel
from .remove_button import RemoveButton
from .status_label import StatusLabel

__all__ = ["FormatChainEdit"]

_PRESERVED_DATA = "__preserved__"


class _FormatCombo(QComboBox):
    def __init__(self, formats: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.setProperty("role", "select-ghost")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        for definition in formats:
            self.addItem(definition["id"], definition["id"])
            self.setItemData(
                self.count() - 1,
                definition["description"],
                Qt.ItemDataRole.ToolTipRole,
            )
        self.setCurrentIndex(-1)
        self.currentTextChanged.connect(self._fit_width)
        self._fit_width()

    def _fit_width(self) -> None:
        self.setFixedWidth(
            max(48, self.fontMetrics().horizontalAdvance(self.currentText()) + 28)
        )

    def showPopup(self) -> None:
        self.view().setMinimumWidth(
            max(
                (
                    self.fontMetrics().horizontalAdvance(self.itemText(i))
                    for i in range(self.count())
                ),
                default=0,
            )
            + 36
        )
        super().showPopup()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        self._fit_width()

    def wheelEvent(self, event) -> None:
        event.ignore()


class _StepRow(QWidget):
    """步骤结果与缩进共用布局；缩进按预览字体的两个字符宽计算。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._preview_offset = 0
        self._main_layout = QHBoxLayout(self)
        self._main_layout.setSpacing(4)
        self.preview = ElideLabel(parent=self)
        self.preview.setProperty("role", "tok-raw")
        self.preview.setTextFormat(Qt.TextFormat.PlainText)
        self.preview.installEventFilter(self)
        self._main_layout.addWidget(self.preview, 1)
        self.set_preview_offset(0)

    def set_preview_offset(self, offset: int) -> None:
        self._preview_offset = max(0, offset)
        indent = self.preview.fontMetrics().horizontalAdvance("00")
        self._main_layout.setContentsMargins(self._preview_offset + indent, 0, 0, 0)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.preview and event.type() == QEvent.Type.FontChange:
            self.set_preview_offset(self._preview_offset)
        return super().eventFilter(watched, event)


class _FormatStep(_StepRow):
    changed = Signal()
    remove_requested = Signal()

    def __init__(
        self, formats: list[dict], name: str, args: tuple[str, ...], parent=None
    ) -> None:
        super().__init__(parent)
        self._definitions = {item["id"]: item for item in formats}
        self.combo = _FormatCombo(formats, self)
        self.combo.setObjectName("format-function")
        self._main_layout.addWidget(self.combo)
        self.remove_button = RemoveButton("删除此格式步骤", self)
        self.remove_button.setObjectName("format-remove")
        self._main_layout.addWidget(self.remove_button)
        self.set_call(name, args)
        self.combo.currentIndexChanged.connect(self._function_changed)
        self.remove_button.clicked.connect(self.remove_requested)

    @property
    def spec(self) -> str:
        return (
            AuthoringService.format_call(self._name, self._args) if self._name else ""
        )

    def set_call(self, name: str, args: tuple[str, ...]) -> None:
        self._name, self._args = name, args
        with QSignalBlocker(self.combo):
            previous = self.combo.findData(_PRESERVED_DATA)
            if previous >= 0:
                self.combo.removeItem(previous)
            index = self.combo.findData(name) if not args else -1
            preserved = bool(name) and index < 0
            if preserved:
                index = self.combo.count()
                self.combo.addItem(name, _PRESERVED_DATA)
                self.combo.model().item(index).setEnabled(False)
            self.combo.setCurrentIndex(index)
        self.combo._fit_width()
        definition = self._definitions.get(self._name, {})
        self.combo.setToolTip(
            f"已保留格式：{self.spec}；暂不提供编辑，可选择 lower、upper 或删除此步骤"
            if preserved
            else definition.get("description", "选择格式函数")
        )

    def _function_changed(self) -> None:
        name = self.combo.currentData() or ""
        if name == _PRESERVED_DATA:
            return
        self.set_call(name, ())
        self.changed.emit()


class FormatChainEdit(QWidget):
    """发出每次编辑后的格式链；投影相同语义时保留输入焦点与选区。"""

    changed = Signal(str)

    def __init__(self, formats: list[dict], spec: str = "", parent=None) -> None:
        super().__init__(parent)
        self._formats = [item for item in formats if item["id"] in {"lower", "upper"}]
        self._spec = ""
        self._errors: list[str] = []
        self._steps: list[_FormatStep] = []
        self._invalid_spec: str | None = None
        self._invalid_row: _StepRow | None = None
        self._prefix: QWidget | None = None
        self._sample: str | None = None
        self._preview_offset = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        header = QWidget(self)
        self._header_layout = QHBoxLayout(header)
        self._header_layout.setContentsMargins(0, 0, 0, 0)
        self._header_layout.setSpacing(4)
        self._header_layout.addStretch(1)
        self.add_button = QPushButton("＋", header)
        self.add_button.setObjectName("format-add")
        self.add_button.setProperty("role", "tok-add")
        self.add_button.setFixedSize(20, 20)
        self.add_button.setToolTip("添加格式步骤")
        self.add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_button.clicked.connect(self.add_step)
        self._header_layout.addWidget(self.add_button)
        layout.addWidget(header)
        self._steps_layout = QVBoxLayout()
        self._steps_layout.setSpacing(4)
        layout.addLayout(self._steps_layout)
        self.error_label = StatusLabel(self)
        self.error_label.setObjectName("format-errors")
        self.error_label.setProperty("role", "note")
        self.error_label.set_status("err")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)
        self.set_spec(spec)

    @property
    def spec(self) -> str:
        return self._spec

    @property
    def errors(self) -> list[str]:
        return list(self._errors)

    def set_prefix(self, widget: QWidget) -> None:
        """将原始预览和名称固定在加号前，增删步骤不移动该控件。"""
        if widget is self._prefix:
            return
        layout = self._header_layout
        item = layout.takeAt(0)
        if item.widget() is not None:
            item.widget().hide()
            item.widget().setParent(None)
        self._prefix = widget
        layout.insertWidget(0, widget, 1)
        widget.show()

    def set_sample(self, sample: str | None) -> None:
        """更新原始词段值，重新投影链上每一步的累计结果。"""
        self._sample = sample
        self._refresh_previews()

    def set_preview_offset(self, offset: int) -> None:
        """指定首行原始预览的起点；子行再缩进两个字符宽。"""
        self._preview_offset = max(0, offset)
        for step in self._steps:
            step.set_preview_offset(self._preview_offset)
        if self._invalid_row is not None:
            self._invalid_row.set_preview_offset(self._preview_offset)

    def set_spec(self, spec: str) -> None:
        if spec == self._spec:
            return
        try:
            calls = AuthoringService.parse_format(spec)
        except ValueError:
            calls = None
        if calls is not None:
            try:
                unchanged = calls == AuthoringService.parse_format(self._spec)
            except ValueError:
                unchanged = False
            if unchanged:
                self._spec = spec
                return
        self._spec = spec
        self._clear_invalid()
        desired = [(call.name, call.args) for call in calls] if calls else []
        for index, (name, args) in enumerate(desired):
            if index < len(self._steps):
                self._steps[index].set_call(name, args)
            else:
                self._append_step(name, args)
        for step in self._steps[len(desired) :]:
            self._discard_step(step)
        del self._steps[len(desired) :]
        if calls is None:
            self._invalid_spec = spec
            row = self._invalid_row = _StepRow(self)
            row.set_preview_offset(self._preview_offset)
            label = QLabel(spec, row)
            label.setObjectName("format-invalid")
            label.setProperty("role", "note")
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            row._main_layout.addWidget(label)
            remove = RemoveButton("删除此格式步骤", row)
            remove.setObjectName("format-remove")
            remove.clicked.connect(self._remove_invalid)
            row._main_layout.addWidget(remove)
            self._steps_layout.addWidget(row)
        self._validate()

    def _append_step(self, name: str, args: tuple[str, ...]) -> None:
        step = _FormatStep(self._formats, name, args, self)
        step.set_preview_offset(self._preview_offset)
        self._steps.append(step)
        self._steps_layout.addWidget(step)
        step.changed.connect(self._edited)
        step.remove_requested.connect(lambda: self._remove_step(step))

    def add_step(self) -> None:
        """追加待选择的格式槽，现有函数和参数保持不变。"""
        self._append_step("", ())
        self._refresh_previews()
        self.changed.emit(self._spec)

    def _remove_step(self, step: _FormatStep) -> None:
        self._steps.remove(step)
        self._discard_step(step)
        self._edited()

    def _discard_step(self, step: _FormatStep) -> None:
        self._steps_layout.removeWidget(step)
        step.hide()
        step.deleteLater()

    def _clear_invalid(self) -> None:
        if self._invalid_row is not None:
            self._steps_layout.removeWidget(self._invalid_row)
            self._invalid_row.hide()
            self._invalid_row.deleteLater()
        self._invalid_row = None
        self._invalid_spec = None

    def _remove_invalid(self) -> None:
        self._clear_invalid()
        self._edited()

    def _edited(self) -> None:
        parts = [self._invalid_spec] if self._invalid_spec is not None else []
        parts.extend(step.spec for step in self._steps if step.spec)
        self._spec = "|".join(parts)
        self._validate()
        self.changed.emit(self._spec)

    def _validate(self) -> None:
        self._errors = AuthoringService.validate_format(self._spec)
        self.error_label.setText("\n".join(self._errors))
        self.error_label.setVisible(bool(self._errors))
        self._refresh_previews()

    def _refresh_previews(self) -> None:
        parts = [self._invalid_spec] if self._invalid_spec is not None else []
        if self._invalid_row is not None:
            self._set_preview(self._invalid_row, self._invalid_spec)
        for step in self._steps:
            if step.spec:
                parts.append(step.spec)
            self._set_preview(step, "|".join(parts))

    def _set_preview(self, row: _StepRow, spec: str) -> None:
        errors = AuthoringService.validate_format(spec)
        if self._sample is None:
            result = "未提供示例"
        elif errors:
            result = "—"
        else:
            # 每一步从原始值执行累计链，与核心的执行顺序保持一致。
            result = AuthoringService.format_value(self._sample, spec)
        row.preview.setText(result)
        row.preview.setToolTip("\n".join(errors) if errors else result)
