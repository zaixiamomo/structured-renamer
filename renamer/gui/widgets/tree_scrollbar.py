"""文件树左侧专属滚动条：比例 thumb（半透明）+ 小地图两色标记"""

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..state.status_style import STATUS_STYLE
from ..theme import T, ThemeManager

__all__ = ["TreeScrollBar"]

# 轨道 / thumb 宽（可滚动态居中）
SB_W = 10
# 小地图标记宽（画在轨道上，thumb 半透明透出）
MARK_W = 4
# thumb 填充透明度（0-255）：透出下方小地图标记
THUMB_ALPHA = 140
# 控件宽（恒宽）：出现/消失不再收窄，避免右侧树视图随滚动条宽度变化整体平移
WIDGET_W = int(T("size.scrollbar.w"))


class TreeScrollBar(QWidget):
    """文件树左侧专属自绘滚动条"""

    def __init__(self, tree, parent=None):
        super().__init__(parent)
        self.setObjectName("treeScrollBar")
        self.setFixedWidth(WIDGET_W)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tree = tree
        self._dragging = False
        self._drag_start_y = 0
        self._drag_start_top = 0.0
        # 内容是否需要滚动（决定是否绘制轨道/thumb）
        self._scrollable = False

        # 小地图缓存 ``(位置比例, 状态色令牌键)``：树结构/状态变化时才重算，paint 只从缓存绘制
        self._marks: list[tuple[float, str]] = []
        self._mark_n = 0

        tree.verticalScrollBar().valueChanged.connect(self.update)
        tree.verticalScrollBar().rangeChanged.connect(self._on_range_changed)
        tree.model_changed.connect(self._rebuild_cache)
        ThemeManager.instance().theme_changed.connect(self.update)
        self._refresh_scrollable()
        self._rebuild_cache()

    # 可滚动状态
    def _on_range_changed(self, *_args) -> None:
        """内部滚动条范围变化（内容行数 / 视口高度变动）时刷新可滚动状态"""
        self._refresh_scrollable()
        self.update()

    def _refresh_scrollable(self) -> None:
        """内容高于视口才可滚动；仅切换轨道/thumb 与标记的绘制模式"""
        scrollable = self._tree.content_height() > self._tree.viewport_height()
        if scrollable != self._scrollable:
            self._scrollable = scrollable
            self.update()

    # 几何
    def _thumb_geometry(self) -> tuple[float, float]:
        """返回 ``(thumb_top, thumb_height)``（像素）"""
        h = self.height()
        view_h = self._tree.viewport_height()
        content_h = self._tree.content_height()
        thumb_h = (view_h / max(1, content_h)) * h
        # clamp 到 [最小 thumb 高, 控件高]，内容短于视口时不越界
        thumb_h = min(max(thumb_h, int(T("size.thumb.min"))), h)
        max_top = max(0, h - thumb_h)
        frac = (
            self._tree.scroll_value() / max(1, content_h - view_h)
            if content_h > view_h
            else 0.0
        )
        return frac * max_top, thumb_h

    # 交互
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        if not self._scrollable:
            event.accept()
            return
        top, thumb_h = self._thumb_geometry()
        y = event.position().y()
        if top <= y <= top + thumb_h:
            self._dragging = True
            self._drag_start_y = y
            self._drag_start_top = top
        else:
            # 点轨道跳转：thumb 中心对准点击处
            view_h = self._tree.viewport_height()
            content_h = self._tree.content_height()
            frac = (y - thumb_h / 2) / max(1, view_h - thumb_h)
            self._tree.set_scroll_value(frac * max(0, content_h - view_h))
        self.update()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._dragging:
            super().mouseMoveEvent(event)
            return
        view_h = self._tree.viewport_height()
        content_h = self._tree.content_height()
        _, thumb_h = self._thumb_geometry()
        dy = event.position().y() - self._drag_start_y
        new_top = self._drag_start_top + dy
        frac = new_top / max(1, view_h - thumb_h)
        self._tree.set_scroll_value(frac * max(0, content_h - view_h))
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self.update()
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta:
            step = self._tree.row_step()
            self._tree.scroll_delta(-delta * step // 120)
            event.accept()
        else:
            super().wheelEvent(event)

    # 绘制
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(T("color.bg.surface2")))

        h = self.height()
        x = (self.width() - SB_W) // 2  # 轨道左缘（仅可滚动态使用）
        mx = (self.width() - MARK_W) // 2  # 标记左缘（两态都居中）

        # 轨道（可滚动 + hover/拖动时显示浅底色）
        if self._scrollable and (self._dragging or self.underMouse()):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(T("color.bg.surface3")))
            painter.drawRoundedRect(QRect(x, 0, SB_W, h), 6, 6)

        # 小地图两色标记（画在轨道上，thumb 半透明透出）
        self._paint_marks(painter, h, mx)
        # Debug：滚动条整条填的底色与树列一致，光靠颜色看不出它是独立组件；虚线框标出
        self._paint_debug_outline(painter)

        # thumb（半透明填充，不遮挡小地图；不可滚动态不绘制）
        if not self._scrollable:
            return
        top, thumb_h = self._thumb_geometry()
        circle = thumb_h <= int(T("size.thumb.circle"))
        if circle:
            cy = top + thumb_h / 2
            col = QColor(T("color.accent.strong"))
            col.setAlpha(THUMB_ALPHA)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(col)
            painter.drawEllipse(QPoint(x + SB_W // 2, int(cy)), SB_W // 2, SB_W // 2)
        else:
            hover = self._dragging or self.underMouse()
            col = QColor(T("color.accent" if hover else "color.sb.thumb"))
            col.setAlpha(THUMB_ALPHA)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(col)
            painter.drawRoundedRect(QRect(x, int(top), SB_W, int(thumb_h)), 6, 6)

    def _paint_debug_outline(self, painter: QPainter) -> None:
        """debug 系列下给自绘滚动条描外框（QSS 不会画到自绘控件上）"""
        if ThemeManager.instance().series != "debug":
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        pen = QPen(QColor("#f9a825"), 1)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

    def _rebuild_cache(self) -> None:
        """树结构 / 状态变化时重算小地图缓存（位置比例到状态色令牌键）"""
        rows = self._tree.visible_rows()
        starts = self._tree.row_starts()
        self._mark_n = len(rows)
        self._marks = []
        total = max(1, self._tree.content_height())
        for i, (node, _depth) in enumerate(rows):
            s = self._tree.row_status(node)
            if s is not None:
                mark = STATUS_STYLE[s][1]
                if mark is not None:
                    # 行高可不均匀（预览幽灵行占双高），按行真实起点定标记位置
                    self._marks.append((starts[i] / total, mark))
        self.update()

    def _paint_marks(self, painter: QPainter, h: int, mx: int) -> None:
        if not self._mark_n:
            return
        total = self._mark_n
        # 纵向标尺：可滚动则整段内容缩放到控件高；不可滚动按内容原高 1:1，标记贴合实际文本行
        span = h if self._scrollable else self._tree.content_height()
        mark_h = max(2.0, span / total - 1)
        for frac, key in self._marks:
            top = frac * span
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(T(key)))
            painter.drawRoundedRect(QRectF(mx, top, MARK_W, mark_h), 2, 2)
