"""词流类型下拉：当前项文字右对齐，下拉箭头保留"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QComboBox, QStyle, QStyleOptionComboBox

from ..theme import T

__all__ = ["TypeCombo"]

# 词流类型下拉的固定宽度（px）
TYPE_W = 48


class TypeCombo(QComboBox):
    """词流类型下拉"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("role", "tok-type")
        self.setFixedWidth(TYPE_W)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        self.style().drawComplexControl(
            QStyle.ComplexControl.CC_ComboBox, opt, painter, self
        )
        text_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox,
            opt,
            QStyle.SubControl.SC_ComboBoxEditField,
            self,
        )
        painter.setPen(
            QColor(
                T("color.accent.strong" if self.underMouse() else "color.text.primary")
            )
        )
        painter.drawText(
            text_rect.adjusted(0, 0, -3, 0),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            self.currentText(),
        )
