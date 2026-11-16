"""组合编辑器的文档表示：词段实例标记、引用读写、示例值与格式注解。

只操作 QTextDocument 和 QTextCursor；光标移动、选择、菜单及拖放归 ComposeEdit。
"""

from PySide6.QtGui import (
    QFont,
    QFontMetricsF,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
)

from renamer.app.authoring import AuthoringService

# 实例号让相邻同名字段保持独立；字段名和注解用于还原引用明文。
_TOK_PROP = int(QTextFormat.Property.UserProperty) + 1
_SALT_PROP = int(QTextFormat.Property.UserProperty) + 2
_SPEC_PROP = int(QTextFormat.Property.UserProperty) + 3
TOKEN_LABEL_PROPERTY = int(QTextFormat.Property.UserProperty) + 4
TOKEN_OBJECT_TYPE = int(QTextFormat.ObjectTypes.UserObject) + 1


class ComposeDocument:
    """把已有 Qt 文档中的内联词段对象与引用明文相互转换。"""

    def __init__(self, document: QTextDocument):
        self.document = document
        self._tokens: dict[str, tuple[str, str]] = {}
        self._open, self._close = "{", "}"
        self._salt = 0

    def refresh_tokens(self, mapping: dict[str, tuple[str, str]]) -> bool:
        """更新展示注册表，返回正文是否需要重新展示。"""
        if mapping == self._tokens:
            return False
        self._tokens = dict(mapping)
        return self.may_show_tokens()

    def insert_token(self, cur: QTextCursor, name: str, spec: str = "") -> None:
        """插入已登记词段；未知词段保留引用原文。"""
        spec = self._normalized_spec(name, spec)
        if name in self._tokens:
            self._insert_token_run(cur, name, spec)
        else:
            cur.setCharFormat(QTextCharFormat())
            cur.insertText(self._ref_text(name, spec))

    def set_delimiters(self, open: str, close: str) -> None:
        view = AuthoringService.tokenize("", open=open, close=close)
        if view.issues:
            raise ValueError(view.issues[0].message)
        self._open, self._close = open, close

    def _ref_text(self, name: str, spec: str) -> str:
        """词段引用明文：有注解写作 ``{name:fmt}``"""
        content = f"{name}:{spec}" if spec else name
        return self._open + content + self._close

    def _normalized_spec(self, name: str, spec: str) -> str:
        try:
            text = AuthoringService.format_reference(
                name, spec, open=self._open, close=self._close
            )
        except ValueError:
            return spec  # 未完成注解仍保留，正式校验负责拒绝。
        return text[len(self._open) : -len(self._close)].partition(":")[2]

    def _token_format(self, render_name: str, spec: str = "") -> QTextCharFormat:
        """每次引用对应一个不可拆分的内联对象。"""
        self._salt += 1
        fmt = QTextCharFormat()
        fmt.setProperty(_TOK_PROP, render_name)
        fmt.setProperty(_SALT_PROP, self._salt)
        fmt.setProperty(_SPEC_PROP, spec)
        fmt.setObjectType(TOKEN_OBJECT_TYPE)
        fmt.setProperty(TOKEN_LABEL_PROPERTY, self._token_label(render_name))
        fmt.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignMiddle)
        # Qt AlignMiddle 以 xHeight / 2 作为对象上升部与下降部之差。
        # 对象字体仅供排版测量；实际胶囊由 TokenChip 绘制，字号不随之改变。
        font = QFont(self.document.defaultFont())
        metrics = QFontMetricsF(font)
        if metrics.xHeight() > 0:
            ratio = 2 * (metrics.ascent() - metrics.descent()) / metrics.xHeight()
            if font.pixelSize() > 0:
                font.setPixelSize(max(1, round(font.pixelSize() * ratio)))
            else:
                font.setPointSizeF(max(1, font.pointSizeF() * ratio))
            fmt.setFont(font)
        return fmt

    def _token_label(self, render_name: str) -> str:
        """编辑区显示格式化前的原值；没有值时显示词段名。"""
        value, _type = self._tokens.get(render_name, ("", "string"))
        return value or render_name

    def _insert_token_run(
        self, cur: QTextCursor, render_name: str, spec: str = ""
    ) -> None:
        """插入显示原始值的内联词段，格式注解仅用于还原引用明文。"""
        cur.insertText("\ufffc", self._token_format(render_name, spec))
        cur.setCharFormat(QTextCharFormat())

    def insert_markup(self, cur: QTextCursor, text: str) -> None:
        """已登记引用显示示例值；未知引用、错误草稿和引用间的文字保留原文。"""
        view = AuthoringService.tokenize(text, open=self._open, close=self._close)
        if view.issues:
            cur.setCharFormat(QTextCharFormat())
            cur.insertText(text)
            return
        start = 0
        for part in view.spans:
            if not part.is_token() or part.name not in self._tokens:
                continue
            if start < part.s:
                cur.setCharFormat(QTextCharFormat())
                cur.insertText(text[start : part.s])
            inner = part.raw[len(self._open) : -len(self._close)]
            self._insert_token_run(cur, part.name, inner.partition(":")[2])
            start = part.e + 1
        if start < len(text):
            cur.setCharFormat(QTextCharFormat())
            cur.insertText(text[start:])

    def may_show_tokens(self) -> bool:
        """正文是否可能含词段用（内联对象或 ``{`` 明文引用），无则无需重建"""
        text = self.document.toPlainText()
        if self._open in text:
            return True
        doc = self.document
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                if it.fragment().charFormat().property(_TOK_PROP):
                    return True
                it += 1
            block = block.next()
        return False

    def markup_text(self, start: int = 0, end: int | None = None) -> str:
        """正文或选区 [start, end) 还原为引用明文，保留块间换行。"""
        parts: list[str] = []
        doc = self.document
        if end is None:
            end = doc.characterCount() - 1
        block = doc.findBlock(start)
        while block.isValid() and block.position() < end:
            bs = block.position()
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                fs = frag.position()
                fe = fs + frag.length()
                lo = max(fs, start)
                hi = min(fe, end)
                if lo >= hi:
                    it += 1
                    continue
                name = frag.charFormat().property(_TOK_PROP)
                if name:
                    spec = frag.charFormat().property(_SPEC_PROP) or ""
                    parts.append(self._ref_text(name, spec))
                else:
                    parts.append(frag.text()[lo - fs : hi - fs])
                it += 1
            # 块间换行符（block 长度含段分隔符，fragment 不含）
            if bs + block.length() <= end and block.next().isValid():
                parts.append("\n")
            block = block.next()
        return "".join(parts)
