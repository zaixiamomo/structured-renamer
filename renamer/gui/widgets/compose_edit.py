"""组合编辑框：负责光标、键盘、菜单和拖放，引用读写交给 ComposeDocument。"""

from PySide6.QtCore import QMimeData, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPalette,
    QTextCharFormat,
    QTextCursor,
    QTextOption,
)
from PySide6.QtWidgets import QApplication, QLabel, QTextEdit

from ..theme import T, ThemeManager
from .compose_document import TOKEN_OBJECT_TYPE, ComposeDocument
from .compose_token import ComposeTokenRenderer
from .token_chip import MIME_TOKEN

__all__ = ["ComposeEdit"]


class ComposeEdit(QTextEdit):
    """组合渲染编辑框：普通文本 + 不可拆分的圆角词段混排"""

    token_dropped = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Qt 原生插入光标会继承相邻内联对象的高度，改为按正文字体绘制。
        self.setCursorWidth(0)
        self._caret_visible = True
        self._token_drag_active = False
        self._caret_timer = QTimer(self)
        self._caret_timer.timeout.connect(self._blink_caret)
        self.selectionChanged.connect(self._reset_caret)
        self.setProperty("role", "compose-edit")
        self.setAcceptDrops(True)
        self.cursorPositionChanged.connect(self._on_cursor_moved)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        # 无内部滚动：高度始终贴合内容（空态收成一行，随内容增长），滚动交给侧栏
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().setDocumentMargin(0)
        self.document().contentsChanged.connect(self._fit_height)
        # 文档默认字号与组合编辑区 QSS 保持一致。
        font = QFont(self.font())
        font.setPixelSize(int(T("font.md")))
        self.setFont(font)
        self.document().setDefaultFont(font)
        # 空态提示：与卡1 空态提示同款的悬浮 QLabel（role=note，QSS 决定 11px 灰字），
        # 真实内容非空即隐藏，避免手绘字号被控件字体盖掉
        self._hint_lbl = QLabel(self.viewport())
        self._hint_lbl.setProperty("role", "note")
        self._hint_lbl.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._hint_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._token_renderer = ComposeTokenRenderer(self)
        self.document().documentLayout().registerHandler(
            TOKEN_OBJECT_TYPE, self._token_renderer
        )
        self._content = ComposeDocument(self.document())
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)
        self._sync_palette()

    def set_hint(self, text: str) -> None:
        """空态提示文案（面板按词池状态推送：无词段/有词段两种）"""
        self._hint_lbl.setText(text)
        self._sync_hint_overlay()

    def _sync_hint_overlay(self) -> None:
        """提示悬浮层：仅在正文为空时显示并铺满视口（文字左对齐垂直居中）"""
        if self.toPlainText():
            self._hint_lbl.hide()
            return
        self._hint_lbl.setGeometry(self.viewport().rect())
        self._hint_lbl.show()

    # 对外契约：拖入 / 词池点击共用入口
    def set_delimiters(self, open: str, close: str) -> None:
        self._content.set_delimiters(open, close)

    def insert_token(self, render_name: str, spec: str = "") -> None:
        """插入显示原始值的词段对象；未登记时保留含格式注解的引用明文。"""
        cur = self.textCursor()
        self._content.insert_token(cur, render_name, spec)
        self.setTextCursor(cur)
        self.setFocus()

    def set_markup(self, text: str) -> None:
        """用 ``{name}`` / ``{name:fmt}`` 明文重建正文：已登记词段 -> 词段对象，其余保留原文"""
        cur = self.textCursor()
        cur.select(QTextCursor.SelectionType.Document)
        cur.removeSelectedText()
        cur.movePosition(QTextCursor.MoveOperation.Start)
        self._content.insert_markup(cur, text)
        self.setTextCursor(cur)

    def markup_text(self) -> str:
        """把正文序列化回 ``{name}`` / ``{name:fmt}`` 明文（TOML/预览/保存的唯一读口）"""
        return self._content.markup_text()

    def refresh_tokens(self, mapping: dict[str, tuple[str, str]]) -> None:
        """词段注册表更新：值/类型有变时重建就地展示（无词段用则跳过）"""
        self._token_renderer.clear()
        if self._content.refresh_tokens(mapping):
            self.set_markup(self.markup_text())

    # 主题热切：普通文字与词段高亮全部重取色
    def _on_theme_changed(self, _series: str) -> None:
        self._sync_palette()
        self._token_renderer.clear()
        self.document().markContentsDirty(0, self.document().characterCount())
        self._fit_height()
        self.viewport().update()

    # 普通文字颜色对齐 QSS color.text.code（QTextEdit 富文本文档不继承 QSS color）
    def _sync_palette(self) -> None:
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Text, QColor(T("color.text.code")))
        pal.setColor(
            QPalette.ColorRole.PlaceholderText, QColor(T("color.text.secondary"))
        )
        self.setPalette(pal)

    # 高度贴合内容（无内部滚动）：空态收成一行字符高，随内容增长自动加高
    def _fit_height(self) -> None:
        if self.viewport().width() <= 0:
            return
        fm = self.fontMetrics()
        doc = self.document()
        h = doc.documentLayout().documentSize().height()
        target = max(fm.height() + 2, int(h) + 2)
        if target != self.height():
            self.setFixedHeight(target)
        self._sync_hint_overlay()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_height()

    def _caret_rect(self) -> QRectF:
        cursor = self.textCursor()
        rect = QRectF(self.cursorRect())
        metrics = QFontMetricsF(self.font())
        block = cursor.block()
        line = block.layout().lineForTextPosition(cursor.positionInBlock())
        if line.isValid():
            block_rect = self.document().documentLayout().blockBoundingRect(block)
            # 光标以插入点为中心，避免 1px 笔画只向右延伸造成两侧间距不等。
            x, _ = line.cursorToX(cursor.positionInBlock())
            rect.moveLeft(
                block_rect.left() + x - self.horizontalScrollBar().value() - 0.5
            )
            rect.moveTop(
                block_rect.top()
                + line.y()
                + line.ascent()
                - metrics.ascent()
                - self.verticalScrollBar().value()
            )
        rect.setHeight(metrics.height())
        rect.setWidth(1)
        return rect

    def _reset_caret(self) -> None:
        self._caret_visible = True
        self._caret_timer.stop()
        flash = QApplication.cursorFlashTime()
        if self.hasFocus() and not self.isReadOnly() and flash > 0:
            self._caret_timer.start(max(1, flash // 2))
        self.viewport().update()

    def _blink_caret(self) -> None:
        self._caret_visible = not self._caret_visible
        self.viewport().update()

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self._reset_caret()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._caret_timer.stop()
        self.viewport().update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if (
            (self.hasFocus() or self._token_drag_active)
            and not self.isReadOnly()
            and not self.textCursor().hasSelection()
            and (self._caret_visible or self._token_drag_active)
        ):
            painter = QPainter(self.viewport())
            painter.fillRect(
                self._caret_rect(), self.palette().color(QPalette.ColorRole.Text)
            )

    def inputMethodQuery(self, query):
        if query == Qt.InputMethodQuery.ImCursorRectangle:
            return self._caret_rect()
        return super().inputMethodQuery(query)

    # 词段按整体导航和删除；文档表示负责识别字段边界。

    def _on_cursor_moved(self) -> None:
        self._reset_caret()
        # 光标不可能在字段内部；键入恒为默认格式，避免 Qt 把字段格式延续给新输入
        if not self.textCursor().hasSelection():
            self.setCurrentCharFormat(QTextCharFormat())

    def inputMethodEvent(self, event) -> None:
        self.setCurrentCharFormat(QTextCharFormat())
        super().inputMethodEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.text() and not event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier
        ):
            self.setCurrentCharFormat(QTextCharFormat())
        super().keyPressEvent(event)

    # 剪贴板：复制/剪切把选区序列化为 ``{name}`` 明文，粘贴按明文重建（跨文档
    # 复制标记格式不可靠；粘贴恒为普通格式，杜绝富文本样式传染）
    def createMimeDataFromSelection(self) -> QMimeData:
        cur = self.textCursor()
        mime = QMimeData()
        mime.setText(
            self._content.markup_text(cur.selectionStart(), cur.selectionEnd())
        )
        return mime

    def insertFromMimeData(self, source: QMimeData) -> None:
        text = source.text() if source.hasText() else ""
        if not text:
            return
        cur = self.textCursor()
        cur.beginEditBlock()
        self._content.insert_markup(cur, text)
        cur.endEditBlock()
        self.setTextCursor(cur)

    # 拖放：token 词段插入光标处
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(MIME_TOKEN):
            self._token_drag_active = True
            self.viewport().update()
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(MIME_TOKEN):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._token_drag_active = False
        self.viewport().update()
        event.accept()

    def dropEvent(self, event) -> None:
        self._token_drag_active = False
        self.viewport().update()
        md = event.mimeData()
        if not md.hasFormat(MIME_TOKEN):
            event.ignore()
            return
        try:
            tid = int(bytes(md.data(MIME_TOKEN)).decode("utf-8"))
        except ValueError:
            event.ignore()
            return
        # 保留编辑区已有的插入点，释放鼠标的位置只决定是否接受拖入。
        self.token_dropped.emit(tid)
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
