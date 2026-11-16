"""按笔画覆盖面积的纵向重心居中的单行文字。"""

from math import ceil

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QPainter,
    QPalette,
    QTextLayout,
)
from PySide6.QtWidgets import QLabel

__all__ = ["OpticalLabel"]


class OpticalLabel(QLabel):
    """左对齐的单行纯文本标签，沿用 QLabel 尺寸提示与 QSS 字体、颜色。

    笔画覆盖面积的重心是光学居中的近似，区别于字体行框或字形包围框居中。
    支持分段着色；不解析 HTML，不支持换行、选区或 QLabel 的边框/缩进。
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self._ink_key: tuple[str, QFont, float] | None = None
        self._ink_center = 0.0
        self._formats: list[QTextLayout.FormatRange] = []

    def setText(self, text: str) -> None:
        """设置普通文字并清除分段颜色。"""
        self._formats = []
        super().setText(text)
        self.update()

    def set_colored_text(self, segments: list[tuple[str, QColor | None]]) -> None:
        """设置同一行的文字与局部颜色；None 表示沿用 QSS 文字颜色。"""
        self.setText("".join(text for text, _ in segments))
        offset = 0
        for text, color in segments:
            # Qt 的文字范围使用 UTF-16 单元，兼容非 BMP 字符。
            length = len(text.encode("utf-16-le")) // 2
            if color is not None and length:
                span = QTextLayout.FormatRange()
                span.start, span.length = offset, length
                span.format.setForeground(color)
                self._formats.append(span)
            offset += length
        self.update()

    def _measure_ink_center(self, text: str, font: QFont, dpr: float) -> float:
        # 在透明画布上按实际缩放测量；四周留白避免抗锯齿边缘被截断。
        bounds = QFontMetricsF(font).tightBoundingRect(text).adjusted(-2, -2, 2, 2)
        origin = QPointF(-bounds.left(), ceil(-bounds.top() * dpr) / dpr)
        mask = QImage(
            ceil(bounds.width() * dpr),
            ceil(bounds.height() * dpr),
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        mask.setDevicePixelRatio(dpr)
        mask.fill(Qt.GlobalColor.transparent)
        painter = QPainter(mask)
        painter.setFont(font)
        painter.setPen(Qt.GlobalColor.white)
        painter.drawText(origin, text)
        painter.end()

        alpha = mask.convertToFormat(QImage.Format.Format_Alpha8)
        pixels = alpha.constBits()
        stride = alpha.bytesPerLine()
        rows = [
            sum(pixels[y * stride : y * stride + alpha.width()])
            for y in range(alpha.height())
        ]
        area = sum(rows)
        if not area:  # 零宽字符等可能没有可见笔画。
            return 0.0
        # 用像素中心而非边缘计量，并转换为相对绘制基线的逻辑坐标。
        return (
            sum((y + 0.5) * weight for y, weight in enumerate(rows)) / area / dpr
            - origin.y()
        )

    def paintEvent(self, event) -> None:
        text, font, dpr = self.text(), self.font(), self.devicePixelRatioF()
        if not text.strip():
            return
        key = (text, font, dpr)
        if key != self._ink_key:
            self._ink_center = self._measure_ink_center(text, font, dpr)
            self._ink_key = key

        rect = QRectF(self.contentsRect())
        # 测量和绘制都把基线放在物理像素边界，避免分数缩放的栅格相位差。
        baseline = round((rect.center().y() - self._ink_center) * dpr) / dpr
        painter = QPainter(self)
        painter.setFont(font)
        # QSS 的 color 已投影到调色板，与原生 QLabel 保持一致。
        painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        if self._formats:
            layout = QTextLayout(text, font, self)
            layout.setFormats(self._formats)
            layout.beginLayout()
            line = layout.createLine()
            line.setNumColumns(len(text.encode("utf-16-le")) // 2)
            layout.endLayout()
            layout.draw(painter, QPointF(rect.left(), baseline - line.ascent()))
        else:
            painter.drawText(QPointF(rect.left(), baseline), text)
