"""模板 / 规则末卡共用的只读 TOML 展示区：无内部滚动 + name/token 高亮点击跳转

高度恒等于当前宽度下全部可视行数（纵向滚动交给侧边抽屉），写入文本剥去尾部
空行；``name`` 值与 ``text`` 内的 token 占位按卡片1 的标记背景着色，左键点击
对应区块经信号通知面板跳转到标题栏 / 词段编辑行。两面板共用
:meth:`readonly` / :meth:`set_content`，只保留各自的信号接线。
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QTextCursor, QTextLayout
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit

from ..theme import T, ThemeManager

__all__ = ["TomlEdit"]


class TomlEdit(QPlainTextEdit):
    """只读 TOML 展示区（模板末卡 / 规则末卡共用）"""

    # 左键点击 name 高亮区（跳顶栏名称编辑）
    name_clicked = Signal()
    # 词段定位标识：模板页使用 token id，规则页使用渲染引用序号。
    token_clicked = Signal(int)

    @classmethod
    def readonly(cls, parent=None) -> "TomlEdit":
        """末卡共用实例：同 role + 同 objectName（QSS 并入卡片底色去边框），
        只读；name/token 信号接线由调用面板按各自语义连接"""
        edit = cls(parent)
        edit.setProperty("role", "template-edit")
        edit.setObjectName("templateTomlEdit")
        edit.setReadOnly(True)
        return edit

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAcceptDrops(False)
        # 末卡只读 TOML 并入卡片底、无内边距：去掉 QTextDocument 默认 4px 外边距，
        # 否则文本比卡内其余内容右移，视觉不齐
        self.document().setDocumentMargin(0)
        self.document().contentsChanged.connect(self._fit_height)
        # 可点击/着色区间：[start, end)，end 不含；文档明文坐标
        self._spans: list[dict] = []
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        # 高亮为 T() 内联色，主题热切自订阅重着色（不随 QSS 重刷）
        ThemeManager.instance().theme_changed.connect(self.rehighlight)

    # 面板侧统一写入口
    def set_content(self, text: str, spans: list[dict]) -> None:
        """写入展示文本并登记高亮区间（面板无脑全量调用）

        相同文本不重写文档，但仍同步变动的点击目标；区间须与剥去尾部空白后的
        明文坐标一致（尾部空白从不含区间）。
        """
        stripped = text.rstrip()
        text_changed = self.toPlainText() != stripped
        if text_changed:
            self.setPlainText(stripped)
        if text_changed or self._spans != spans:
            self.set_highlight_spans(spans)

    # 高亮与点击区间
    def set_highlight_spans(self, spans: list[dict]) -> None:
        """登记可点击/着色区间并按当前主题取色"""
        self._spans = list(spans or ())
        self._apply_formats()

    def rehighlight(self) -> None:
        """主题切换后按新取色重着色（区间不变）"""
        self._apply_formats()

    def _apply_formats(self) -> None:
        doc = self.document()
        bg = self._mark_bg()
        fg = QColor(T("color.accent.strong"))
        selections = []
        for sp in self._spans:
            start, end = sp["start"], sp["end"]
            if end <= start:
                continue
            cur = QTextCursor(doc)
            cur.setPosition(start)
            cur.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cur
            selection.format.setBackground(bg)
            selection.format.setForeground(fg)
            selections.append(selection)
        self.setExtraSelections(selections)
        self.viewport().update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        # 与拆分画布一致：相邻词段用 1px 半透明强调色标出接缝。
        tokens = [sp for sp in self._spans if sp["kind"] == "token"]
        ends = {sp["end"] for sp in tokens if sp["end"] > sp["start"]}
        color = QColor(T("color.accent.strong"))
        color.setAlphaF(0.45)
        painter = QPainter(self.viewport())
        for sp in tokens:
            start = sp["start"]
            if start not in ends or sp["end"] <= start:
                continue
            cursor = QTextCursor(self.document())
            cursor.setPosition(start)
            rect = self.cursorRect(cursor)
            cursor.movePosition(QTextCursor.MoveOperation.PreviousCharacter)
            if self.cursorRect(cursor).top() != rect.top():
                continue  # 换行已自然分隔，行首不额外画线。
            painter.fillRect(rect.x() - 1, rect.y(), 1, rect.height(), color)
        painter.end()

    def _span_at(self, pos) -> dict | None:
        """视图坐标命中可点击区间（None = 普通文本）"""
        idx = self.cursorForPosition(pos).position()
        for sp in self._spans:
            if sp["start"] <= idx < sp["end"]:
                return sp
        return None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            sp = self._span_at(event.position().toPoint())
            if sp is not None:
                if sp["kind"] == "name":
                    self.name_clicked.emit()
                elif sp["kind"] == "token":
                    self.token_clicked.emit(sp["tid"])
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        # 双击高亮区与单击同等处理，避免 Windows 双击判定吞掉跳转后的快速连点
        if event.button() == Qt.MouseButton.LeftButton:
            sp = self._span_at(event.position().toPoint())
            if sp is not None:
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            want = (
                Qt.CursorShape.PointingHandCursor
                if self._span_at(event.position().toPoint()) is not None
                else Qt.CursorShape.IBeamCursor
            )
            if self.viewport().cursor().shape() != want:
                self.viewport().setCursor(want)
        super().mouseMoveEvent(event)

    # 高度贴合内容（无内部滚动）
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_height()

    def _measure_lines(self) -> int:
        """按当前视口宽统计全部块的换行后可视行数（尾随空块不计）"""
        doc = self.document()
        width = self.viewport().width()
        blocks = []
        b = doc.firstBlock()
        while b.isValid():
            blocks.append(b)
            b = b.next()
        while blocks and not blocks[-1].text().strip():
            blocks.pop()  # 删去尾随空行
        total = 0
        opt = doc.defaultTextOption()
        font = self.font()
        for blk in blocks:
            tl = QTextLayout(blk.text())
            tl.setFont(font)
            tl.setTextOption(opt)
            tl.beginLayout()
            while True:
                line = tl.createLine()
                if not line.isValid():
                    break
                line.setLineWidth(width)
            tl.endLayout()
            total += tl.lineCount()
        return max(1, total)

    def _fit_height(self) -> None:
        if self.viewport().width() <= 0:
            return
        doc = self.document()
        fm = self.fontMetrics()
        content = self._measure_lines() * fm.height() + doc.documentMargin() * 2
        self.setFixedHeight(int(content) + self.frameWidth() * 2 + 2)

    # 卡片1 标记背景（accent 向白混合 65%，同 WordCanvas 选中/token 底色）
    @staticmethod
    def _mark_bg() -> QColor:
        acc = QColor(T("color.accent"))
        return QColor(
            round(acc.red() + (255 - acc.red()) * 0.65),
            round(acc.green() + (255 - acc.green()) * 0.65),
            round(acc.blue() + (255 - acc.blue()) * 0.65),
        )
