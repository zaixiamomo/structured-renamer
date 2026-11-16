"""仅在 debug 主题显示的水平几何中线。"""

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..theme import ThemeManager

__all__ = ["DebugCenterGuide"]


class DebugCenterGuide(QWidget):
    """覆盖宿主的水平中线，自动跟随尺寸且不接收鼠标事件。"""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setGeometry(parent.rect())
        parent.installEventFilter(self)
        theme = ThemeManager.instance()
        theme.theme_changed.connect(self._sync_visibility)
        self._sync_visibility(theme.series)

    def _sync_visibility(self, series: str) -> None:
        self.setVisible(series == "debug")
        if series == "debug":
            self.raise_()

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.Resize:
            self.setGeometry(watched.rect())
        return super().eventFilter(watched, event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        pen = QPen(QColor("#ff0070"), 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        y = self.height() / 2
        painter.drawLine(QPointF(0, y), QPointF(self.width(), y))
