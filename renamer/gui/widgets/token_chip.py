"""可拖动 token 词组件：圆角矩形包裹，类型色标注，可拖动 / 可点选 / 可删除"""

from PySide6.QtCore import QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QDrag,
    QFont,
    QFontMetrics,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel

from ..theme import T
from .remove_button import RemoveButton

__all__ = ["MIME_TOKEN", "TokenChip", "chip_pixmap"]

# token 拖拽 MIME 类型（负载 = token id 十进制字符串）
MIME_TOKEN = "application/x-structured-renamer-token"


def chip_pixmap(name: str, value: str, color: str) -> QPixmap:
    """拖动跟随图：类型色描边圆角块 + 名字 + 值"""
    font = QFont()
    font.setPixelSize(int(T("font.sm")))
    fm = QFontMetrics(font)
    text = name + (f" · {value}" if value else "")
    w = max(24, fm.horizontalAdvance(text) + 16)
    h = fm.height() + 8
    pm = QPixmap(w, h)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor(color))
    painter.setBrush(QColor(T("color.bg.surface")))
    painter.drawRoundedRect(1, 1, pm.width() - 2, pm.height() - 2, 7, 7)
    painter.setPen(QColor(T("color.text.primary")))
    painter.setFont(font)
    painter.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, text)
    painter.end()
    return pm


class TokenChip(QFrame):
    """圆角矩形 token 词组件：只显示词本身，悬停看全部信息"""

    # 拖拽发起（参数为 token id）
    drag_started = Signal(int)
    # 单击（参数为 token id）：词池点击追加进组合，解析词左键激活进词池
    clicked = Signal(int)
    # 右键（参数为 token id）：取消激活（移出词池）
    right_clicked = Signal(int)
    # 删除按钮（参数为 token id）：组合内移除
    remove_clicked = Signal(int)

    def __init__(
        self,
        tid: int,
        name: str,
        value: str = "",
        type: str = "string",
        source: str = "parse",
        remove: bool = False,
        tooltip: str = "",
        active: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self._tid = tid
        self._name = name
        self._value = value
        self._type = type
        self._source = source
        self._active = active
        self._press_pos: QPoint | None = None
        self.setProperty("role", "t-chip")
        self.setProperty("tch", type)  # string / int / date / enum
        self.setProperty("tsrc", source)  # parse / enrich
        # 激活态统一主题色、未激活灰态
        self.setProperty("tstate", "active" if active else "inactive")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        lay = QHBoxLayout(self)
        # 紧凑胶囊：比字面量略高即可（此前 7,3 偏大导致与字面量一高一低）
        lay.setContentsMargins(5, 1, 5, 1)
        lay.setSpacing(4)

        # 只显示词本身；超长截断，避免 QLabel 最小宽度撑爆流向布局
        word = value or name
        _shown = word if len(word) <= 28 else word[:25] + "…"
        word_lbl = QLabel(_shown)
        word_lbl.setProperty("role", "t-chip-name")
        word_lbl.setToolTip(tooltip or self._info_text())
        lay.addWidget(word_lbl)
        if remove:
            del_btn = RemoveButton("移除词段")
            del_btn.clicked.connect(self._emit_remove)
            lay.addWidget(del_btn)

    def _info_text(self) -> str:
        """默认悬停信息：名 / 值 / 类型 / 来源（面板可传更全的 tooltip 覆盖）"""
        src = "解析" if self._source == "parse" else "enrich"
        return (
            f"名 = {self._name}"
            f" · 值 = {self._value or '（空）'}"
            f" · 类型 = {self._type}"
            f" · 来源 = {src}"
        )

    # 信号桥
    def _emit_remove(self) -> None:
        self.remove_clicked.emit(self._tid)

    # 鼠标：左键按下上报单击（可发拖拽）；右键取消激活
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
            self.clicked.emit(self._tid)
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit(self._tid)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if (
            self._press_pos is not None
            and (event.buttons() & Qt.MouseButton.LeftButton)
            and (event.position().toPoint() - self._press_pos).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            self._start_drag()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._press_pos = None
        super().mouseReleaseEvent(event)

    # 拖拽
    def _start_drag(self) -> None:
        """发起 token 拖拽：携带 token id，阻塞到放置 / 取消才返回"""
        mime = QMimeData()
        mime.setData(MIME_TOKEN, str(self._tid).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        color = T("color.accent.strong") if self._active else T("color.text.secondary")
        drag.setPixmap(chip_pixmap(self._name, self._value, color))
        drag.setHotSpot(QPoint(10, 10))
        drag.exec_(Qt.DropAction.CopyAction)
        self._press_pos = None
