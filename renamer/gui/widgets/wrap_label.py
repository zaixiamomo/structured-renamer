"""任意字符处折行的纯文本标签

Qt 原生 QLabel.wordWrap 只按空白/词边界断行；无空格的长文本（如文件名）
即使开了 wordWrap 也不会换行、无法随宽度动态重排。本件把文本按给定宽度
逐字符贪心排布，heightForWidth 与 paint 使用同一套排布，宽度变化即时重排。
"""

from PySide6.QtCore import QSize
from PySide6.QtGui import QPainter, QPalette
from PySide6.QtWidgets import QLabel

__all__ = ["WrapLabel"]


class WrapLabel(QLabel):
    """任意字符处折行的纯文本标签（QLabel 子类，沿用 QSS 取色/字体）"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        # FlowLayout 依赖 wordWrap 标志识别可折行子件（见 flow_layout._do_layout）
        self.setWordWrap(True)

    def _text_width(self) -> int:
        return self.fontMetrics().horizontalAdvance(self.text())

    def _wrap(self, width: int) -> list[str]:
        """按 width 逐字符贪心折行；超宽字符单独成行，空文本返回单行空串"""
        fm = self.fontMetrics()
        text = self.text()
        if not text or width <= 0:
            return [text]
        lines: list[str] = []
        cur = ""
        cur_w = 0
        for ch in text:
            cw = fm.horizontalAdvance(ch)
            if cur and cur_w + cw > width:
                lines.append(cur)
                cur = ch
                cur_w = cw
            else:
                cur += ch
                cur_w += cw
        lines.append(cur)
        return lines

    def _line_height(self) -> int:
        return self.fontMetrics().height()

    def sizeHint(self) -> QSize:
        return QSize(self._text_width(), self._line_height())

    def minimumSizeHint(self) -> QSize:
        # 允许流式布局把本件压缩到任意窄（折行替代截断）
        return QSize(0, self._line_height())

    def heightForWidth(self, width: int) -> int:
        return len(self._wrap(width)) * self._line_height()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setFont(self.font())
        # 与 QLabel 一致取 QSS color（映射到 WindowText 角色）
        painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        fm = self.fontMetrics()
        y = 0
        for line in self._wrap(max(1, self.width())):
            painter.drawText(0, fm.ascent() + y, line)
            y += fm.height()
