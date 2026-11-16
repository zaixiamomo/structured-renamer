"""编辑页滚动区：按当前页收敛高度，合并延迟布局并恢复滚动位置。"""

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import QFrame, QScrollArea

from .panel_stack import PanelStack


class PanelScrollArea(QScrollArea):
    """小于底部留白的溢出保持在顶部；实际内容溢出时才允许滚动。"""

    _OVERFLOW_TOLERANCE = 20

    def __init__(self, stack: PanelStack, parent=None):
        super().__init__(parent)
        self._stack = stack
        self._rounds = 0
        self._restore_value: int | None = None
        self.setObjectName("sidePanelBody")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.viewport().setObjectName("sidePanelViewport")
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWidget(stack)
        # Timer 随滚动区销毁；切页会取消旧恢复任务，避免迟到回调访问旧页面。
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._settle)
        stack.currentChanged.connect(self._cancel_pending)
        self.verticalScrollBar().rangeChanged.connect(self._sync_scrollbar)
        self._sync_scrollbar(0, 0)

    def refit(self) -> None:
        self._rounds = max(self._rounds, 2)
        self._timer.start(0)

    def restore_position(self, value: int) -> None:
        self._restore_value = value
        self._rounds = 3
        self._settle()

    def _cancel_pending(self) -> None:
        self._timer.stop()
        self._rounds = 0
        self._restore_value = None

    def _settle(self) -> None:
        viewport = self.viewport()
        if self.isVisible() and viewport.width() > 0 and viewport.height() > 0:
            need = self._stack.current_content_height(viewport.width())
            target = max(viewport.height(), need)
            if need > 0 and self._stack.height() != target:
                self._stack.resize(self._stack.width(), target)
        bar = self.verticalScrollBar()
        if self._restore_value is not None:
            bar.setValue(min(self._restore_value, bar.maximum()))
        if bar.maximum() <= self._OVERFLOW_TOLERANCE:
            bar.setValue(0)
        self._rounds -= 1
        if self._rounds > 0:
            self._timer.start(0)
        else:
            self._restore_value = None

    def _sync_scrollbar(self, _minimum: int, maximum: int) -> None:
        policy = (
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if maximum > self._OVERFLOW_TOLERANCE
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        if self.verticalScrollBarPolicy() != policy:
            self.setVerticalScrollBarPolicy(policy)
        if maximum <= self._OVERFLOW_TOLERANCE:
            self.verticalScrollBar().setValue(0)

    def viewportEvent(self, event) -> bool:
        if (
            event.type() == QEvent.Type.Wheel
            and self.verticalScrollBar().maximum() <= self._OVERFLOW_TOLERANCE
        ):
            return True
        return super().viewportEvent(event)
