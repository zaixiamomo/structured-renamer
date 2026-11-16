"""编辑页共用卡片：QSS 外观与一致的内容留白。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget


class EditorCard(QWidget):
    """卡片子类只向 body 添加内容；标题由页面放在卡片上方。"""

    CONTENT_MARGIN_X = 12
    HINT_ROW_HEIGHT = 21

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("role", "match-pane")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(
            self.CONTENT_MARGIN_X, 10, self.CONTENT_MARGIN_X, 12
        )
        self.body.setSpacing(8)
