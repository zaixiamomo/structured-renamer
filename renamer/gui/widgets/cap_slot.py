"""能力输入/输出槽位：灰态与绑定/成功态由 state 属性驱动 QSS"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSpacerItem

from .remove_button import RemoveButton
from .token_chip import MIME_TOKEN

__all__ = ["CapSlot"]


class _InputValueLabel(QLabel):
    """沿用空态单行行距，避免绑定值的后备字体撑高槽位。"""

    def sizeHint(self):
        size = super().sizeHint()
        size.setHeight(self.fontMetrics().lineSpacing())
        return size

    def minimumSizeHint(self):
        size = super().minimumSizeHint()
        size.setHeight(self.fontMetrics().lineSpacing())
        return size


class CapSlot(QFrame):
    """能力输入/输出槽位"""

    token_dropped = Signal(str, int)  # (field_key, tid)
    unbind_requested = Signal(str)  # field_key
    output_activate = Signal(str)  # field_key（输出槽左键激活）
    output_deactivate = Signal(str)  # field_key（输出槽右键取消）

    def __init__(self, field_key: str, drops: bool = True, parent=None):
        super().__init__(parent)
        self._field = field_key
        self._output_name = field_key.rsplit(":", 1)[-1].lower()
        self._bound = False
        self._drops = drops
        self._produced = False
        self.setProperty("role", "slot")
        self.setProperty("state", "idle")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAcceptDrops(drops)
        self.setToolTip(field_key)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(7, 4, 7, 4)
        lay.setSpacing(6)

        cap = QLabel(field_key)
        cap.setProperty("role", "slot-cap")
        lay.addWidget(cap)
        self._cap = cap

        self._val = _InputValueLabel("") if drops else QLabel()
        self._val.setProperty("role", "slot-val")
        lay.addWidget(self._val, 1)

        self._unbind = RemoveButton("解除绑定", self)
        self._unbind.setVisible(False)
        self._unbind.clicked.connect(self._emit_unbind)
        # 按钮利用槽位上下留白；布局只预留宽度，不撑高原有文字行。
        self._unbind_space = QSpacerItem(0, 0)
        lay.addItem(self._unbind_space)
        self.set_idle()

    def _position_unbind(self) -> None:
        right = self.contentsRect().right() - self.layout().contentsMargins().right()
        self._unbind.move(
            right - self._unbind.width() + 1,
            (self.height() - self._unbind.height()) // 2,
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_unbind()

    def _emit_unbind(self) -> None:
        self.unbind_requested.emit(self._field)

    # 状态切换（repolish 触发 QSS 属性选择器）
    def _set_state(
        self, state: str, value: str, unbind: bool, cap_visible: bool = True
    ) -> None:
        if self.property("state") != state:
            self.setProperty("state", state)
            self.style().unpolish(self)
            self.style().polish(self)
        self._cap.setVisible(cap_visible)
        self._val.setText(value)
        self._unbind_space.changeSize(
            self._unbind.width() + self.layout().spacing() if unbind else 0, 0
        )
        self.layout().invalidate()
        self._unbind.setVisible(unbind)
        self._position_unbind()
        self._bound = unbind
        self._produced = state in ("done", "done-off")

    def set_idle(self) -> None:
        if self._drops:
            self._set_state("idle", "", False, True)
        else:
            # 仅恢复刚添加时的显示占位，不重新激活已删除的产出词段。
            self._set_state("done-off", f"= {self._output_name}", False, True)
            self._produced = False

    def set_bound(self, value: str, *, unbind: bool = True) -> None:
        """输入槽绑定：只显示词段实际内容（隐藏字段 key 与箭头）"""
        self._set_state("bound", value, unbind, False)

    def set_done(
        self, value: str | None, active: bool = True, *, name: str | None = None
    ) -> None:
        """输出词段可选用；无预览时保留名称占位，有预览时只显示值。"""
        if name is not None:
            self._output_name = name
        self._set_state(
            "done" if active else "done-off",
            f"= {self._output_name}" if value is None else value,
            False,
            value is None,
        )

    # 输出槽点击：左键激活 / 右键取消（仅产出态生效）
    def mousePressEvent(self, event) -> None:
        if not self._drops and self._produced:
            if event.button() == Qt.MouseButton.LeftButton:
                self.output_activate.emit(self._field)
                event.accept()
                return
            if event.button() == Qt.MouseButton.RightButton:
                self.output_deactivate.emit(self._field)
                event.accept()
                return
        super().mousePressEvent(event)

    # 拖放（仅输入槽启用）
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(MIME_TOKEN):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(MIME_TOKEN):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        md = event.mimeData()
        data = md.data(MIME_TOKEN)
        if data:
            try:
                tid = int(bytes(data).decode("utf-8"))
            except ValueError:
                event.ignore()
                return
            self.token_dropped.emit(self._field, tid)
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()
