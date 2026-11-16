"""流式布局：子项超行宽自动换行，词池/词段/组合区共用"""

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLabel, QLayout

__all__ = ["FlowLayout"]


class FlowLayout(QLayout):
    """子项超行宽自动换行的流式布局"""

    def __init__(self, parent=None, margin: int = 0, spacing: int = 6):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self._spacing = spacing
        self._items: list = []

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        m = self.contentsMargins()
        size = QSize(0, 0)
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return QSize(
            size.width() + m.left() + m.right(),
            size.height() + m.top() + m.bottom(),
        )

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        """逐字符/逐件排布：先按宽分出行（含可折行子件收缩），再对每行子件纵向居中"""
        m = self.contentsMargins()
        if not self._items:
            return m.top() + m.bottom()
        left = rect.x() + m.left()
        right = rect.right() - m.right()
        rows: list = []  # 每行 ([(item, w, h)], 行高)
        row: list = []
        x = left
        line_h = 0
        for item in self._items:
            hint = item.sizeHint()
            w, h = hint.width(), hint.height()
            # 当前行放不下 → 换行（与子件是否可折行无关）
            if x + w > right + 1 and row:
                rows.append((row, line_h))
                row = []
                x = left
                line_h = 0
            # 独占一行仍放不下：子件若是开启自动换行的 QLabel，收缩到行内宽折行
            # （其余子件如词 chip 保持原样，溢出行为不变）
            if x + w > right + 1:
                wd = item.widget()
                if isinstance(wd, QLabel) and wd.wordWrap():
                    w = right - x + 1
                    h = wd.heightForWidth(w)
            row.append((item, w, h))
            x += w + self._spacing
            line_h = max(line_h, h)
        if row:
            rows.append((row, line_h))

        y = rect.y() + m.top()
        for n, (row_items, row_h) in enumerate(rows):
            x = left
            for item, w, h in row_items:
                if not test_only:
                    # 行内纵向居中：高矮子件（胶囊 vs 字面量）共中线，避免顶对齐凸底
                    item.setGeometry(
                        QRect(QPoint(x, y + (row_h - h) // 2), QSize(w, h))
                    )
                x += w + self._spacing
            if n < len(rows) - 1:
                y += row_h + self._spacing
        return y + row_h - rect.y() + m.bottom()
