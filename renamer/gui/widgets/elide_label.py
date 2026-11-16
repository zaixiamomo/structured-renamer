"""按可用宽度右省略的标签，文本再长也不撑宽所属行"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QLabel, QSizePolicy

__all__ = ["ElideLabel"]


class ElideLabel(QLabel):
    """按可用宽度右省略的标签"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._apply()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply()

    def setText(self, text: str) -> None:
        self._full = text
        self._apply()

    def _apply(self) -> None:
        elided = QFontMetrics(self.font()).elidedText(
            self._full, Qt.TextElideMode.ElideRight, max(1, self.width())
        )
        if elided != self.text():
            super().setText(elided)
