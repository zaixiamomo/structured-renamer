"""组合文档内联词段：复用 TokenChip 外观，以单个文档对象参与排版。"""

from math import ceil

from PySide6.QtCore import QPointF, QSizeF, Qt
from PySide6.QtGui import QFontMetricsF, QPixmap, QPyTextObject

from ..theme import ThemeManager
from .compose_document import TOKEN_LABEL_PROPERTY
from .token_chip import TokenChip


class ComposeTokenRenderer(QPyTextObject):
    def __init__(self, parent):
        super().__init__(parent)
        self._images = {}

    def clear(self) -> None:
        self._images.clear()

    def _image(self, fmt):
        label = fmt.property(TOKEN_LABEL_PROPERTY) or ""
        parent = self.parent()
        key = (label, ThemeManager.instance().series, parent.devicePixelRatioF())
        if key not in self._images:
            # 独立隐藏控件，避免在文档排版回调中改变编辑器子树导致重入。
            chip = TokenChip(-1, label)
            chip.hide()
            chip.ensurePolished()
            chip.resize(chip.sizeHint())
            dpr = parent.devicePixelRatioF()
            image = QPixmap(ceil(chip.width() * dpr), ceil(chip.height() * dpr))
            image.setDevicePixelRatio(dpr)
            image.fill(Qt.GlobalColor.transparent)
            chip.render(image)
            self._images[key] = image
            chip.deleteLater()
        return self._images[key]

    def intrinsicSize(self, document, position, fmt):
        size = self._image(fmt).deviceIndependentSize()
        return QSizeF(size.width() + 4, size.height() + 2)

    def drawObject(self, painter, rect, document, position, fmt):
        image = self._image(fmt)
        block = document.findBlock(position)
        layout = block.layout()
        line = layout.lineForTextPosition(position - block.position())
        metrics = QFontMetricsF(self.parent().font())
        baseline = layout.position().y() + line.y() + line.ascent()
        center = baseline + (metrics.descent() - metrics.ascent()) / 2
        top = center - image.deviceIndependentSize().height() / 2
        painter.drawPixmap(QPointF(rect.left() + 2, top), image)
