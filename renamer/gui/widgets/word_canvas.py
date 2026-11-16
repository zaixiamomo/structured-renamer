"""划词画布：字符级拖选 + token 类型着色 + 右键确认/撤销"""

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget

from renamer.app.authoring import Span

from ..theme import T, ThemeManager

__all__ = ["WordCanvas"]


class WordCanvas(QWidget):
    """示例文件名的字符级划词画布"""

    # 拖选区间变化（参数为起止字符索引，含端点；左键按下即开始）
    selection_changed = Signal(int, int)
    # 右键确认选区即生成新 token（参数为选区起止字符索引，含端点）
    selection_confirmed = Signal(int, int)
    # 左键点击已标 token 即在词流中定位（参数为 token id）
    token_clicked = Signal(int)
    # 右键点击已标 token 即撤销该 token（参数为 token id）
    token_unconfirmed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._chars: list[str] = []
        self._token_of: list[int | None] = []
        self._spans: dict[int, Span] = {}
        # 布局缓存：``(行起始字符, 行结束字符, 行顶部 y)``
        self._lines: list[tuple[int, int, int]] = []
        self._content_h = 0
        # 拖选状态：选区 [sel_s, sel_e] 含端点，均为自由字符
        self._sel_s = -1
        self._sel_e = -1
        self._anchor = -1
        self._dragging = False

        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        ThemeManager.instance().theme_changed.connect(self.update)

    # 数据（由外部面板注入，本控件不持有业务状态）
    def set_content(
        self, chars: list[str], token_of: list[int | None], spans: dict[int, Span]
    ) -> None:
        """注入字符序列与 token 归属，重建布局并重绘"""
        self._chars = list(chars)
        self._token_of = list(token_of)
        self._spans = spans
        self._sel_s = self._sel_e = self._anchor = -1
        self._dragging = False
        self._reflow()
        self.updateGeometry()
        self.update()

    def clear_selection(self) -> None:
        """清除当前拖选（保留 token 归属）"""
        self._sel_s = self._sel_e = self._anchor = -1
        self._dragging = False
        self.update()

    # 几何
    def _reflow(self) -> None:
        """按当前宽度手动换行，记录每行字符区间与内容总高"""
        fm = QFontMetrics(self.font())
        width = self.width() if self.width() > 0 else 360
        line_h = fm.height()
        lines: list[tuple[int, int, int]] = []
        cur: list[int] = []
        x = 0
        y = 0
        for i, ch in enumerate(self._chars):
            w = fm.horizontalAdvance(ch)
            if cur and x + w > width:
                lines.append((cur[0], cur[-1], y))
                y += line_h
                cur = [i]
                x = w
            else:
                cur.append(i)
                x += w
        if cur:
            lines.append((cur[0], cur[-1], y))
        self._lines = lines
        self._content_h = (lines[-1][2] + line_h) if lines else line_h
        # 钉住最小高度 = 内容高，否则布局收缩会把画布压扁
        if self.minimumHeight() != self._content_h:
            self.setMinimumHeight(self._content_h)

    def sizeHint(self) -> QSize:
        self._reflow()
        return QSize(360, self._content_h)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reflow()
        self.updateGeometry()
        self.update()

    def _hit(self, pos: QPoint) -> int | None:
        """命中字符索引（空白/越界返回 None）"""
        if not self._chars:
            return None
        fm = QFontMetrics(self.font())
        line_h = fm.height()
        for s0, e0, y in self._lines:
            if y <= pos.y() < y + line_h:
                x = 0
                for i in range(s0, e0 + 1):
                    w = fm.horizontalAdvance(self._chars[i])
                    if pos.x() < x + w:
                        return i
                    x += w
                return e0  # 行尾右侧空白即吸附行尾
        return None

    def _nearest_free(self, i: int) -> int | None:
        """返回与索引 ``i`` 最近的自由（非 token）字符索引；全 token 则 None"""
        n = len(self._chars)
        for d in range(n):
            if i - d >= 0 and self._token_of[i - d] is None:
                return i - d
            if i + d < n and self._token_of[i + d] is None:
                return i + d
        return None

    def _clamp_to_free(self, i: int, anchor: int) -> int:
        """拖选游标钳制：选区永不跨 token，确认后不可能重叠"""
        if i == anchor:
            return anchor
        step = 1 if i > anchor else -1
        j = anchor
        while j != i:
            nxt = j + step
            if 0 <= nxt < len(self._chars) and self._token_of[nxt] is None:
                j = nxt
            else:
                break
        return j

    # 事件
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._handle_left_press(event)
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        """与单击同等处理：避免 Windows 双击判定吞掉快速连续划词"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._handle_left_press(event)
        else:
            super().mouseDoubleClickEvent(event)

    def _handle_left_press(self, event) -> None:
        i = self._hit(event.pos())
        if i is None:
            event.ignore()
            return
        if self._token_of[i] is not None:
            # 点到已标 token：清除拖选、通知词流定位
            self._sel_s = self._sel_e = self._anchor = -1
            self._dragging = False
            self.token_clicked.emit(self._token_of[i])
            self.update()
            event.accept()
            return
        f = self._nearest_free(i)
        if f is None:
            event.accept()
            return
        self._anchor = f
        self._sel_s = f
        self._sel_e = f
        self._dragging = True
        self.update()
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if not self._dragging:
            # 光标反馈：token 上可点（手型）、literal 上可选（IBeam）
            i = self._hit(event.pos())
            want = (
                Qt.CursorShape.PointingHandCursor
                if (i is not None and self._token_of[i] is not None)
                else Qt.CursorShape.IBeamCursor
            )
            if self.cursor() != want:
                self.setCursor(want)
            super().mouseMoveEvent(event)
            return
        i = self._hit(event.pos())
        if i is None:
            return
        f = self._clamp_to_free(i, self._anchor)
        self._sel_s = min(self._anchor, f)
        self._sel_e = max(self._anchor, f)
        self.selection_changed.emit(self._sel_s, self._sel_e)
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:
        """右键：命中已标 token 则撤销；否则有有效选区则确认生成"""
        i = self._hit(event.pos())
        if i is not None and self._token_of[i] is not None:
            tid = self._token_of[i]
            self._sel_s = self._sel_e = self._anchor = -1
            self.update()
            self.token_unconfirmed.emit(tid)
            event.accept()
            return
        if self._sel_s >= 0 and self._sel_e >= self._sel_s:
            self.selection_confirmed.emit(self._sel_s, self._sel_e)
            event.accept()
            return
        event.ignore()

    # 绘制
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 选区/token 底色用 accent 向白混合 65% 的不透明强调色：accent.soft 太淡看不清
        _acc = QColor(T("color.accent"))
        _mark_bg = QColor(
            round(_acc.red() + (255 - _acc.red()) * 0.65),
            round(_acc.green() + (255 - _acc.green()) * 0.65),
            round(_acc.blue() + (255 - _acc.blue()) * 0.65),
        )
        # 相邻标记区之间的细分隔线（半透明）：连续划词无空格时靠它看得出边界
        _sep = QColor(T("color.accent.strong"))
        _sep.setAlphaF(0.45)
        fm = QFontMetrics(self.font())
        line_h = fm.height()

        # 底色 + 相邻标记块边界分隔线
        for s0, e0, y in self._lines:
            x = 0
            for i in range(s0, e0 + 1):
                w = fm.horizontalAdvance(self._chars[i])
                cur = self._block(i)
                if cur:
                    painter.fillRect(QRectF(x, y, w, line_h), _mark_bg)
                x += w
                if cur and i < e0:
                    nxt = self._block(i + 1)
                    if nxt and nxt != cur:
                        # 关抗锯齿画 1px 竖线：避免细线被 AA 晕成 2px 重影
                        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                        painter.fillRect(QRectF(x - 1, y, 1, line_h), _sep)
                        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 文字逐字符独立绘制，避免分段整串绘制在段边界处字形微移
        for s0, e0, y in self._lines:
            self._paint_text_line(painter, s0, e0, y, fm)

        # Debug：画布与卡片同底色（surface2），靠颜色看不出自身范围；虚线框标出
        if ThemeManager.instance().series == "debug":
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            pen = QPen(QColor("#1565c0"), 1)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

    def _block(self, i: int):
        """位置 ``i`` 所属的标记块：选区或 token 标记，无则 None"""
        if self._sel_s <= i <= self._sel_e:
            return ("sel",)
        tid = self._token_of[i]
        if tid is not None:
            return ("tok", tid)
        return None

    def _style_of(self, i: int) -> tuple[str, str]:
        """返回 ``(样式种类, 颜色令牌键)``：lit / tok / sel"""
        if self._sel_s <= i <= self._sel_e:
            return ("sel", "color.accent.strong")
        if self._token_of[i] is not None:
            return ("tok", "color.accent.strong")
        return ("lit", "color.text.primary")

    def _paint_text_line(self, painter: QPainter, s0: int, e0: int, y: int, fm) -> None:
        x = 0
        line_h = fm.height()
        for i in range(s0, e0 + 1):
            w = fm.horizontalAdvance(self._chars[i])
            _, key = self._style_of(i)
            painter.setFont(QFont(self.font()))
            painter.setPen(QColor(T(key)))
            painter.drawText(
                QRectF(x, y, w, line_h),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                self._chars[i],
            )
            x += w
