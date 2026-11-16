"""模板词段行：编辑名称、类型和候选值，通过信号交给页面更新草稿。"""

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QWidget

from .elide_label import ElideLabel
from .name_edit import NameEdit
from .remove_button import RemoveButton
from .type_combo import TypeCombo


class TemplateTokenRow(QWidget):
    """行内编辑不重建控件，保留焦点和未完成的候选表达式。"""

    name_edited = Signal(str)
    type_changed = Signal(str)
    candidates_edited = Signal(str)
    remove_requested = Signal()

    def __init__(
        self,
        index: int,
        *,
        name: str,
        type_name: str,
        sample: str | None,
        candidates: str,
    ):
        super().__init__()
        self.setProperty("role", "tok-row")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        seq = QLabel(f"{index:02d}")
        seq.setProperty("role", "tok-seq")
        seq.setFixedWidth(22)
        raw = ElideLabel(sample if sample is not None else "未提供示例")
        raw.setProperty("role", "tok-raw")

        self.name_edit = NameEdit(name)
        self.name_edit.setProperty("role", "tok-token")
        self.name_edit.setAcceptDrops(False)
        self.name_edit.settle_display()
        self.type_combo = TypeCombo()
        # TODO: date / enum 的显示效果未完成，暂不提供新建选项，见 docs/todos.md。
        for display, value in (
            ("str", "string"),
            ("int", "int"),
        ):
            self.type_combo.addItem(display, value)
        index = self.type_combo.findData(type_name)
        if index < 0:
            self.type_combo.addItem(type_name, type_name)
            index = self.type_combo.count() - 1
        self.type_combo.setCurrentIndex(index)

        self.values_edit = QLineEdit(candidates)
        self.values_edit.setProperty("role", "tok-values")
        self.values_edit.setFixedWidth(56)
        self.values_edit.setPlaceholderText("a,b；含逗号用引号")
        self.values_edit.setVisible(type_name == "enum")
        self.values_edit.setAcceptDrops(False)
        remove = RemoveButton("删除词段")

        layout.addWidget(seq)
        layout.addWidget(raw, 1)
        for widget in (self.name_edit, self.type_combo, self.values_edit, remove):
            layout.addWidget(widget)
        self.name_edit.textChanged.connect(self.name_edited)
        self.type_combo.currentIndexChanged.connect(self._type_changed)
        self.values_edit.textChanged.connect(self.candidates_edited)
        remove.clicked.connect(self.remove_requested)

    def _type_changed(self) -> None:
        self.values_edit.setVisible(self.type_combo.currentData() == "enum")
        self.type_changed.emit(self.type_combo.currentData())

    def set_candidates(self, text: str) -> None:
        with QSignalBlocker(self.values_edit):
            self.values_edit.setText(text)

    def focus_name(self) -> None:
        self.name_edit.setFocus(Qt.FocusReason.MouseFocusReason)
        self.name_edit.selectAll()
